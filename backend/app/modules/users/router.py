from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import List
from datetime import timedelta

from app.core.config import settings
from app.core.client_ip import obtener_ip_cliente
from app.db.session import get_db
from app.modules.auditoria.service import record_event
from app.modules.users import schemas, service, model
from app.modules.users.deps import (
    get_current_user,
    es_admin,
    modulos_accesibles,
    obtener_permisos_rol,
    guardar_permisos_rol,
    MODULOS_CATALOGO,
)
from app.modules.catalogos.model import Rol
from app.modules.catalogos.schemas import RolResponse

router = APIRouter()

def _sid_del_token(token: str):
    """sid (id de sesión) embebido en el JWT; None si el token no lo trae."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sid = payload.get("sid")
        return int(sid) if sid is not None else None
    except (JWTError, TypeError, ValueError):
        return None

def _emitir_sesion(db: Session, user: model.Usuario, request: Request) -> dict:
    """Login completo: fila de sesión + par de tokens atados a ella (claim sid)."""
    ip = obtener_ip_cliente(request)
    sesion = service.crear_sesion(db, user.id, ip, request.headers.get("user-agent", ""))
    access_token = service.crear_token_acceso(
        data={"sub": user.nombre_usuario, "type": "access", "sid": sesion.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = service.crear_token_acceso(
        data={"sub": user.nombre_usuario, "type": "refresh", "sid": sesion.id},
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    fila_refresh = service.guardar_refresh_token(db, user.id, refresh_token)
    sesion.refresh_token_id = fila_refresh.id
    db.commit()
    service.actualizar_ultimo_acceso(db, user.id)
    return {"access_token": access_token, "refresh_token": refresh_token}

# ------------------------------------------------------------
# Endpoints públicos
# ------------------------------------------------------------
@router.post("/register", response_model=schemas.UsuarioResponse, status_code=201)
def register(
    user: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin),
):
    """Registra un nuevo usuario (solo administradores)."""
    try:
        return service.crear_usuario(db, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def login(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Autentica con username y password (form-urlencoded; se admite el campo
    extra turnstile_token para el captcha invisible tras fallos repetidos).

    Si el usuario tiene 2FA activo (y este equipo no está en la lista de
    confiables) devuelve {"requiere_2fa": true, "ticket": ...} SIN tokens:
    el ticket dura 5 minutos y sirve solo para /2fa/verificar.
    """
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    ip = obtener_ip_cliente(request)
    if service.usuario_bloqueado(db, username, ip):
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo.",
        )

    user = service.autenticar_usuario(db, username, password)
    if not user:
        service.registrar_intento(db, username, ip, False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Captcha invisible: solo reta a quien YA puso las credenciales correctas
    # tras fallos repetidos (los intentos erróneos siguen respondiendo 401 y
    # el lockout por IP/combinación no cambia). El desafío NO cuenta como
    # fallo: quien puso la clave correcta no está adivinando nada.
    if service.captcha_requerido(db, username, ip):
        token_captcha = form.get("turnstile_token") or ""
        if not token_captcha or not service.verificar_turnstile(token_captcha, ip):
            raise HTTPException(
                status_code=400,
                detail={"requiere_captcha": True, "mensaje": "Verificación anti-bots requerida."},
            )

    # Segundo factor: contraseña correcta ≠ acceso. Este equipo confiable
    # (cookie firmada de 30 días) pasa directo; los demás resuelven el código.
    if user.totp_habilitado and not service.dispositivo_confiable(request, user):
        return {"requiere_2fa": True, "ticket": service.crear_ticket_2fa(user)}

    ultimo_acceso_previo = user.ultimo_acceso
    tokens = _emitir_sesion(db, user, request)
    service.registrar_intento(db, username, ip, True)
    return {
        "access_token": tokens["access_token"],
        "token_type": "bearer",
        "refresh_token": tokens["refresh_token"],
        "ultimo_acceso_previo": ultimo_acceso_previo,
    }

@router.post("/refresh", response_model=schemas.Token)
async def refresh_token(
    payload_in: schemas.RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Recibe un refresh token y retorna nuevos access y refresh tokens.
    El token recibido se revoca (rotación) y la MISMA sesión continúa con el
    token nuevo (no se crea una fila de sesión por cada refresh).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar el refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(payload_in.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub: str = payload.get("sub")
        token_type: str = payload.get("type")
        sid: str = payload.get("sid")
        if sub is None or token_type != "refresh":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    resultado = service.rotar_refresh_token(db, payload_in.refresh_token)
    if resultado is None:
        raise credentials_exception
    user, refresh_viejo = resultado
    if not user.activo:
        raise credentials_exception

    ip = obtener_ip_cliente(request)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = service.crear_token_acceso(
        data={"sub": user.nombre_usuario, "type": "access", "sid": sid},
        expires_delta=access_token_expires,
    )
    new_refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    new_refresh_token = service.crear_token_acceso(
        data={"sub": user.nombre_usuario, "type": "refresh", "sid": sid},
        expires_delta=new_refresh_token_expires,
    )
    nueva_fila = service.guardar_refresh_token(db, user.id, new_refresh_token)
    service.vincular_sesion_a_nuevo_refresh(db, refresh_viejo.id, nueva_fila.id)
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": new_refresh_token}

# ------------------------------------------------------------
# Endpoint protegido (requiere token)
# ------------------------------------------------------------
@router.get("/me", response_model=schemas.MeResponse)
def read_users_me(
    db: Session = Depends(get_db),
    current_user: model.Usuario = Depends(get_current_user)
):
    """Devuelve el usuario autenticado con el detalle de módulos que puede ver/editar."""
    base = schemas.UsuarioResponse.model_validate(current_user)
    return schemas.MeResponse(**base.model_dump(), modulos=modulos_accesibles(db, current_user))

# ------------------------------------------------------------
# Roles y permisos (solo administradores)
# ------------------------------------------------------------
@router.get("/roles", response_model=List[RolResponse])
def listar_roles(
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Lista todos los roles disponibles."""
    return db.query(Rol).all()

@router.get("/modulos", response_model=List[schemas.ModulosCatalogo])
def listar_modulos(
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Catálogo de módulos (para el panel de privilegios)."""
    return MODULOS_CATALOGO

@router.get("/roles/{rol_id}/permisos", response_model=List[schemas.ModuloAcceso])
def ver_permisos_rol(
    rol_id: int,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Estado de acceso a cada módulo para un rol."""
    rol = db.query(Rol).filter(Rol.id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    return obtener_permisos_rol(db, rol_id)

@router.put("/roles/{rol_id}/permisos", response_model=List[schemas.ModuloAcceso])
def actualizar_permisos_rol(
    rol_id: int,
    esquema: schemas.RolPermisosUpdate,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Guarda los módulos (y si se gestionan) de un rol."""
    rol = db.query(Rol).filter(Rol.id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    guardar_permisos_rol(db, rol_id, [p.model_dump() for p in esquema.permisos])
    return obtener_permisos_rol(db, rol_id)

@router.post("/usuario/{usuario_id}/roles/{rol_id}", response_model=schemas.UsuarioResponse)
def asignar_rol_usuario(
    usuario_id: int,
    rol_id: int,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Asigna un rol a un usuario."""
    user = db.query(model.Usuario).filter(model.Usuario.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    rol = db.query(Rol).filter(Rol.id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")

    if rol not in user.roles:
        user.roles.append(rol)
        db.commit()
        db.refresh(user)
    return user

@router.delete("/usuario/{usuario_id}/roles/{rol_id}", response_model=schemas.UsuarioResponse)
def remover_rol_usuario(
    usuario_id: int,
    rol_id: int,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Remueve un rol de un usuario."""
    user = db.query(model.Usuario).filter(model.Usuario.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    rol = db.query(Rol).filter(Rol.id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")

    if rol in user.roles:
        user.roles.remove(rol)
        db.commit()
        db.refresh(user)
    return user

@router.get("/users", response_model=List[schemas.UsuarioResponse])
def listar_usuarios(
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Lista todos los usuarios (solo administradores)."""
    return db.query(model.Usuario).order_by(model.Usuario.id).all()

@router.put("/users/{usuario_id}/status", response_model=schemas.UsuarioResponse)
def actualizar_estado_usuario(
    usuario_id: int,
    activo: bool,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Activa o desactiva un usuario (solo administradores)."""
    if usuario_id == usuario_actual.id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario")

    user = db.query(model.Usuario).filter(model.Usuario.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.activo = activo
    db.commit()
    db.refresh(user)
    return user

@router.post("/users", response_model=schemas.UsuarioResponse, status_code=201)
def admin_crear_usuario(
    user_in: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Crea un nuevo usuario directamente (solo administradores)."""
    try:
        return service.crear_usuario(db, user_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/users/{usuario_id}", status_code=204)
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin)
):
    """Elimina un usuario (solo administradores)."""
    if usuario_id == usuario_actual.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")

    user = db.query(model.Usuario).filter(model.Usuario.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db.delete(user)
    db.commit()
    return None

# ------------------------------------------------------------
# Mi seguridad: sesiones visibles y cambio de contraseña
# ------------------------------------------------------------
@router.get("/sesiones", response_model=List[schemas.SesionResponse])
def listar_sesiones(
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/login")),
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Sesiones activas del usuario autenticado; 'actual' viene marcada."""
    sid = _sid_del_token(token)
    return [
        schemas.SesionResponse(
            id=s.id, ip=s.ip, user_agent=s.user_agent, revocada=s.revocada,
            creado_en=s.creado_en, ultimo_uso=s.ultimo_uso, actual=(s.id == sid),
        )
        for s in service.sesiones_activas(db, usuario_actual.id)
    ]

@router.delete("/sesiones/{sesion_id}", status_code=204)
def cerrar_sesion(
    sesion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Revoca una sesión propia (y su refresh token)."""
    if not service.revocar_sesion(db, usuario_actual.id, sesion_id):
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return None

@router.post("/sesiones/cerrar-otras")
def cerrar_otras(
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/login")),
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Cierra todas las sesiones excepto la que hace la petición."""
    sid = _sid_del_token(token)
    if sid is None:
        raise HTTPException(status_code=400, detail="No se pudo identificar la sesión actual")
    return {"revocadas": service.cerrar_otras_sesiones(db, usuario_actual.id, sid)}

@router.put("/me/password")
def cambiar_mi_password(
    esquema: schemas.CambioPasswordRequest,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Cambia la contraseña propia y revoca TODAS las sesiones: hay que
    volver a entrar en cada equipo (así una clave filtrada deja de servir)."""
    if not service.verificar_password(esquema.password_actual, usuario_actual.password_hash):
        raise HTTPException(status_code=401, detail="La contraseña actual no coincide")
    usuario_actual.password_hash = service.obtener_password_hash(esquema.password_nueva)
    service.revocar_todas_las_sesiones(db, usuario_actual.id)
    db.commit()
    return {"mensaje": "Contraseña actualizada. Inicia sesión de nuevo con la nueva."}

# ------------------------------------------------------------
# Mi seguridad: 2FA con app (TOTP)
# ------------------------------------------------------------
@router.post("/2fa/generar")
def generar_2fa(
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Genera (o re-genera) el secreto TOTP y devuelve el QR para la app."""
    service.generar_totp(db, usuario_actual)
    uri = service.uri_totp(usuario_actual)
    return {"otpauth_uri": uri, "qr_base64": service.qr_totp_base64(uri)}

@router.post("/2fa/activar")
def activar_2fa(
    esquema: schemas.Codigo2FARequest,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Confirma el primer código de la app y devuelve los códigos de respaldo
    (se muestran UNA vez)."""
    try:
        codigos = service.activar_totp(db, usuario_actual, esquema.codigo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"codigos_respaldo": codigos}

@router.post("/2fa/desactivar")
def desactivar_2fa(
    esquema: schemas.Codigo2FARequest,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Apaga el 2FA pidiendo un código vigente (o de respaldo)."""
    try:
        service.desactivar_totp(db, usuario_actual, esquema.codigo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"mensaje": "2FA desactivado."}

@router.post("/2fa/verificar")
async def verificar_2fa(
    payload: schemas.Verificar2FARequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Segundo factor del login: ticket + código TOTP (o de respaldo).
    Con recordar_equipo deja una cookie firmada de 30 días para este equipo."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Ticket de 2FA inválido o expirado. Ingresa tu contraseña de nuevo.",
    )
    try:
        payload_jwt = jwt.decode(
            payload.ticket, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            options={"verify_exp": True, "require_exp": True},
        )
        username: str = payload_jwt.get("sub")
        if payload_jwt.get("type") != "2fa" or not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = service.obtener_usuario_por_nombre(db, username)
    if user is None or not user.activo:
        raise credentials_exception
    if not service.verificar_codigo_2fa(db, user, payload.codigo):
        service.registrar_intento(db, username, obtener_ip_cliente(request), False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código incorrecto")

    tokens = _emitir_sesion(db, user, request)
    service.registrar_intento(db, username, obtener_ip_cliente(request), True)
    body = {
        "access_token": tokens["access_token"],
        "token_type": "bearer",
        "refresh_token": tokens["refresh_token"],
    }
    if payload.recordar_equipo:
        respuesta = JSONResponse(body)
        dispositivo = service.crear_token_acceso(
            data={"sub": user.nombre_usuario, "type": "device"},
            expires_delta=timedelta(days=30),
        )
        respuesta.set_cookie(
            key="yeikar_dispositivo", value=dispositivo,
            max_age=30 * 24 * 3600, httponly=True, samesite="lax",
            secure=not settings.DEBUG,
        )
        return respuesta
    return body

@router.post("/users/{usuario_id}/reset-2fa")
def resetear_2fa_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(es_admin),
):
    """El dueño/admin rescata a un usuario que perdió su app: apaga su 2FA,
    cierra sus sesiones y lo deja entrar solo con contraseña (auditado)."""
    target = db.query(model.Usuario).filter(model.Usuario.id == usuario_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    service.resetear_totp(db, usuario_id)
    service.revocar_todas_las_sesiones(db, usuario_id)
    record_event(
        db,
        actor=usuario_actual,
        action="UPDATE",
        entity_type="usuario",
        entity_id=usuario_id,
        after={"accion": "reset_2fa", "usuario": target.nombre_usuario},
    )
    return {"mensaje": f"2FA de {target.nombre_usuario} reseteado. Sus sesiones fueron cerradas."}

# ------------------------------------------------------------
# Mi seguridad: huella / passkeys (WebAuthn)
# ------------------------------------------------------------
@router.post("/webauthn/registro/inicio")
def huella_registro_inicio(
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Opciones WebAuthn para registrar la huella de este equipo."""
    return service.opciones_registro_huella(db, usuario_actual)

@router.post("/webauthn/registro/fin")
def huella_registro_fin(
    esquema: schemas.RegistroHuellaRequest,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Valida la ceremonia del navegador y guarda la llave del equipo."""
    try:
        credencial = service.registrar_credencial_huella(
            db, usuario_actual, esquema.dispositivo or "", esquema.respuesta)
    except Exception as e:
        # Cualquier rechazo criptográfico (desafío, origen, rp_id) es 400.
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": credencial.id, "dispositivo": credencial.dispositivo, "mensaje": "Huella registrada."}

@router.get("/webauthn/huellas", response_model=List[schemas.HuellaResponse])
def listar_huellas(
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Huellas biometricas activas del usuario autenticado."""
    return service.huellas_activas(db, usuario_actual.id)

@router.delete("/webauthn/huellas/{huella_id}", status_code=204)
def borrar_huella(
    huella_id: int,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user),
):
    """Desactiva una huella propia (el equipo deja de poder entrar así)."""
    huella = db.query(model.CredencialWebauthn).filter(
        model.CredencialWebauthn.id == huella_id,
        model.CredencialWebauthn.usuario_id == usuario_actual.id,
    ).first()
    if not huella or not huella.activa:
        raise HTTPException(status_code=404, detail="Huella no encontrada")
    huella.activa = False
    db.commit()
    return None

@router.post("/webauthn/login/inicio")
def huella_login_inicio(
    esquema: schemas.UsuarioHuellaRequest,
    db: Session = Depends(get_db),
):
    """Opciones de autenticación biométrica (público: aún no hay sesión).

    Con `nombre_usuario` filtra las huellas de esa cuenta; sin él devuelve
    opciones discoverables + `sesion_huella` para el modo sin usuario.
    """
    try:
        return service.opciones_login_huella(db, (esquema.nombre_usuario or "").strip() or None)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/webauthn/login/fin")
def huella_login_fin(
    esquema: schemas.LoginHuellaRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login con huella: la firma biométrica sustituye contraseña + 2FA."""
    try:
        nombre = (esquema.nombre_usuario or "").strip() or None
        user = service.verificar_login_huella(db, esquema.respuesta, nombre, esquema.sesion_huella)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    tokens = _emitir_sesion(db, user, request)
    service.registrar_intento(db, user.nombre_usuario, obtener_ip_cliente(request), True)
    return {
        "access_token": tokens["access_token"],
        "token_type": "bearer",
        "refresh_token": tokens["refresh_token"],
        "ultimo_acceso_previo": user.ultimo_acceso,
    }