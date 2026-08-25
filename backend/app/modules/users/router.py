from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import List
from datetime import timedelta

from app.core.config import settings
from app.core.client_ip import obtener_ip_cliente
from app.db.session import get_db
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

@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Autentica al usuario con nombre_usuario y password.
    Retorna un token JWT y un refresh token.
    """
    ip = obtener_ip_cliente(request) if request else "unknown"
    if service.usuario_bloqueado(db, form_data.username, ip):
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo.",
        )
    user = service.autenticar_usuario(db, form_data.username, form_data.password)
    if not user:
        service.registrar_intento(db, form_data.username, ip, False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Crear token de acceso con expiración
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = service.crear_token_acceso(
        data={"sub": user.nombre_usuario, "type": "access"}, expires_delta=access_token_expires
    )
    # Crear refresh token con expiración más larga
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = service.crear_token_acceso(
        data={"sub": user.nombre_usuario, "type": "refresh"}, expires_delta=refresh_token_expires
    )
    # Registrar el último acceso
    service.registrar_intento(db, form_data.username, ip, True)
    service.guardar_refresh_token(db, user.id, refresh_token)
    service.actualizar_ultimo_acceso(db, user.id)
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": refresh_token}

@router.post("/refresh", response_model=schemas.Token)
def refresh_token(
    payload_in: schemas.RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Recibe un refresh token y retorna nuevos access y refresh tokens.
    El token recibido se revoca (rotación) y el nuevo par queda registrado en BD.
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
        if sub is None or token_type != "refresh":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = service.rotar_refresh_token(db, payload_in.refresh_token)
    if user is None or not user.activo:
        raise credentials_exception

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = service.crear_token_acceso(
        data={"sub": user.nombre_usuario, "type": "access"}, expires_delta=access_token_expires
    )
    new_refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    new_refresh_token = service.crear_token_acceso(
        data={"sub": user.nombre_usuario, "type": "refresh"}, expires_delta=new_refresh_token_expires
    )
    service.guardar_refresh_token(db, user.id, new_refresh_token)
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