from sqlalchemy import func
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
from uuid import uuid4
from jose import jwt, JWTError
import hashlib
import io
import json
import base64
import secrets
import logging
import httpx
import pyotp
import qrcode
from webauthn import (
    generate_registration_options,
    generate_authentication_options,
    verify_registration_response,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers import (
    bytes_to_base64url,
    base64url_to_bytes,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from app.core.config import settings
from app.core.hora_ve import ahora_ve
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
    # Case-insensitive: evita cuentas duplicadas por mayúsculas y eludir
    # el contador de intentos variando la caja del nombre de usuario.
    return db.query(model.Usuario).filter(func.lower(model.Usuario.nombre_usuario) == username.lower()).first()

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
        nombre=user.nombre,
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
        user.ultimo_acceso = ahora_ve()
        db.commit()

# ------------------------------------------------------------
# Seguridad: intentos de login y bloqueo
# ------------------------------------------------------------
def registrar_intento(db: Session, username: str, ip: str, exito: bool):
    db.query(model.LoginIntento).filter(
        model.LoginIntento.created_at < func.now() - timedelta(hours=1)
    ).delete(synchronize_session=False)
    db.add(model.LoginIntento(username=username.lower(), ip=ip, exito=exito))
    db.commit()

def usuario_bloqueado(db: Session, username: str, ip: str) -> bool:
    """Anti-brute-force sin DoS trivial:
    - por combinación (cuenta, IP): un atacante solo se bloquea a sí mismo;
    - por IP global: tope duro por origen;
    - cuenta atacada desde >= 3 IPs distintas en la ventana: brute-force distribuido."""
    username = username.lower()
    ventana = func.now() - timedelta(minutes=settings.LOGIN_VENTANA_MINUTOS)
    base = db.query(model.LoginIntento).filter(
        model.LoginIntento.exito == False,
        model.LoginIntento.created_at >= ventana,
    )
    fallos_combo = base.filter(
        model.LoginIntento.username == username,
        model.LoginIntento.ip == ip,
    ).count()
    if fallos_combo >= settings.LOGIN_MAX_INTENTOS:
        return True
    fallos_ip = base.filter(model.LoginIntento.ip == ip).count()
    if fallos_ip >= settings.LOGIN_MAX_INTENTOS_IP:
        return True
    ips_distintas = base.filter(
        model.LoginIntento.username == username
    ).with_entities(model.LoginIntento.ip).distinct().count()
    return ips_distintas >= settings.LOGIN_IP_DISTINTAS_PARA_BLOQUEO

# ------------------------------------------------------------
# Refresh tokens con rotación
# ------------------------------------------------------------
def guardar_refresh_token(db: Session, usuario_id: int, token: str) -> model.RefreshToken:
    rt = model.RefreshToken(
        usuario_id=usuario_id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        revocado=False,
    )
    db.add(rt)
    db.commit()
    db.refresh(rt)
    return rt

def rotar_refresh_token(db: Session, token: str):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    # FOR UPDATE: dos refrescos simultáneos con el mismo token se serializan;
    # el segundo ve revocado=True y no emite un par nuevo (rotación atómica).
    rt = db.query(model.RefreshToken).filter(
        model.RefreshToken.token_hash == token_hash
    ).with_for_update().first()
    if rt is None or rt.revocado or rt.expires_at < datetime.utcnow():
        return None
    rt.revocado = True
    db.commit()
    return rt.usuario, rt

def revocar_tokens_usuario(db: Session, usuario_id: int):
    db.query(model.RefreshToken).filter(
        model.RefreshToken.usuario_id == usuario_id,
        model.RefreshToken.revocado == False,
    ).update({"revocado": True}, synchronize_session=False)
    db.commit()

# ------------------------------------------------------------
# Sesiones visibles (una por login)
# ------------------------------------------------------------
def crear_sesion(db: Session, usuario_id: int, ip: str, user_agent: str) -> model.Sesion:
    sesion = model.Sesion(
        usuario_id=usuario_id,
        ip=(ip or None),
        user_agent=(user_agent or "")[:300],
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion

def sesiones_activas(db: Session, usuario_id: int):
    return db.query(model.Sesion).filter(
        model.Sesion.usuario_id == usuario_id,
        model.Sesion.revocada == False,
    ).order_by(model.Sesion.ultimo_uso.desc()).all()

def _revocar_refresh_por_ids(db: Session, refresh_ids: list):
    if refresh_ids:
        db.query(model.RefreshToken).filter(
            model.RefreshToken.id.in_(refresh_ids),
        ).update({"revocado": True}, synchronize_session=False)

def revocar_sesion(db: Session, usuario_id: int, sesion_id: int) -> bool:
    sesion = db.query(model.Sesion).filter(
        model.Sesion.id == sesion_id,
        model.Sesion.usuario_id == usuario_id,
    ).first()
    if not sesion or sesion.revocada:
        return False
    if sesion.refresh_token_id:
        _revocar_refresh_por_ids(db, [sesion.refresh_token_id])
    sesion.revocada = True
    db.commit()
    return True

def cerrar_otras_sesiones(db: Session, usuario_id: int, sesion_actual_id: int) -> int:
    otras = db.query(model.Sesion).filter(
        model.Sesion.usuario_id == usuario_id,
        model.Sesion.revocada == False,
        model.Sesion.id != sesion_actual_id,
    ).all()
    _revocar_refresh_por_ids(db, [s.refresh_token_id for s in otras if s.refresh_token_id])
    for sesion in otras:
        sesion.revocada = True
    db.commit()
    return len(otras)

def revocar_todas_las_sesiones(db: Session, usuario_id: int) -> None:
    """Al cambiar la contraseña: cero sesiones vivas y cero refresh vigentes."""
    db.query(model.Sesion).filter(
        model.Sesion.usuario_id == usuario_id,
        model.Sesion.revocada == False,
    ).update({"revocada": True}, synchronize_session=False)
    revocar_tokens_usuario(db, usuario_id)

def vincular_sesion_a_nuevo_refresh(db: Session, refresh_viejo_id: int, refresh_nuevo_id: int) -> None:
    """Rotación de refresh: la misma sesión continúa con el token nuevo."""
    db.query(model.Sesion).filter(
        model.Sesion.refresh_token_id == refresh_viejo_id,
    ).update(
        {"refresh_token_id": refresh_nuevo_id, "ultimo_uso": func.now()},
        synchronize_session=False,
    )
    db.commit()

# ------------------------------------------------------------
# Captcha invisible (Cloudflare Turnstile)
# ------------------------------------------------------------
def contar_fallos_recientes(db: Session, username: str, ip: str) -> int:
    """Fallos en la ventana por (usuario, ip): gatillo del captcha."""
    ventana = func.now() - timedelta(minutes=settings.LOGIN_VENTANA_MINUTOS)
    return db.query(model.LoginIntento).filter(
        model.LoginIntento.exito == False,
        model.LoginIntento.created_at >= ventana,
        model.LoginIntento.username == username.lower(),
        model.LoginIntento.ip == ip,
    ).count()

def captcha_requerido(db: Session, username: str, ip: str) -> bool:
    return bool(settings.TURNSTILE_SECRET_KEY) and (
        contar_fallos_recientes(db, username, ip) >= settings.CAPTCHA_LUEGO_DE_FALLOS
    )

def verificar_turnstile(token: str, ip: str) -> bool:
    """Valida el token del widget con Cloudflare. Sin clave configurada no
    hay captcha y esto devuelve True (desactivado == pasa)."""
    if not settings.TURNSTILE_SECRET_KEY:
        return True
    try:
        respuesta = httpx.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": settings.TURNSTILE_SECRET_KEY, "response": token, "remoteip": ip},
            timeout=10.0,
        )
        return bool(respuesta.json().get("success"))
    except Exception:
        logger.exception("siteverify de Turnstile no respondió; se rechaza el intento")
        return False

# ------------------------------------------------------------
# 2FA con app (TOTP RFC 6238)
# ------------------------------------------------------------
ISSUER_2FA = "YEIKAR"

def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.encode("utf-8")).hexdigest()

def dispositivo_confiable(request, usuario: model.Usuario) -> bool:
    """Cookie firmada 'yeikar_dispositivo' (30 días): el equipo ya pasó 2FA."""
    cookie = request.cookies.get("yeikar_dispositivo")
    if not cookie:
        return False
    try:
        payload = jwt.decode(
            cookie, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            options={"verify_exp": True, "require_exp": True},
        )
        return payload.get("type") == "device" and payload.get("sub") == usuario.nombre_usuario
    except JWTError:
        return False

def generar_totp(db: Session, usuario: model.Usuario) -> str:
    """Secreto pendiente (o re-generado). Regenerar rota el secreto pero no
    apaga un 2FA ya activo: quien regenera debe re-escanear el QR en la app."""
    usuario.totp_secret = pyotp.random_base32()
    db.commit()
    return usuario.totp_secret

def uri_totp(usuario: model.Usuario) -> str:
    return pyotp.TOTP(usuario.totp_secret).provisioning_uri(
        name=usuario.nombre_usuario, issuer_name=ISSUER_2FA,
    )

def qr_totp_base64(uri: str) -> str:
    imagen = qrcode.make(uri)
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")

def activar_totp(db: Session, usuario: model.Usuario, codigo: str) -> list:
    """Confirma el primer código de la app y emite 10 códigos de respaldo
    (se devuelven UNA vez; en BD solo quedan sus hashes)."""
    if not usuario.totp_secret:
        raise ValueError("Genera primero el código QR.")
    if not pyotp.TOTP(usuario.totp_secret).verify(codigo, valid_window=1):
        raise ValueError("El código no coincide. Verifica la hora del equipo y reintenta.")
    codigos = [f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}" for _ in range(10)]
    usuario.totp_habilitado = True
    usuario.totp_respaldo_hash = json.dumps([_hash_codigo(c) for c in codigos])
    db.commit()
    return codigos

def verificar_codigo_2fa(db: Session, usuario: model.Usuario, codigo: str) -> bool:
    """Acepta TOTP vigente (ventana ±30s) o un código de respaldo de un solo uso."""
    codigo = (codigo or "").replace(" ", "").upper()
    if not usuario.totp_habilitado or not usuario.totp_secret:
        return False
    if pyotp.TOTP(usuario.totp_secret).verify(codigo, valid_window=1):
        return True
    if usuario.totp_respaldo_hash and codigo:
        hashes = json.loads(usuario.totp_respaldo_hash)
        digest = _hash_codigo(codigo)
        if digest in hashes:
            hashes.remove(digest)
            usuario.totp_respaldo_hash = json.dumps(hashes)
            db.commit()
            return True
    return False

def desactivar_totp(db: Session, usuario: model.Usuario, codigo: str) -> None:
    if not verificar_codigo_2fa(db, usuario, codigo):
        raise ValueError("Código inválido: el 2FA sigue activo.")
    usuario.totp_habilitado = False
    usuario.totp_secret = None
    usuario.totp_respaldo_hash = None
    db.commit()

def resetear_totp(db: Session, usuario_id: int) -> None:
    usuario = obtener_usuario_por_id(db, usuario_id)
    if usuario:
        usuario.totp_habilitado = False
        usuario.totp_secret = None
        usuario.totp_respaldo_hash = None
        db.commit()

def crear_ticket_2fa(usuario: model.Usuario) -> str:
    """Token corto (5 min) que demuestra contraseña correcta pendiente de 2FA."""
    return crear_token_acceso(
        data={"sub": usuario.nombre_usuario, "type": "2fa"},
        expires_delta=timedelta(minutes=5),
    )

# ------------------------------------------------------------
# Huella / passkeys (WebAuthn)
# ------------------------------------------------------------
# Desafíos en memoria (TTL 5 min). Dev/single-worker: suficiente; en prod
# multi-worker conviene moverlo a Redis (marcado para el rollout).
_DESAFIOS: dict = {}
TTL_DESAFIO = timedelta(minutes=5)

def _guardar_desafio(clave: str, desafio) -> None:
    _DESAFIOS[clave] = (desafio, datetime.utcnow() + TTL_DESAFIO)

def _tomar_desafio(clave: str):
    valor = _DESAFIOS.pop(clave, None)
    if not valor or valor[1] < datetime.utcnow():
        return None
    return valor[0]

def huellas_activas(db: Session, usuario_id: int):
    return db.query(model.CredencialWebauthn).filter(
        model.CredencialWebauthn.usuario_id == usuario_id,
        model.CredencialWebauthn.activa == True,  # noqa: E712
    ).order_by(model.CredencialWebauthn.creado_en.desc()).all()

def opciones_registro_huella(db: Session, usuario: model.Usuario) -> dict:
    """Opciones para que el navegador registre la huella de este equipo.

    Se pide llave residente (discoverable) para que el login SIN usuario
    funcione: el navegador guarda la cuenta dentro del autenticador y luego
    la ofrece al tocar la huella. Las huellas viejas (no residentes) siguen
    valiendo con el flujo clásico con usuario.
    """
    opciones = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(usuario.id).encode("utf-8"),
        user_name=usuario.nombre_usuario,
        user_display_name=usuario.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in huellas_activas(db, usuario.id)
        ],
    )
    _guardar_desafio(f"reg:{usuario.id}", opciones.challenge)
    return json.loads(options_to_json(opciones))

