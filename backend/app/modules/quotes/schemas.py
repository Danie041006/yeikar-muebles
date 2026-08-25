from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List, Any
from app.modules.clients.schemas import ClientResponse
from app.modules.catalogos.schemas import MonedaResponse

class DetalleCotizacionBase(BaseModel):
    producto_id: int
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
    pass

class DetalleCotizacionResponse(DetalleCotizacionBase):
    id: int
    cotizacion_id: int

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

    class Config:
        from_attributes = True
