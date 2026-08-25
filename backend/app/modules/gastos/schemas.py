from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal

from app.modules.catalogos.schemas import TipoGastoResponse, MonedaResponse, AreaResponse
from app.modules.adjuntos.schemas import AdjuntoInfo

class GastoBase(BaseModel):
    tipo_gasto_id: int
    moneda_id: int
    fecha: date
    descripcion: Optional[str] = None
    monto: Decimal = Field(..., gt=0)
    tasa_cambio: Decimal = Field(default=Decimal("1.0"), gt=0)
    # Área/departamento al que se imputa el gasto (opcional).
    area_id: Optional[int] = None
    # Método de caja del egreso (id de MetodoCaja). Si se indica, el gasto
    # descuenta esa cuenta al crearse (el efectivo "sale" de verdad).
    metodo_caja_id: Optional[int] = None
    observaciones: Optional[str] = None

class GastoCreate(GastoBase):
    # None → se resuelve la tasa vigente (o 1.0 si es COP) en el servicio.
    tasa_cambio: Optional[Decimal] = Field(None, gt=0)

class GastoUpdate(BaseModel):
    tipo_gasto_id: Optional[int] = None
    moneda_id: Optional[int] = None
    fecha: Optional[date] = None
    descripcion: Optional[str] = None
    monto: Optional[Decimal] = Field(None, gt=0)
    tasa_cambio: Optional[Decimal] = Field(None, gt=0)
    area_id: Optional[int] = None
    metodo_caja_id: Optional[int] = None
    observaciones: Optional[str] = None

class GastoResponse(GastoBase):
    id: int
    monto_en_moneda_base: Decimal
    tipo_gasto: Optional[TipoGastoResponse] = None
    moneda: Optional[MonedaResponse] = None
    area: Optional[AreaResponse] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    creado_por_id: Optional[int] = None
    actualizado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    # Cuenta de caja del egreso (se resuelve desde su movimiento de caja).
    metodo_caja_nombre: Optional[str] = None
    # Comprobantes digitales del egreso (adjuntos tipo GASTO)
    comprobantes: List[AdjuntoInfo] = []

    class Config:
        from_attributes = True
