from pydantic import BaseModel, Field, model_validator
from datetime import date, datetime
from typing import List, Optional
from app.modules.clients.schemas import ClientResponse
from app.modules.productos.schemas import ProductoResponse, MaterialResponse
from app.modules.quotes.schemas import (
    CotizacionResponse,
    PiezaJuegoBase,
    PiezaJuegoCreate,
    validar_piezas_juego,
)


class DetallePedidoPiezaResponse(PiezaJuegoBase):
    id: int
    detalle_pedido_id: int
    orden: int

    class Config:
        from_attributes = True


class DetallePedidoPiezaListaResponse(BaseModel):
    """Pieza para los listados: sin la foto (data URL) para no inflar el JSON."""
    id: int
    detalle_pedido_id: int
    nombre: str
    cantidad: float
    notas: Optional[str] = None
    orden: int

    class Config:
        from_attributes = True

class DetallePedidoBase(BaseModel):
    producto_id: Optional[int] = None
    material_id: Optional[int] = None
    tipo_item: str = Field("FABRICADO", pattern=r"^(FABRICADO|REVENTA|INSUMO|REPARACION|SERVICIO)$")
    cantidad: float = Field(gt=0)
    precio: float = Field(ge=0)
    # Unidad vendida vs. unidad de inventario (insumos). La conversión la
    # calcula el backend al convertir la cotización; el campo es opcional para
    # pedidos creados por otras vías.
    unidad_captura: Optional[str] = Field(None, pattern=r"^(M|CM)$")
    cantidad_base: Optional[float] = Field(None, gt=0)
    costo_unitario: Optional[float] = Field(None, ge=0)
    porcentaje_ganancia: Optional[float] = None
    alto: Optional[float] = Field(None, ge=0)
    ancho: Optional[float] = Field(None, ge=0)
    largo: Optional[float] = Field(None, ge=0)
    color: Optional[str] = None
    acabado: Optional[str] = None
    descripcion_especifica: Optional[str] = None
    observaciones: Optional[str] = None
    es_obsequio: bool = False

class DetallePedidoCreate(DetallePedidoBase):
    # Piezas del juego (opcional). Se copian de la cotización o se envían en la
    # conversión; cada una genera su propia orden de producción. None = no se
    # enviaron; [] = explícitamente sin piezas (permite dividir un juego).
    piezas: Optional[List[PiezaJuegoCreate]] = None

    @model_validator(mode="after")
    def _validate_item(self):
        validar_piezas_juego(self.piezas or [], self.tipo_item)
        # La validación de integridad vive SOLO en el Create: el Response
        # también debe poder serializar pedidos 100% personalizados
        # (producto_id NULL, p. ej. notas de entrega históricas o muebles a
        # medida), que la BD sí permite. Mismo patrón que Cotizaciones.
        if self.tipo_item == "INSUMO":
            if not self.material_id:
                raise ValueError("material_id es requerido para tipo_item INSUMO")
            if self.producto_id:
                raise ValueError("producto_id no debe enviarse para tipo_item INSUMO")
        elif self.tipo_item in ("REPARACION", "SERVICIO"):
            if self.producto_id:
                raise ValueError("producto_id no debe enviarse para tipo_item REPARACION/SERVICIO")
            if self.material_id:
                raise ValueError("material_id no debe enviarse para tipo_item REPARACION/SERVICIO")
            if not (self.descripcion_especifica or self.observaciones):
                raise ValueError("La descripción es obligatoria para tipo_item REPARACION/SERVICIO")
        elif self.tipo_item == "FABRICADO":
            # Mueble a la medida: sin producto, descrito en descripcion_especifica.
            if not self.producto_id and not (self.descripcion_especifica or self.observaciones):
                raise ValueError(
                    "producto_id es requerido para tipo_item FABRICADO "
                    "(o describe el mueble a medida en descripcion_especifica)"
                )
        else:
            if not self.producto_id:
                raise ValueError("producto_id es requerido para tipo_item REVENTA")
        return self

