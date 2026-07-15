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

class DetalleVentaResponse(DetalleVentaBase):
    id: int
    venta_id: int
    producto_id: int
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

class PagoResponse(PagoBase):
    id: int
    venta_id: int
    moneda_id: int
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
    moneda_id: int
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
