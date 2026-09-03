from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import List, Optional

from app.modules.clients.schemas import ClientResponse
from app.modules.productos.schemas import ProductoResponse, MaterialResponse


# ------------------------------------------------------------
# Detalle Factura
# ------------------------------------------------------------
class DetalleFacturaCreate(BaseModel):
    # Identifica la línea concreta del pedido (detalle_pedido.id), no el producto:
    # un pedido puede tener varias líneas del mismo producto y se facturan por separado.
    detalle_pedido_id: int
    # Monto en USD decidido por la dueña para esta línea del pedido.
    precio_usd: float = Field(..., gt=0)

class DetalleFacturaResponse(BaseModel):
    id: int
    factura_id: int
    tipo_item: str = "FABRICADO"
    producto_id: Optional[int] = None
    material_id: Optional[int] = None
    descripcion: Optional[str] = None
    cantidad: float
    precio_usd: float
    subtotal_usd: float
    subtotal_bs: float
    producto: Optional[ProductoResponse] = None
    material: Optional[MaterialResponse] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Factura
# ------------------------------------------------------------
class FacturaCreate(BaseModel):
    pedido_id: int
    # 1 USD = X Bs.
    tasa_usd_ves: float = Field(..., gt=0)
    fecha_emision: Optional[date] = None
    # Debe cubrir todos los productos del pedido (cantidad fija del pedido).
    lineas: List[DetalleFacturaCreate] = Field(..., min_length=1)
    observaciones: Optional[str] = None
    # True = el Dueño/Administrador autoriza emitir aunque el pedido tenga saldo
    # pendiente (decisión caso a caso al emitir, sin bandera permanente en el cliente).
    permitir_saldo_pendiente: bool = False

class FacturaResponse(BaseModel):
    id: int
    pedido_id: int
    cliente_id: int
    fecha_emision: date
    total_usd: float
    tasa_usd_ves: float
    base_imponible_bs: float
    iva_bs: float
    igtf_bs: float
    total_bs: float
    estado: str  # EMITIDA, ANULADA
    observaciones: Optional[str] = None
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    cliente: Optional[ClientResponse] = None

    class Config:
        from_attributes = True

class FacturaDetalleResponse(FacturaResponse):
    detalles: List[DetalleFacturaResponse] = []


# ------------------------------------------------------------
# Pedidos facturables (venta sin factura; puede tener saldo pendiente)
# ------------------------------------------------------------
class LineaPedidoFacturable(BaseModel):
    # Id de la línea del pedido (detalle_pedido.id) — único por línea, aún si hay
    # varios detalles con el mismo producto.
    detalle_pedido_id: int
    nombre: str
    cantidad: float
    # Precio original del pedido (moneda de la cotización) — solo como referencia.
    precio_referencia: float
    moneda_codigo: Optional[str] = None

class PedidoFacturableResponse(BaseModel):
    pedido_id: int
    cliente_id: int
    cliente_nombre: str
    fecha: date
    estado: str
    venta_id: int
    total_venta: float
    total_pagado: float
    saldo_pendiente: float
    venta_estado: str  # PENDIENTE, ABONADA, PAGADA (CANCELADA nunca es facturable)
    venta_moneda_codigo: Optional[str] = None
    lineas: List[LineaPedidoFacturable]


# ------------------------------------------------------------
# Tasas de impuestos (configurables)
# ------------------------------------------------------------
class TasaImpuestoResponse(BaseModel):
    clave: str
    nombre: str
    tasa: float
    vigente: bool

    class Config:
        from_attributes = True

class TasaImpuestoUpdate(BaseModel):
    tasa: float = Field(..., gt=0)