class DetallePedidoResponse(DetallePedidoBase):
    id: int
    pedido_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    producto: Optional[ProductoResponse] = None
    material: Optional[MaterialResponse] = None
    piezas: List[DetallePedidoPiezaResponse] = []

    class Config:
        from_attributes = True


class DetallePedidoListaResponse(DetallePedidoBase):
    """Renglón de los listados: piezas sin foto."""
    id: int
    pedido_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    producto: Optional[ProductoResponse] = None
    material: Optional[MaterialResponse] = None
    piezas: List[DetallePedidoPiezaListaResponse] = []

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


class EntregaResumen(BaseModel):
    """Progreso de entrega de un pedido (unidades físicas/piezas)."""

    total: float = 0
    entregado: float = 0
    pendiente: float = 0
    estado: str = "PENDIENTE"  # PENDIENTE | PARCIAL | COMPLETO
    envios: int = 0
    ultima_entrega: Optional[datetime] = None


class PedidoConEntregasResponse(PedidoResponse):
    """Pedido con el resumen de entregas (lista y detalle de Pedidos)."""

    entrega_resumen: Optional[EntregaResumen] = None


class PedidoListaConEntregasResponse(PedidoConEntregasResponse):
    """Listado de pedidos: mismo contrato sin las fotos de las piezas."""
    detalles: List[DetallePedidoListaResponse] = []

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
    # Fecha del abono inicial (YYYY-MM-DD): a veces el cliente abonó ANTES de
    # convertir. Si se omite, se usa HOY en hora Venezuela.
    fecha_adelanto: Optional[date] = None


class RentabilidadPieza(BaseModel):
    """Costo real de UNA orden interna (pieza de un juego o mueble suelto).

    Sin precio propio: el precio es del renglón completo, así que aquí solo
    se publica el costo para que el negocio vea en qué se fue el dinero.
    """

    orden_id: int
    detalle_pedido_id: Optional[int] = None
    pieza_nombre: Optional[str] = None
    producto_nombre: Optional[str] = None
    cantidad: Optional[float] = None
    estado: str
    # Costo real en COP (misma base interna que el resto del costo real).
    costo_real: float = 0.0


class RentabilidadPedidoResponse(BaseModel):
    """Compara el costo ESTIMADO (de la cotización) con el costo REAL (producción
    + flete) de un pedido, para conocer el margen real.

    Monedas:
    - `total_cobrado` y los campos `*_moneda` van en la moneda del pedido
      (la de la cotización/venta), que es como el cliente ve el precio.
    - Los campos `*_base` y `margen_*` van en COP (compatibilidad y control
      interno). El frontend prioriza la moneda original del pedido.
    """

    pedido_id: int
    moneda_id: int
    moneda_codigo: Optional[str] = None
    moneda_simbolo: Optional[str] = None
    # Tasa congelada de la venta: COP por 1 unidad de la moneda del pedido.
    tasa_cambio: float = 1.0
    total_cobrado: float = 0.0
    total_cobrado_base: float = 0.0
    costo_estimado_produccion: float = 0.0
    costo_real_produccion: float = 0.0
    diferencia_costo: float = 0.0
    flete_cobrado_base: float = 0.0
    flete_real_base: float = 0.0
    margen_estimado: float = 0.0
    margen_real: float = 0.0
    # Mismos conceptos convertidos a la moneda original del pedido.
    costo_estimado_moneda: float = 0.0
    costo_real_moneda: float = 0.0
    flete_real_moneda: float = 0.0
    margen_estimado_moneda: float = 0.0
    margen_real_moneda: float = 0.0
    diferencia_costo_moneda: float = 0.0
    tiene_produccion: bool = False
    # Desglose interno por pieza/orden (juegos con precio global).
    por_pieza: List[RentabilidadPieza] = []
