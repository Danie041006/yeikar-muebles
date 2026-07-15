from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional
from decimal import Decimal

class GastoBase(BaseModel):
    tipo_gasto_id: int
    moneda_id: int
    fecha: date
    descripcion: Optional[str] = None
    monto: Decimal = Field(..., gt=0)
    observaciones: Optional[str] = None

class GastoCreate(GastoBase):
    pass

class GastoUpdate(BaseModel):
    tipo_gasto_id: Optional[int] = None
    moneda_id: Optional[int] = None
    fecha: Optional[date] = None
    descripcion: Optional[str] = None
    monto: Optional[Decimal] = Field(None, gt=0)
    observaciones: Optional[str] = None

class GastoResponse(GastoBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True