def registrar_credencial_huella(db: Session, usuario: model.Usuario, dispositivo: str, respuesta: dict) -> model.CredencialWebauthn:
    """Valida la ceremonia del navegador y guarda la llave pública del equipo."""
    desafio = _tomar_desafio(f"reg:{usuario.id}")
    if not desafio:
        raise ValueError("El registro expiró; vuelve a intentarlo.")
    verificacion = verify_registration_response(
        credential=respuesta,
        expected_challenge=desafio,
        expected_origin=settings.WEBAUTHN_EXPECTED_ORIGIN,
        expected_rp_id=settings.WEBAUTHN_RP_ID,
        require_user_verification=False,
    )
    credencial = model.CredencialWebauthn(
        usuario_id=usuario.id,
        credential_id=bytes_to_base64url(verificacion.credential_id),
        llave_publica=bytes_to_base64url(verificacion.credential_public_key),
        contador=verificacion.sign_count,
        dispositivo=(dispositivo or "Huella")[:100],
    )
    db.add(credencial)
    db.commit()
    db.refresh(credencial)
    return credencial

def _normalizar_credential_id(raw: str) -> str:
    """Normaliza el id de credencial (base64url sin relleno) para comparar."""
    return bytes_to_base64url(base64url_to_bytes(raw or ""))


