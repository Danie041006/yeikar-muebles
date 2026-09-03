from pydantic import BaseModel, Field, model_validator
from datetime import date, datetime
from typing import Optional, List, Any
from app.modules.clients.schemas import ClientResponse
from app.modules.catalogos.schemas import MonedaResponse
from app.modules.productos.schemas import MaterialResponse

class ClienteRapidoCreate(BaseModel):
    """Alta mínima de cliente desde el flujo de cotización: solo lo necesario
    para cotizar. El resto del perfil se completa desde el módulo Clientes."""

    nombre: str = Field(min_length=1, max_length=150)
    telefono: str = Field(min_length=1, max_length=50)
    cedula: Optional[str] = Field(None, max_length=30)


class ClienteRapidoResponse(BaseModel):
    id: int
    nombre: str
    telefono: str


class DetalleCotizacionBase(BaseModel):
    producto_id: Optional[int] = None
    material_id: Optional[int] = None
    tipo_item: str = Field("FABRICADO", pattern=r"^(FABRICADO|REVENTA|INSUMO)$")
    cantidad: float = Field(gt=0)
    precio: float = Field(ge=0)
    alto: Optional[float] = Field(None, ge=0)
    ancho: Optional[float] = Field(None, ge=0)
    largo: Optional[float] = Field(None, ge=0)
    observaciones: Optional[str] = None
    costo_materiales: Optional[float] = Field(None, ge=0)
    costo_mano_obra: Optional[float] = Field(None, ge=0)
    costo_gastos: Optional[float] = Field(None, ge=0)
    costo_total: Optional[float] = Field(None, ge=0)
    receta_personalizada: Optional[Any] = None

class DetalleCotizacionCreate(DetalleCotizacionBase):
    @model_validator(mode="after")
    def _validate_item(self):
        # La validación de integridad vive SOLO en el Create: el Response
        # también debe poder serializar cotizaciones 100% personalizadas
        # (producto_id NULL, p. ej. guardadas desde el Cotizador IA sin
        # producto base), que la BD sí permite.
        if self.tipo_item == "INSUMO":
            if not self.material_id:
                raise ValueError("material_id es requerido para tipo_item INSUMO")
            if self.producto_id:
                raise ValueError("producto_id no debe enviarse para tipo_item INSUMO")
        else:
            if not self.producto_id:
                raise ValueError("producto_id es requerido para tipo_item FABRICADO/REVENTA")
        return self

class DetalleCotizacionResponse(DetalleCotizacionBase):
    id: int
    cotizacion_id: int
    material: Optional[MaterialResponse] = None

    class Config:
        from_attributes = True

class CotizacionBase(BaseModel):
    fecha: date
    estado: str
    total_estimado: float = Field(ge=0)
    moneda_id: int = 1
    tasa_cambio: float = Field(1.0, gt=0)
    total_en_moneda_base: Optional[float] = Field(None, ge=0)
    observaciones: Optional[str] = None

class CotizacionCreate(CotizacionBase):
    cliente_id: int
    detalles: List[DetalleCotizacionCreate] = []

class CotizacionUpdate(BaseModel):
    cliente_id: Optional[int] = None
    fecha: Optional[date] = None
    estado: Optional[str] = None
    total_estimado: Optional[float] = Field(None, ge=0)
    moneda_id: Optional[int] = None
    tasa_cambio: Optional[float] = Field(None, gt=0)
    total_en_moneda_base: Optional[float] = Field(None, ge=0)
    observaciones: Optional[str] = None
    # Reemplazo COMPLETO de los renglones (mismo contrato que al crear): si se
    # envía, la cotización queda exactamente con estos detalles.
    detalles: Optional[List[DetalleCotizacionCreate]] = None

class CotizacionResponse(CotizacionBase):
    id: int
    cliente_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    creado_por_id: Optional[int] = None
    actualizado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    cliente: Optional[ClientResponse] = None
    moneda: Optional[MonedaResponse] = None
    detalles: List[DetalleCotizacionResponse] = []
    # Atributos anotados por el servicio (no son columnas): si la cotización ya
    # fue convertida a pedido, aquí viene el id/estado del pedido para que la UI
    # la distinga y no ofrezca convertirla otra vez.
    pedido_id: Optional[int] = None
    pedido_estado: Optional[str] = None

    class Config:
        from_attributes = True
