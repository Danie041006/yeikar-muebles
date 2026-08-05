from pydantic import BaseModel
from datetime import date, datetime
from typing import List, Optional
from app.modules.clients.schemas import ClientResponse
from app.modules.productos.schemas import ProductoResponse
from app.modules.quotes.schemas import CotizacionResponse

class DetallePedidoBase(BaseModel):
    producto_id: int
    cantidad: float
    precio: float
    costo_unitario: Optional[float] = None
    porcentaje_ganancia: Optional[float] = None
    alto: Optional[float] = None
    ancho: Optional[float] = None
    largo: Optional[float] = None
    color: Optional[str] = None
    acabado: Optional[str] = None
    descripcion_especifica: Optional[str] = None
    observaciones: Optional[str] = None

class DetallePedidoCreate(DetallePedidoBase):
    pass

class DetallePedidoResponse(DetallePedidoBase):
    id: int
    pedido_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    producto: Optional[ProductoResponse] = None

    class Config:
        from_attributes = True

class PedidoBase(BaseModel):
    fecha: date
    estado: str
    observaciones: Optional[str] = None
    fecha_entrega_estimada: Optional[date] = None

class PedidoCreate(PedidoBase):
    cotizacion_id: int
    cliente_id: int
    detalles: List[DetallePedidoCreate]

class PedidoUpdate(BaseModel):
    cotizacion_id: Optional[int] = None
    cliente_id: Optional[int] = None
    fecha: Optional[date] = None
    estado: Optional[str] = None
    observaciones: Optional[str] = None
    fecha_entrega_estimada: Optional[date] = None

class PedidoResponse(PedidoBase):
    id: int
    cotizacion_id: int
    cliente_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    cliente: Optional[ClientResponse] = None
    cotizacion: Optional[CotizacionResponse] = None
    detalles: List[DetallePedidoResponse] = []

    class Config:
        from_attributes = True

class ConvertirCotizacionBody(BaseModel):
    detalles: List[DetallePedidoCreate]
    fecha_entrega_estimada: Optional[str] = None
    # Abono inicial (OPCIONAL) al convertir cotización → pedido. Si es 0/None, el pedido
    # se convierte sin abono y la factura queda PENDIENTE.
    adelanto: Optional[float] = None
    # Moneda del adelanto. Por defecto se usa la moneda de la cotización.
    moneda_adelanto_id: Optional[int] = None
    # TRM solo cuando el abono se recibe en una moneda no deducible de la tasa
    # de la cotización (p.ej. VES con factura en USD/COP).
    tasa_cambio_adelanto: Optional[float] = None
    # EFECTIVO_COP | EFECTIVO_USD | EFECTIVO_VES | BANCOLOMBIA | BANCARIBE | ZELLE
    metodo_pago: Optional[str] = None