def opciones_login_huella(db: Session, nombre_usuario: str | None = None) -> dict:
    """Opciones de autenticación, en modo híbrido.

    - CON usuario: flujo clásico, `allowCredentials` limitado a las huellas
      de esa cuenta (rápido y compatible con huellas viejas no residentes).
    - SIN usuario: no se filtra nada; el navegador ofrece las passkeys de
      este equipo y el usuario se descubre en `/fin` por la credencial.
      El desafío se ata a un `sesion_huella` aleatorio que el front devuelve.
    """
    nombre = (nombre_usuario or "").strip()
    if nombre:
        usuario = obtener_usuario_por_nombre(db, nombre)
        huellas = huellas_activas(db, usuario.id) if usuario else []
        if not usuario or not usuario.activo or not huellas:
            raise ValueError("No hay huellas registradas para ese usuario.")
        opciones = generate_authentication_options(
            rp_id=settings.WEBAUTHN_RP_ID,
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
                for c in huellas
            ],
        )
        _guardar_desafio(f"auth:{nombre.lower()}", opciones.challenge)
        return json.loads(options_to_json(opciones))
    # Sin usuario: passkeys discoverables, sin enumerar cuentas.
    opciones = generate_authentication_options(rp_id=settings.WEBAUTHN_RP_ID)
    sesion_huella = uuid4().hex
    _guardar_desafio(f"auth:anon:{sesion_huella}", opciones.challenge)
    return {"options": json.loads(options_to_json(opciones)), "sesion_huella": sesion_huella}


