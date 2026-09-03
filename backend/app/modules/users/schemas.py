from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

class UsuarioBase(BaseModel):
    nombre_usuario: str
    nombre: Optional[str] = None   # Nombre visible (saludos en la UI)
    email: Optional[EmailStr] = None   # EmailStr valida formato

class UsuarioCreate(UsuarioBase):
    password: str = Field(min_length=8, max_length=128)

class UsuarioLogin(BaseModel):
    nombre_usuario: str
    password: str

from typing import List
from app.modules.catalogos.schemas import RolResponse

class UsuarioResponse(UsuarioBase):
    id: int
    empleado_id: Optional[int] = None
    activo: bool
    ultimo_acceso: Optional[datetime] = None
    created_at: datetime
    roles: List[RolResponse] = []

    class Config:
        from_attributes = True   # Permite convertir el modelo SQLAlchemy a este esquema

class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None

class TokenData(BaseModel):
    nombre_usuario: Optional[str] = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str

# ------------------------------------------------------------
# Permisos por módulo
# ------------------------------------------------------------
class ModuloAcceso(BaseModel):
    modulo: str
    gestionar: bool = False

class ModulosCatalogo(BaseModel):
    clave: str
    nombre: str
    descripcion: Optional[str] = None

class RolPermisosUpdate(BaseModel):
    permisos: List[ModuloAcceso]

class MeResponse(UsuarioResponse):
    modulos: List[ModuloAcceso] = []
