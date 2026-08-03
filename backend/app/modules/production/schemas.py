from pydantic import BaseModel
from datetime import date, datetime
from typing import List, Optional
from app.modules.catalogos.schemas import AreaResponse
from app.modules.empleados.schemas import EmpleadoResponse
from app.modules.productos.schemas import MaterialResponse, ProductoResponse

# ------------------------------------------------------------
# Consumo de Material
# ------------------------------------------------------------
class ConsumoMaterialBase(BaseModel):
    cantidad: float
    fecha: datetime
    observaciones: Optional[str] = None

class ConsumoMaterialCreate(ConsumoMaterialBase):
    etapa_produccion_id: int
    material_id: int

class ConsumoMaterialUpdate(BaseModel):
    cantidad: Optional[float] = None
    fecha: Optional[datetime] = None
    observaciones: Optional[str] = None

class ConsumoMaterialResponse(ConsumoMaterialBase):
    id: int
    etapa_produccion_id: int
    material_id: int
    costo_unitario: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    material: Optional[MaterialResponse] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Mano de Obra
# ------------------------------------------------------------
class ManoObraBase(BaseModel):
    monto: float
    porcentaje_recargo: Optional[float] = 0.0
    pagado: Optional[bool] = False
    observaciones: Optional[str] = None

class ManoObraCreate(ManoObraBase):
    etapa_produccion_id: int
    empleado_id: int

class ManoObraUpdate(BaseModel):
    monto: Optional[float] = None
    porcentaje_recargo: Optional[float] = None
    observaciones: Optional[str] = None

class ManoObraResponse(ManoObraBase):
    id: int
    etapa_produccion_id: int
    empleado_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    empleado: Optional[EmpleadoResponse] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Asignado Adicional
# ------------------------------------------------------------
class AsignadoAdicionalResponse(BaseModel):
    id: int
    etapa_produccion_id: int
    empleado_id: int
    empleado: Optional[EmpleadoResponse] = None

    class Config:
        from_attributes = True

class AsignadoAdicionalCreate(BaseModel):
    empleado_id: int

# ------------------------------------------------------------
# Etapa de Producción
# ------------------------------------------------------------
class EtapaProduccionBase(BaseModel):
    estado: str
    observaciones: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None

class EtapaProduccionCreate(EtapaProduccionBase):
    orden_produccion_id: int
    area_id: int
    empleado_responsable_id: int

class EtapaProduccionUpdate(BaseModel):
    area_id: Optional[int] = None
    empleado_responsable_id: Optional[int] = None
    estado: Optional[str] = None
    observaciones: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None

class EtapaProduccionResponse(EtapaProduccionBase):
    id: int
    orden_produccion_id: int
    area_id: int
    empleado_responsable_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    area: Optional[AreaResponse] = None
    empleado_responsable: Optional[EmpleadoResponse] = None
    consumos: List[ConsumoMaterialResponse] = []
    mano_obras: List[ManoObraResponse] = []
    asignados_adicionales: List[AsignadoAdicionalResponse] = []
    orden: Optional['OrdenProduccionMinima'] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Costo de Producción
# ------------------------------------------------------------
class CostoProduccionBase(BaseModel):
    costo_material: float
    costo_mano_obra: float
    costo_gastos: float
    precio_impuestos_base: float
    ganancia_porcentaje: float
    precio_venta_calculado: float
    costo_total: float

class CostoProduccionCreate(BaseModel): 
    ganancia_porcentaje: Optional[float] = 0.0
    costo_gastos: Optional[float] = 0.0
    precio_impuestos_base: Optional[float] = 0.0

class CostoProduccionUpdate(BaseModel):
    costo_material: Optional[float] = None
    costo_mano_obra: Optional[float] = None
    costo_gastos: Optional[float] = None
    precio_impuestos_base: Optional[float] = None
    ganancia_porcentaje: Optional[float] = None
    precio_venta_calculado: Optional[float] = None
    costo_total: Optional[float] = None

class CostoProduccionResponse(CostoProduccionBase):
    id: int
    orden_produccion_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Orden de Producción
# ------------------------------------------------------------
class OrdenProduccionBase(BaseModel):
    estado: str
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None

class OrdenProduccionCreate(OrdenProduccionBase):
    detalle_pedido_id: int

class OrdenProduccionUpdate(BaseModel):
    estado: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None

class ClienteBasicoResponse(BaseModel):
    id: int
    nombre: str
    telefono: Optional[str] = None

    class Config:
        from_attributes = True

class PedidoBasicoEnDetalle(BaseModel):
    id: int
    cliente: Optional[ClienteBasicoResponse] = None

    class Config:
        from_attributes = True

class DetalleDePedidoBasico(BaseModel):
    id: int
    ancho: Optional[float] = None
    largo: Optional[float] = None
    producto: Optional[ProductoResponse] = None
    pedido: Optional[PedidoBasicoEnDetalle] = None

    class Config:
        from_attributes = True

class OrdenProduccionMinima(BaseModel):
    id: int
    detalle_pedido_id: int
    detalle_pedido: Optional[DetalleDePedidoBasico] = None
    estado: str
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None

    class Config:
        from_attributes = True
    
class OrdenProduccionResponse(OrdenProduccionBase):
    id: int
    detalle_pedido_id: int
    detalle_pedido: Optional[DetalleDePedidoBasico] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    etapas: List[EtapaProduccionResponse] = []
    costo: Optional[CostoProduccionResponse] = None

    class Config:
        from_attributes = True

EtapaProduccionResponse.model_rebuild()


# ------------------------------------------------------------
# Referencia de Receta (para visualización en Kanban)
# ------------------------------------------------------------
class MaterialReferencia(BaseModel):
    material_id: int
    nombre: str
    seccion: str
    cantidad_base: float
    cantidad_esperada: float
    unidad: str
    costo_unitario: float

class ReferenciaRecetaResponse(BaseModel):
    producto_id: int
    producto_nombre: str
    dimensiones: dict
    materiales: List[MaterialReferencia]


# ------------------------------------------------------------
# Pasar a Área (transición controlada)
# ------------------------------------------------------------
class PasarAAreaRequest(BaseModel):
    area_id: int
    empleado_responsable_id: int
    empleados_adicionales_ids: List[int] = []
    observaciones: Optional[str] = None
