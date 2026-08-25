from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from decimal import Decimal

from app.modules.catalogos.schemas import AreaResponse


class PrecioProduccionBase(BaseModel):
    area_id: int
    descripcion: str = Field(..., max_length=200)
    producto_id: Optional[int] = None
    precio: Decimal = Field(..., ge=0)
    activo: bool = True
    orden: int = 0

class PrecioProduccionCreate(PrecioProduccionBase):
    pass

class PrecioProduccionUpdate(BaseModel):
    area_id: Optional[int] = None
    descripcion: Optional[str] = Field(None, max_length=200)
    producto_id: Optional[int] = None
    precio: Optional[Decimal] = Field(None, ge=0)
    activo: Optional[bool] = None
    orden: Optional[int] = None

class PrecioProduccionResponse(PrecioProduccionBase):
    id: int
    area: Optional[AreaResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
