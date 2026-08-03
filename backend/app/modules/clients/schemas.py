from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional

class ClientBase(BaseModel):
    nombre: str
    telefono: str
    direccion: Optional[str] = None
    email: Optional[str] = None
    ciudad: Optional[str] = None
    estado: Optional[str] = None
    observaciones: Optional[str] = None
    fecha_registro: Optional[date] = None

class ClientCreate(ClientBase):
    pass

class ClientUpdate(BaseModel):
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    email: Optional[str] = None
    ciudad: Optional[str] = None
    estado: Optional[str] = None
    observaciones: Optional[str] = None

class ClientResponse(ClientBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True