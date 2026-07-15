from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.modules.catalogos.schemas import CargoResponse

class EmpleadoBase(BaseModel):
    nombre: str
    cargo_id: int
    telefono: Optional[str] = None
    activo: Optional[bool] = True

class EmpleadoCreate(EmpleadoBase):
    pass

class EmpleadoUpdate(BaseModel):
    nombre: Optional[str] = None
    cargo_id: Optional[int] = None
    telefono: Optional[str] = None
    activo: Optional[bool] = None

class EmpleadoResponse(EmpleadoBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    cargo: Optional[CargoResponse] = None

    class Config:
        from_attributes = True
