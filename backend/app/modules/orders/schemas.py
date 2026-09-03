from pydantic import BaseModel, Field, model_validator
from datetime import date, datetime
from typing import List, Optional
from app.modules.clients.schemas import ClientResponse
from app.modules.productos.schemas import ProductoResponse, MaterialResponse
from app.modules.quotes.schemas import CotizacionResponse

class DetallePedidoBase(BaseModel):
    producto_id: Optional[int] = None
    material_id: Optional[int] = None
    tipo_item: str = Field("FABRICADO", pattern=r"^(FABRICADO|REVENTA|INSUMO)$")
    cantidad: float = Field(gt=0)
    precio: float = Field(ge=0)
    costo_unitario: Optional[float] = Field(None, ge=0)
    porcentaje_ganancia: Optional[float] = None
    alto: Optional[float] = Field(None, ge=0)
    ancho: Optional[float] = Field(None, ge=0)
    largo: Optional[float] = Field(None, ge=0)
    color: Optional[str] = None
    acabado: Optional[str] = None
    descripcion_especifica: Optional[str] = None
    observaciones: Optional[str] = None

    @model_validator(mode="after")
    def _validate_item(self):
        if self.tipo_item == "INSUMO":
            if not self.material_id:
                raise ValueError("material_id es requerido para tipo_item INSUMO")
            if self.producto_id:
                raise ValueError("producto_id no debe enviarse para tipo_item INSUMO")
        else:
            if not self.producto_id:
                raise ValueError("producto_id es requerido para tipo_item FABRICADO/REVENTA")
        return self

class DetallePedidoCreate(DetallePedidoBase):
    pass

class DetallePedidoResponse(DetallePedidoBase):
    id: int
    pedido_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    producto: Optional[ProductoResponse] = None
    material: Optional[MaterialResponse] = None

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
    creado_por_id: Optional[int] = None
    actualizado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
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
    # EFECTIVO_COP | EFECTIVO_USD | EFECTIVO_VES | BANCOLOMBIA | BANCARIBE | ZELLE | BINANCE
    metodo_pago: Optional[str] = None
