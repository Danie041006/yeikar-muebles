from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from datetime import timedelta

from app.db.session import get_db
from app.modules.users import schemas, service, model
from app.core.config import settings

router = APIRouter()

# Configura el esquema OAuth2: espera token en la URL /api/auth/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# ------------------------------------------------------------
# Dependencia que obtiene el usuario actual a partir del token
# ------------------------------------------------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> model.Usuario:
    """
    Valida el token JWT y retorna el usuario autenticado.
    Lanza HTTP 401 si el token es inválido o el usuario no existe.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type", "access")
        if username is None or token_type != "access":
            raise credentials_exception
        token_data = schemas.TokenData(nombre_usuario=username)
    except JWTError:
        raise credentials_exception

    user = service.obtener_usuario_por_nombre(db, username=token_data.nombre_usuario)
    if user is None or not user.activo:
        raise credentials_exception
    return user

# ------------------------------------------------------------
# Endpoints públicos
# ------------------------------------------------------------
@router.post("/register", response_model=schemas.UsuarioResponse, status_code=201)
def register(user: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    """Registra un nuevo usuario. (No lo usarás mucho porque ya tienes usuarios)"""
    try:
        return service.crear_usuario(db, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Autentica al usuario con nombre_usuario y password.
    Retorna un token JWT y un refresh token.
    """
    user = service.autenticar_usuario(db, form_data.username, form_data.password)
    if not user:
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
    service.actualizar_ultimo_acceso(db, user.id)
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": refresh_token}

@router.post("/refresh", response_model=schemas.Token)
def refresh_token(
    payload_in: schemas.RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Recibe un refresh token y retorna nuevos access y refresh tokens.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar el refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(payload_in.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type")
        if username is None or token_type != "refresh":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = service.obtener_usuario_por_nombre(db, username=username)
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
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": new_refresh_token}

# ------------------------------------------------------------
# Endpoint protegido (requiere token)
# ------------------------------------------------------------
@router.get("/me", response_model=schemas.UsuarioResponse)
def read_users_me(current_user: model.Usuario = Depends(get_current_user)):
    return current_user

from app.modules.catalogos.model import Rol
from app.modules.catalogos.schemas import RolResponse
from typing import List

@router.get("/roles", response_model=List[RolResponse])
def listar_roles(
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user)
):
    """Lista todos los roles disponibles."""
    return db.query(Rol).all()

@router.post("/usuario/{usuario_id}/roles/{rol_id}", response_model=schemas.UsuarioResponse)
def asignar_rol_usuario(
    usuario_id: int,
    rol_id: int,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user)
):
    """Asigna un rol a un usuario."""
    user_roles = [r.nombre for r in usuario_actual.roles]
    if "Dueño" not in user_roles and "Administrador" not in user_roles:
        raise HTTPException(status_code=403, detail="No tienes permisos para modificar roles")

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
    usuario_actual: model.Usuario = Depends(get_current_user)
):
    """Remueve un rol de un usuario."""
    user_roles = [r.nombre for r in usuario_actual.roles]
    if "Dueño" not in user_roles and "Administrador" not in user_roles:
        raise HTTPException(status_code=403, detail="No tienes permisos para modificar roles")

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
    usuario_actual: model.Usuario = Depends(get_current_user)
):
    """Lista todos los usuarios (solo administradores)."""
    user_roles = [r.nombre for r in usuario_actual.roles]
    if "Dueño" not in user_roles and "Administrador" not in user_roles:
        raise HTTPException(status_code=403, detail="No tienes permisos para listar usuarios")
    return db.query(model.Usuario).order_by(model.Usuario.id).all()

@router.put("/users/{usuario_id}/status", response_model=schemas.UsuarioResponse)
def actualizar_estado_usuario(
    usuario_id: int,
    activo: bool,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user)
):
    """Activa o desactiva un usuario (solo administradores)."""
    user_roles = [r.nombre for r in usuario_actual.roles]
    if "Dueño" not in user_roles and "Administrador" not in user_roles:
        raise HTTPException(status_code=403, detail="No tienes permisos para modificar el estado de usuarios")
    
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
    usuario_actual: model.Usuario = Depends(get_current_user)
):
    """Crea un nuevo usuario directamente (solo administradores)."""
    user_roles = [r.nombre for r in usuario_actual.roles]
    if "Dueño" not in user_roles and "Administrador" not in user_roles:
        raise HTTPException(status_code=403, detail="No tienes permisos para crear usuarios")
    
    try:
        return service.crear_usuario(db, user_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/users/{usuario_id}", status_code=204)
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_actual: model.Usuario = Depends(get_current_user)
):
    """Elimina un usuario (solo administradores)."""
    user_roles = [r.nombre for r in usuario_actual.roles]
    if "Dueño" not in user_roles and "Administrador" not in user_roles:
        raise HTTPException(status_code=403, detail="No tienes permisos para eliminar usuarios")
        
    if usuario_id == usuario_actual.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    
    user = db.query(model.Usuario).filter(model.Usuario.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    db.delete(user)
    db.commit()
    return None