def _verificar_firma_huella(desafio, credencial: model.CredencialWebauthn, respuesta: dict) -> None:
    verificacion = verify_authentication_response(
        credential=respuesta,
        expected_challenge=desafio,
        expected_origin=settings.WEBAUTHN_EXPECTED_ORIGIN,
        expected_rp_id=settings.WEBAUTHN_RP_ID,
        require_user_verification=False,
        credential_public_key=base64url_to_bytes(credencial.llave_publica),
        credential_current_sign_count=credencial.contador,
    )
    credencial.contador = verificacion.new_sign_count
    credencial.ultimo_uso = ahora_ve()


def verificar_login_huella(
    db: Session,
    respuesta: dict,
    nombre_usuario: str | None = None,
    sesion_huella: str | None = None,
) -> model.Usuario:
    """Valida la firma biométrica y devuelve el usuario. El contador de firmas
    (lo lleva la librería) rechaza credenciales clonadas.

    Con `nombre_usuario` valida contra las huellas de esa cuenta; sin él
    descubre al dueño por el `credential_id` (requiere `sesion_huella`).
    """
    nombre = (nombre_usuario or "").strip()
    if nombre:
        usuario = obtener_usuario_por_nombre(db, nombre)
        if not usuario or not usuario.activo:
            raise ValueError("Usuario no encontrado.")
        huellas = {c.credential_id: c for c in huellas_activas(db, usuario.id)}
        credential_id = _normalizar_credential_id((respuesta or {}).get("id", ""))
        credencial = huellas.get(credential_id)
        if credencial is None:
            raise ValueError("Esta huella no está registrada para el usuario.")
        desafio = _tomar_desafio(f"auth:{nombre.lower()}")
        if not desafio:
            raise ValueError("El intento expiró; vuelve a intentar entrar con huella.")
        _verificar_firma_huella(desafio, credencial, respuesta)
        db.commit()
        return usuario
    # Sin usuario: descubrir por credencial global (solo discoverables nuevas
    # y cualquier llave cuya id coincida; las viejas no residentes también
    # validan si el navegador las ofrece).
    if not sesion_huella:
        raise ValueError("La sesión de huella expiró; vuelve a intentarlo.")
    desafio = _tomar_desafio(f"auth:anon:{sesion_huella}")
    if not desafio:
        raise ValueError("El intento expiró; vuelve a intentar entrar con huella.")
    credential_id = _normalizar_credential_id((respuesta or {}).get("id", ""))
    if not credential_id:
        raise ValueError("Respuesta de huella inválida.")
    credencial = db.query(model.CredencialWebauthn).filter(
        model.CredencialWebauthn.credential_id == credential_id,
        model.CredencialWebauthn.activa == True,  # noqa: E712
    ).first()
    if credencial is None:
        raise ValueError("Esta huella no está registrada en este equipo.")
    usuario = obtener_usuario_por_id(db, credencial.usuario_id)
    if not usuario or not usuario.activo:
        raise ValueError("Usuario no encontrado.")
    _verificar_firma_huella(desafio, credencial, respuesta)
    db.commit()
    return usuario
