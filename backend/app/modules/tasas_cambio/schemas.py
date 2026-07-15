from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

class TasaCambioBase(BaseModel):
    moneda_origen_id: int
    moneda_destino_id: int
    valor: Decimal = Field(..., gt=0)
    fecha: date

class TasaCambioCreate(TasaCambioBase):
    pass

class TasaCambioResponse(TasaCambioBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True