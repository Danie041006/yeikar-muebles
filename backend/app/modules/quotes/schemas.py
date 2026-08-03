from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List, Any
from app.modules.clients.schemas import ClientResponse
from app.modules.catalogos.schemas import MonedaResponse

class DetalleCotizacionBase(BaseModel):
    producto_id: int
    cantidad: float
    precio: float
    alto: Optional[float] = None
    ancho: Optional[float] = None
    largo: Optional[float] = None
    observaciones: Optional[str] = None
    costo_materiales: Optional[float] = None
    costo_mano_obra: Optional[float] = None
    costo_gastos: Optional[float] = None
    costo_total: Optional[float] = None
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
    total_estimado: float
    moneda_id: int = 1
    tasa_cambio: float = 1.0
    total_en_moneda_base: Optional[float] = None
    observaciones: Optional[str] = None

class CotizacionCreate(CotizacionBase):
    cliente_id: int
    detalles: List[DetalleCotizacionCreate] = []

class CotizacionUpdate(BaseModel):
    cliente_id: Optional[int] = None
    fecha: Optional[date] = None
    estado: Optional[str] = None
    total_estimado: Optional[float] = None
    moneda_id: Optional[int] = None
    tasa_cambio: Optional[float] = None
    total_en_moneda_base: Optional[float] = None
    observaciones: Optional[str] = None

class CotizacionResponse(CotizacionBase):
    id: int
    cliente_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    cliente: Optional[ClientResponse] = None
    moneda: Optional[MonedaResponse] = None
    detalles: List[DetalleCotizacionResponse] = []

    class Config:
        from_attributes = True
