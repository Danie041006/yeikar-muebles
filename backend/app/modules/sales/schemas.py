from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import List, Optional
from app.modules.clients.schemas import ClientResponse
from app.modules.catalogos.schemas import MonedaResponse
from app.modules.productos.schemas import ProductoResponse

# ------------------------------------------------------------
# Detalle Venta
# ------------------------------------------------------------
class DetalleVentaBase(BaseModel):
    cantidad: float = Field(..., gt=0)
    precio: float = Field(..., ge=0)

class DetalleVentaCreate(DetalleVentaBase):
    venta_id: int
    producto_id: int
    costo_unitario: Optional[float] = None
    porcentaje_ganancia: Optional[float] = None
    descuento: Optional[float] = 0.0

class DetalleVentaResponse(DetalleVentaBase):
    id: int
    venta_id: int
    producto_id: int
    costo_unitario: Optional[float] = None
    porcentaje_ganancia: Optional[float] = None
    utilidad: Optional[float] = None
    descuento: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    producto: Optional[ProductoResponse] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Pago (Abono)
# ------------------------------------------------------------
class PagoBase(BaseModel):
    fecha: datetime
    monto: float = Field(..., gt=0)
    metodo_pago: str  
    referencia: Optional[str] = None
    observaciones: Optional[str] = None

class PagoCreate(PagoBase):
    venta_id: int
    moneda_id: int
    # Tasa de cambio respecto a la moneda base de la venta.
    # Debe indicarse cuando la moneda del pago difiere de la moneda de la venta.
    # Ej: si la venta es en COP y el pago es en USD, tasa_cambio = TRM del día (ej: 4200.0)
    # Si las monedas coinciden, se puede omitir (se asume 1.0).
    tasa_cambio: Optional[float] = Field(None, gt=0, description="TRM/tasa de conversión. Requerido si moneda_id difiere de la moneda de la venta.")

class PagoResponse(PagoBase):
    id: int
    venta_id: int
    moneda_id: int
    tasa_cambio: float
    monto_en_moneda_base: float
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    moneda: Optional[MonedaResponse] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Venta (Factura)
# ------------------------------------------------------------
class VentaBase(BaseModel):
    fecha: date
    observaciones: Optional[str] = None

class VentaCreate(BaseModel):
    pedido_id: int
    # Si no se indica, se usa la moneda de la cotización que originó el pedido.
    moneda_id: Optional[int] = None
    fecha: Optional[date] = None
    observaciones: Optional[str] = None

class VentaUpdate(BaseModel):
    estado: Optional[str] = None
    observaciones: Optional[str] = None

class VentaResponse(VentaBase):
    id: int
    pedido_id: int
    cliente_id: int
    moneda_id: int
    total: float
    estado: str  # PENDIENTE, ABONADA, PAGADA, CANCELADA
    tasa_cambio: float
    total_en_moneda_base: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    cliente: Optional[ClientResponse] = None
    moneda: Optional[MonedaResponse] = None

    class Config:
        from_attributes = True

class VentaDetalleResponse(VentaResponse):
    detalles: List[DetalleVentaResponse] = []
    pagos: List[PagoResponse] = []
    total_pagado: float = 0.0
    saldo_pendiente: float = 0.0


# ------------------------------------------------------------
# Cuentas por Cobrar
# ------------------------------------------------------------
class CuentaPorCobrarResponse(BaseModel):
    venta_id: int
    cliente_nombre: str
    fecha: date
    total: float
    total_pagado: float
    saldo_pendiente: float
    moneda_codigo: str

    class Config:
        from_attributes = True
