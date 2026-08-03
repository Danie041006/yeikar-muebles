from sqlalchemy import func
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
from uuid import uuid4
from jose import jwt
import hashlib
import logging
from app.core.config import settings
from app.modules.users import model, schemas

# Configuración de hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash dummy para igualar el tiempo de verificación cuando el usuario no existe
DUMMY_HASH = pwd_context.hash("dummy-pass-placeholder")

logger = logging.getLogger("yeikar.auth")

# ------------------------------------------------------------
# Funciones de contraseña
# ------------------------------------------------------------
def verificar_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def obtener_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# ------------------------------------------------------------
# Funciones de búsqueda
# ------------------------------------------------------------
def obtener_usuario_por_nombre(db: Session, username: str):
    return db.query(model.Usuario).filter(model.Usuario.nombre_usuario == username).first()

def obtener_usuario_por_email(db: Session, email: str):
    return db.query(model.Usuario).filter(model.Usuario.email == email).first()

def obtener_usuario_por_id(db: Session, user_id: int):
    return db.query(model.Usuario).filter(model.Usuario.id == user_id).first()

# ------------------------------------------------------------
# Crear usuario
# ------------------------------------------------------------
def crear_usuario(db: Session, user: schemas.UsuarioCreate):
    existing = obtener_usuario_por_nombre(db, user.nombre_usuario)
    if existing:
        raise ValueError(f"El usuario {user.nombre_usuario} ya existe")
    
    if user.email:
        existing_email = obtener_usuario_por_email(db, user.email)
        if existing_email:
            raise ValueError(f"El email {user.email} ya está registrado")
    
    db_user = model.Usuario(
        nombre_usuario=user.nombre_usuario,
        email=user.email,
        password_hash=obtener_password_hash(user.password),
        activo=True
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# ------------------------------------------------------------
# Autenticación
# ------------------------------------------------------------
def autenticar_usuario(db: Session, username: str, password: str):
    user = obtener_usuario_por_nombre(db, username)
    if not user:
        pwd_context.verify(password, DUMMY_HASH)
        logger.info("login fallido para %s", username)
        return False

    if not verificar_password(password, user.password_hash):
        logger.info("login fallido para %s", username)
        return False

    if not user.activo:
        logger.info("login fallido para %s (inactivo)", username)
        return False

    logger.info("login exitoso para %s", username)
    return user

# ------------------------------------------------------------
# JWT
# ------------------------------------------------------------
def crear_token_acceso(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    # jti aleatorio: garantiza tokens unicos aunque se emitan en el mismo segundo
    # (la BD exige token_hash unico para la rotacion de refresh tokens)
    to_encode.setdefault("jti", uuid4().hex)
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def actualizar_ultimo_acceso(db: Session, user_id: int):
    user = obtener_usuario_por_id(db, user_id)
    if user:
        user.ultimo_acceso = datetime.utcnow()
        db.commit()

# ------------------------------------------------------------
# Seguridad: intentos de login y bloqueo
# ------------------------------------------------------------
def registrar_intento(db: Session, username: str, ip: str, exito: bool):
    db.query(model.LoginIntento).filter(
        model.LoginIntento.created_at < func.now() - timedelta(hours=1)
    ).delete(synchronize_session=False)
    db.add(model.LoginIntento(username=username, ip=ip, exito=exito))
    db.commit()

def usuario_bloqueado(db: Session, username: str, ip: str) -> bool:
    ventana = func.now() - timedelta(minutes=settings.LOGIN_VENTANA_MINUTOS)
    fallos_username = db.query(model.LoginIntento).filter(
        model.LoginIntento.username == username,
        model.LoginIntento.exito == False,
        model.LoginIntento.created_at >= ventana,
    ).count()
    if fallos_username >= settings.LOGIN_MAX_INTENTOS:
        return True
    fallos_ip = db.query(model.LoginIntento).filter(
        model.LoginIntento.ip == ip,
        model.LoginIntento.exito == False,
        model.LoginIntento.created_at >= ventana,
    ).count()
    return fallos_ip >= settings.LOGIN_MAX_INTENTOS_IP

# ------------------------------------------------------------
# Refresh tokens con rotación
# ------------------------------------------------------------
def guardar_refresh_token(db: Session, usuario_id: int, token: str):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    db.add(model.RefreshToken(
        usuario_id=usuario_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        revocado=False,
    ))
    db.commit()

def rotar_refresh_token(db: Session, token: str):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    rt = db.query(model.RefreshToken).filter(model.RefreshToken.token_hash == token_hash).first()
    if rt is None or rt.revocado or rt.expires_at < datetime.utcnow():
        return None
    rt.revocado = True
    db.commit()
    return rt.usuario

def revocar_tokens_usuario(db: Session, usuario_id: int):
    db.query(model.RefreshToken).filter(
        model.RefreshToken.usuario_id == usuario_id,
        model.RefreshToken.revocado == False,
    ).update({"revocado": True}, synchronize_session=False)
    db.commit()