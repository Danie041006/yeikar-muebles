from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt
from app.core.config import settings
from app.modules.users import model, schemas

# Configuración de hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
    print(f"\n🔐 Intento de login para: '{username}'")
    
    user = obtener_usuario_por_nombre(db, username)
    if not user:
        print("❌ Usuario NO encontrado")
        return False
    
    print(f"✅ Usuario encontrado: {user.nombre_usuario}")
    print(f"📝 Hash: {user.password_hash[:30]}...")
    
    if not verificar_password(password, user.password_hash):
        print("❌ Contraseña incorrecta")
        return False
    
    if not user.activo:
        print("❌ Usuario inactivo")
        return False
    
    print("✅ Autenticación exitosa")
    return user

# ------------------------------------------------------------
# JWT
# ------------------------------------------------------------
def crear_token_acceso(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
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