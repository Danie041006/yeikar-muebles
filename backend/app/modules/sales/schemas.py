from pydantic import BaseModel, Field, model_validator
from datetime import date, datetime
from typing import List, Optional
from app.modules.clients.schemas import ClientResponse
from app.modules.catalogos.schemas import MonedaResponse
from app.modules.productos.schemas import ProductoResponse, MaterialResponse
from app.modules.adjuntos.schemas import AdjuntoInfo

# ------------------------------------------------------------
# Detalle Venta
# ------------------------------------------------------------
class DetalleVentaBase(BaseModel):
    cantidad: float = Field(..., gt=0)
    precio: float = Field(..., ge=0)

class DetalleVentaCreate(DetalleVentaBase):
    venta_id: int
    producto_id: Optional[int] = None
    material_id: Optional[int] = None
    tipo_item: str = Field("FABRICADO", pattern=r"^(FABRICADO|REVENTA|INSUMO)$")
    costo_unitario: Optional[float] = None
    porcentaje_ganancia: Optional[float] = None
    descuento: Optional[float] = 0.0
    descripcion_especifica: Optional[str] = None

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

class DetalleVentaResponse(DetalleVentaBase):
    id: int
    venta_id: int
    producto_id: Optional[int] = None
    material_id: Optional[int] = None
    tipo_item: str = "FABRICADO"
    costo_unitario: Optional[float] = None
    porcentaje_ganancia: Optional[float] = None
    utilidad: Optional[float] = None
    descuento: Optional[float] = None
    descripcion_especifica: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    producto: Optional[ProductoResponse] = None
    material: Optional[MaterialResponse] = None

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
    # Comprobantes digitales del pago (adjuntos tipo PAGO)
    recibos: List[AdjuntoInfo] = []

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Descuento de cobro (rebaja que resta del saldo sin mover caja)
# ------------------------------------------------------------
class DescuentoBase(BaseModel):
    fecha: datetime
    monto: float = Field(..., gt=0)
    motivo: Optional[str] = None
    observaciones: Optional[str] = None

class DescuentoCreate(DescuentoBase):
    venta_id: int
    moneda_id: int
    # Tasa de cambio respecto a la moneda de la venta.
    # Debe indicarse cuando la moneda del descuento difiere de la moneda de la venta
    # (misma regla que en PagoCreate). Si coinciden, se puede omitir (se asume 1.0).
    tasa_cambio: Optional[float] = Field(None, gt=0, description="TRM/tasa de conversión. Requerido si moneda_id difiere de la moneda de la venta.")

class DescuentoResponse(DescuentoBase):
    id: int
    venta_id: int
    moneda_id: int
    tasa_cambio: float
    monto_en_moneda_base: float
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
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
    creado_por_id: Optional[int] = None
    actualizado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    cliente: Optional[ClientResponse] = None
    moneda: Optional[MonedaResponse] = None
    # Estado del pedido vinculado (ENTREGADO = ya despachado): la UI de
    # "Cuentas por cobrar" separa entregados de en-proceso con este campo.
    pedido_estado: Optional[str] = None

    class Config:
        from_attributes = True

class VentaDetalleResponse(VentaResponse):
    detalles: List[DetalleVentaResponse] = []
    pagos: List[PagoResponse] = []
    descuentos: List[DescuentoResponse] = []
    total_pagado: float = 0.0
    total_descontado: float = 0.0
    saldo_pendiente: float = 0.0


# ------------------------------------------------------------
# Cuentas por Cobrar
# ------------------------------------------------------------
class CuentaPorCobrarResponse(BaseModel):
    venta_id: int
    pedido_id: int
    cliente_nombre: str
    fecha: date
    total: float
    total_pagado: float
    total_descontado: float = 0.0
    saldo_pendiente: float
    moneda_codigo: str
    pedido_estado: Optional[str] = None

    class Config:
        from_attributes = True
