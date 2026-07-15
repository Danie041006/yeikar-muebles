from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UsuarioBase(BaseModel):
    nombre_usuario: str
    email: Optional[EmailStr] = None   # EmailStr valida formato

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioLogin(BaseModel):
    nombre_usuario: str
    password: str

from typing import List
from app.modules.catalogos.schemas import RolResponse

class UsuarioResponse(UsuarioBase):
    id: int
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