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
    totp_habilitado: bool = False
    created_at: datetime
    roles: List[RolResponse] = []

    class Config:
        from_attributes = True   # Permite convertir el modelo SQLAlchemy a este esquema

class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None
    # Último acceso ANTES de este login (para saludar/avisar en la UI).
    ultimo_acceso_previo: Optional[datetime] = None

class SesionResponse(BaseModel):
    id: int
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    revocada: bool
    creado_en: datetime
    ultimo_uso: datetime
    actual: bool = False

class CambioPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8, max_length=128)

# ------------------------------------------------------------
# 2FA con app (TOTP)
# ------------------------------------------------------------
class Codigo2FARequest(BaseModel):
    codigo: str = Field(min_length=4, max_length=16)

class Verificar2FARequest(BaseModel):
    ticket: str
    codigo: str = Field(min_length=4, max_length=16)
    recordar_equipo: bool = False

# ------------------------------------------------------------
# Huella / passkeys (WebAuthn)
# ------------------------------------------------------------
class UsuarioHuellaRequest(BaseModel):
    # Opcional: si viene vacío se hace login sin usuario (passkey
    # discoverable: el navegador ofrece las cuentas de este equipo).
    nombre_usuario: Optional[str] = None

class RegistroHuellaRequest(BaseModel):
    dispositivo: Optional[str] = None
    respuesta: dict

class LoginHuellaRequest(BaseModel):
    # Híbrido: con nombre_usuario se usa el flujo filtrado clásico;
    # sin él se descubre el usuario por la credencial + sesion_huella.
    nombre_usuario: Optional[str] = None
    respuesta: dict
    sesion_huella: Optional[str] = None

class HuellaResponse(BaseModel):
    id: int
    dispositivo: Optional[str] = None
    creado_en: datetime
    ultimo_uso: Optional[datetime] = None

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
