from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal

from app.modules.catalogos.schemas import MonedaResponse, TipoGastoResponse
from app.modules.proveedores.schemas import ProveedorResponse


class AbonoBase(BaseModel):
    fecha: date
    # Monto del abono EN LA MONEDA DE LA DEUDA.
    monto: Decimal = Field(..., gt=0)
    metodo_caja_id: int
    # Tasa "1 [moneda de la cuenta] = X COP" (obligatoria si la cuenta no es COP).
    tasa_cambio: Optional[Decimal] = Field(None, gt=0)


class AbonoCreate(AbonoBase):
    pass


class AbonoResponse(AbonoBase):
    id: int
    tasa_cambio: Decimal = Decimal("1.0")
    monto_en_moneda_base: Decimal
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    metodo_caja_nombre: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DetalleCuentaPorPagarCreate(BaseModel):
    # Renglón de la deuda: qué se compró, a cuánto, y para quién.
    descripcion: Optional[str] = None
    material_id: Optional[int] = None
    cantidad: Decimal = Field(1, gt=0)
    precio_unitario: Decimal = Field(0, ge=0)
    cliente_nombre: Optional[str] = None
    cliente_id: Optional[int] = None
    observaciones: Optional[str] = None


class DetalleCuentaPorPagarResponse(DetalleCuentaPorPagarCreate):
    id: int
    orden: int
    total: Decimal

    class Config:
        from_attributes = True


class CuentaPorPagarBase(BaseModel):
    proveedor_id: int
    tipo_gasto_id: int
    moneda_id: int = 1
    fecha: date
    descripcion: Optional[str] = None
    monto: Decimal = Field(..., gt=0)
    tasa_cambio: Optional[Decimal] = Field(None, gt=0)


class CuentaPorPagarCreate(CuentaPorPagarBase):
    # Renglones que componen la deuda. Si se envían, el monto debe ser la
    # suma de los renglones (se valida en el servicio).
    detalles: Optional[List[DetalleCuentaPorPagarCreate]] = None


class CuentaPorPagarResponse(CuentaPorPagarBase):
    id: int
    gasto_id: Optional[int] = None
    monto_en_moneda_base: Decimal
    monto_pagado: Decimal
    saldo: Decimal
    estado: str
    origen_tipo: Optional[str] = None
    origen_id: Optional[int] = None
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    proveedor: Optional[ProveedorResponse] = None
    moneda: Optional[MonedaResponse] = None
    tipo_gasto: Optional[TipoGastoResponse] = None
    detalles: List[DetalleCuentaPorPagarResponse] = []
    pagos: List[AbonoResponse] = []

    class Config:
        from_attributes = True


class LineaSaldoProveedor(BaseModel):
    proveedor_id: int
    proveedor_nombre: str
    saldo: Decimal


class ResumenCuentasPorPagar(BaseModel):
    total_pendiente: Decimal
    total_pagado: Decimal
    total_deudas: int
    por_proveedor: List[LineaSaldoProveedor]