from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.catalogos.schemas import MonedaResponse


class AplicarSaldoCreate(BaseModel):
    venta_id: int
    saldo_favor_id: int
    monto: Decimal = Field(..., gt=0, max_digits=15, decimal_places=2)
    tasa_cambio: Decimal | None = Field(None, gt=0, allow_inf_nan=False)
    fecha: datetime | None = None
    operacion_id: UUID


class SaldoFavorResponse(BaseModel):
    id: int
    cliente_id: int
    cliente_nombre: str
    moneda_id: int
    moneda: MonedaResponse
    pago_origen_id: int | None
    monto: Decimal
    monto_usado: Decimal
    saldo: Decimal
    referencia: str
    created_at: datetime
    creador_nombre: str | None

    class Config:
        from_attributes = True
