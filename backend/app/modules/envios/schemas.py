from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.modules.orders.schemas import PedidoResponse
from app.modules.empleados.schemas import EmpleadoResponse
class EnvioBase(BaseModel):
    pedido_id: int
    empleado_id: Optional[int] = None
    fecha_salida: Optional[datetime] = None
    fecha_entrega: Optional[datetime] = None
    estado: str  # 'PREPARADO', 'EN_TRANSITO', 'ENTREGADO', 'FALLIDO'
    direccion_entrega: Optional[str] = None
    guia_despacho: Optional[str] = None
    observaciones: Optional[str] = None
class EnvioCreate(EnvioBase):
    pass
class EnvioUpdate(BaseModel):
    empleado_id: Optional[int] = None
    fecha_salida: Optional[datetime] = None
    fecha_entrega: Optional[datetime] = None
    estado: Optional[str] = None
    direccion_entrega: Optional[str] = None
    guia_despacho: Optional[str] = None
    observaciones: Optional[str] = None
class EnvioResponse(EnvioBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    pedido: Optional[PedidoResponse] = None
    empleado: Optional[EmpleadoResponse] = None
    class Config:
        from_attributes = True