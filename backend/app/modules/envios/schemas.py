from pydantic import BaseModel, ConfigDict, Field
from datetime import date, datetime
from typing import List, Optional
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
    creado_por_id: Optional[int] = None
    actualizado_por_id: Optional[int] = None
    asignado_por_usuario_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    asignado_por_nombre: Optional[str] = None
    pedido: Optional[PedidoResponse] = None
    empleado: Optional[EmpleadoResponse] = None
    class Config:
        from_attributes = True


class ClienteRepartoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None


class ProductoRepartoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: Optional[str] = None


class MaterialRepartoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: Optional[str] = None


class DetallePedidoRepartoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pedido_id: int
    # INSUMO vendido suelto: producto_id NULL, material_id presente.
    producto_id: Optional[int] = None
    material_id: Optional[int] = None
    tipo_item: Optional[str] = None
    cantidad: float
    alto: Optional[float] = None
    ancho: Optional[float] = None
    largo: Optional[float] = None
    color: Optional[str] = None
    acabado: Optional[str] = None
    observaciones: Optional[str] = None
    producto: Optional[ProductoRepartoResponse] = None
    material: Optional[MaterialRepartoResponse] = None


class PedidoRepartoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int
    fecha: Optional[date] = None
    estado: str
    fecha_entrega_estimada: Optional[date] = None
    cliente: Optional[ClienteRepartoResponse] = None
    detalles: List[DetallePedidoRepartoResponse] = []


class EnvioRepartoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pedido_id: int
    empleado_id: Optional[int] = None
    fecha_salida: Optional[datetime] = None
    fecha_entrega: Optional[datetime] = None
    estado: str
    direccion_entrega: Optional[str] = None
    guia_despacho: Optional[str] = None
    observaciones: Optional[str] = None
    pedido: Optional[PedidoRepartoResponse] = None


class EnvioUbicacionCreate(BaseModel):
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    precision_m: Optional[float] = Field(None, ge=0, le=100000)
    velocidad: Optional[float] = Field(None, ge=0, le=1000)
    rumbo: Optional[float] = Field(None, ge=0, lt=360)
    capturada_en: Optional[datetime] = None
    fuente: str = Field(default="web", max_length=30)
    secuencia: Optional[int] = Field(None, ge=0)


class EnvioUbicacionResponse(EnvioUbicacionCreate):
    id: int
    envio_id: int
    empleado_id: Optional[int] = None
    reportado_por_id: Optional[int] = None
    reportado_por_nombre: Optional[str] = None
    recibida_en: datetime

    class Config:
        from_attributes = True
