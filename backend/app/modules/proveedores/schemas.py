from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class ProveedorBase(BaseModel):
    nombre: str
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    direccion: Optional[str] = None

class ProveedorCreate(ProveedorBase):
    pass

class ProveedorUpdate(BaseModel):
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    direccion: Optional[str] = None

class ProveedorResponse(ProveedorBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Salida en str: la columna es String(150) sin restricción y datos legacy
    # (o migraciones) con email inválido reventarían EmailStr → ResponseValidationError 500.
    email: Optional[str] = None

    class Config:
        from_attributes = True
