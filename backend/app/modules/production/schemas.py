from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import List, Optional
from app.modules.catalogos.schemas import AreaResponse
from app.modules.empleados.schemas import EmpleadoResponse
from app.modules.productos.schemas import MaterialResponse, ProductoResponse

# ------------------------------------------------------------
# Consumo de Material
# ------------------------------------------------------------
class ConsumoMaterialBase(BaseModel):
    cantidad: float = Field(gt=0)
    fecha: datetime
    observaciones: Optional[str] = None
    seccion: Optional[str] = None

class ConsumoMaterialCreate(ConsumoMaterialBase):
    etapa_produccion_id: int
    material_id: int
    # Obligatorio: quién pide el material (empleado). Trazabilidad por honestidad.
    solicitante_empleado_id: int
    # --- Pedido de LÁMINA COMPLETA (confirmación de uso después) ---
    # Si es True y el material es laminar, `cantidad` = N.º de láminas enteras
    # que salen del depósito AHORA (costo provisional N × costo_base) y el
    # consumo queda PENDIENTE hasta confirmar por cortes cuánto se usó.
    es_lamina_completa: Optional[bool] = False
    # --- Consumo por CORTE (materiales laminares) ---
    # Si se envían las dos medidas, `cantidad` = NÚMERO de cortes de ese tamaño.
    ancho_corte_cm: Optional[float] = Field(None, gt=0)
    largo_corte_cm: Optional[float] = Field(None, gt=0)
    # Sobrante del que salen los cortes (None = láminas nuevas del depósito).
    origen_sobrante_id: Optional[int] = None
    # Opcional: medidas reales del pedazo restante que el operario editó.
    sobrante_largo_cm: Optional[float] = Field(None, gt=0)
    sobrante_ancho_cm: Optional[float] = Field(None, gt=0)
    # --- Captura flexible de madera (cm/mts, pieza volumétrica) ---
    # `cantidad` = número digitado por el operario (en modo pieza: N.º de
    # piezas). El backend lo convierte a la unidad base del material antes de
    # descontar (ver app/modules/production/unidades.py).
    unidad_captura: Optional[str] = Field(None, pattern="^(M|CM)$")
    # Medidas de UNA pieza tal cual las escribe el taller; si alguna viene se
    # activa la fórmula de la casa: (L×A×E) × cantidad ÷ 1000 = m³.
    pieza_largo: Optional[float] = Field(None, gt=0)
    pieza_ancho: Optional[float] = Field(None, gt=0)
    pieza_espesor: Optional[float] = Field(None, gt=0)
    # --- Componente y consumo extra (estructura de costes desde producción) ---
    # componente: pieza del mueble (CAMA, NOCHERO, CABECERA...) → secciones
    # "SECCIÓN (COMPONENTE)" en la estructura generada.
    componente: Optional[str] = Field(None, max_length=50)
    # es_excedente: material usado de más (daño/desperdicio) → cuenta en el
    # costo real de la orden pero se excluye de la estructura de costes.
    es_excedente: Optional[bool] = False
    motivo_exceso: Optional[str] = Field(None, max_length=100)

class ConsumoMaterialUpdate(BaseModel):
    cantidad: Optional[float] = Field(None, gt=0)
    fecha: Optional[datetime] = None
    observaciones: Optional[str] = None

class ConsumoConfirmarCreate(BaseModel):
    """Confirmación de uso de una lámina pedida completa: cuántos cortes de qué
    tamaño salieron de las láminas. Recalcula el costo real (proporcional al
    área), devuelve/descarta láminas según corresponda y genera el sobrante."""
    cantidad_cortes: float = Field(gt=0)
    largo_corte_cm: float = Field(gt=0)
    ancho_corte_cm: float = Field(gt=0)
    # Opcional: medidas reales del pedazo restante que el operario editó.
    sobrante_largo_cm: Optional[float] = Field(None, gt=0)
    sobrante_ancho_cm: Optional[float] = Field(None, gt=0)

class ConsumoMaterialResponse(ConsumoMaterialBase):
    id: int
    etapa_produccion_id: int
    material_id: int
    estado: Optional[str] = None
    costo_unitario: Optional[float] = None
    solicitante_empleado_id: Optional[int] = None
    solicitante_nombre: Optional[str] = None
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    material: Optional[MaterialResponse] = None
    ancho_corte_cm: Optional[float] = None
    largo_corte_cm: Optional[float] = None
    origen_sobrante_id: Optional[int] = None
    laminas_consumidas: Optional[float] = None
    unidad_captura: Optional[str] = None
    pieza_largo: Optional[float] = None
    pieza_ancho: Optional[float] = None
    pieza_espesor: Optional[float] = None
    componente: Optional[str] = None
    es_excedente: Optional[bool] = False
    motivo_exceso: Optional[str] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Mano de Obra
# ------------------------------------------------------------
class ManoObraBase(BaseModel):
    monto: float = Field(ge=0)
    porcentaje_recargo: Optional[float] = Field(0.0, ge=0, le=100)
    pagado: Optional[bool] = False
    listo_nomina: Optional[bool] = True
    observaciones: Optional[str] = None

class ManoObraCreate(ManoObraBase):
    etapa_produccion_id: int
    empleado_id: int
    # Tarifa del listado de costos de producción de la que salió el monto.
    precio_produccion_id: Optional[int] = None

class ManoObraUpdate(BaseModel):
    monto: Optional[float] = Field(None, ge=0)
    porcentaje_recargo: Optional[float] = Field(None, ge=0, le=100)
    observaciones: Optional[str] = None

class ManoObraResponse(ManoObraBase):
    id: int
    etapa_produccion_id: int
    empleado_id: int
    precio_produccion_id: Optional[int] = None
    precio_produccion_descripcion: Optional[str] = None
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
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
    observaciones: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None

class EtapaProduccionResponse(EtapaProduccionBase):
    id: int
    orden_produccion_id: int
    area_id: int
    empleado_responsable_id: Optional[int] = None
    es_retrabajo: bool = False
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
    costo_material: float = Field(ge=0)
    costo_mano_obra: float = Field(ge=0)
    costo_gastos: float = Field(ge=0)
    precio_impuestos_base: float = Field(ge=0)
    ganancia_porcentaje: float = Field(ge=0, le=100)
    precio_venta_calculado: float = Field(ge=0)
    costo_total: float = Field(ge=0)
    # Estimado congelado al calcular el costo (precio_costo_base × unidades).
    # None si el producto no tenía costo base: no hay comparativa.
    costo_estimado: Optional[float] = None

class CostoProduccionCreate(BaseModel): 
    ganancia_porcentaje: Optional[float] = Field(0.0, ge=0, le=100)
    costo_gastos: Optional[float] = Field(0.0, ge=0)
    precio_impuestos_base: Optional[float] = Field(0.0, ge=0)

class CostoProduccionUpdate(BaseModel):
    costo_material: Optional[float] = Field(None, ge=0)
    costo_mano_obra: Optional[float] = Field(None, ge=0)
    costo_gastos: Optional[float] = Field(None, ge=0)
    precio_impuestos_base: Optional[float] = Field(None, ge=0)
    ganancia_porcentaje: Optional[float] = Field(None, ge=0, le=100)
    precio_venta_calculado: Optional[float] = Field(None, ge=0)
    costo_total: Optional[float] = Field(None, ge=0)

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
    # Opcional: si es_stock=True, no hace falta detalle de pedido.
    detalle_pedido_id: Optional[int] = None
    es_stock: Optional[bool] = False
    # Solo para órdenes de stock: qué mueble se fabrica.
    producto_id: Optional[int] = None
    # Opcional: el servicio deriva el tipo (PEDIDO/EXHIBICION/STOCK) según el
    # producto; si se envía debe coincidir con lo derivado.
    tipo: Optional[str] = None

class OrdenProduccionUpdate(BaseModel):
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
    # Fecha prometida de entrega: el Kanban la muestra para que el área
    # conozca el compromiso con el cliente.
    fecha_entrega_estimada: Optional[date] = None

    class Config:
        from_attributes = True

class DetalleDePedidoBasico(BaseModel):
    id: int
    cantidad: Optional[float] = None
    ancho: Optional[float] = None
    largo: Optional[float] = None
    producto: Optional[ProductoResponse] = None
    pedido: Optional[PedidoBasicoEnDetalle] = None

    class Config:
        from_attributes = True

class OrdenProduccionMinima(BaseModel):
    id: int
    detalle_pedido_id: Optional[int] = None
    detalle_pedido: Optional[DetalleDePedidoBasico] = None
    producto: Optional[ProductoResponse] = None
    es_stock: bool = False
    # Destino de lo fabricado: PEDIDO | EXHIBICION | STOCK.
    tipo: str = "PEDIDO"
    estado: str
    ancho: Optional[float] = None
    largo: Optional[float] = None
    alto: Optional[float] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None

    class Config:
        from_attributes = True
    
class OrdenProduccionResponse(OrdenProduccionBase):
    id: int
    detalle_pedido_id: Optional[int] = None
    detalle_pedido: Optional[DetalleDePedidoBasico] = None
    producto: Optional[ProductoResponse] = None
    es_stock: bool = False
    # Destino de lo fabricado: PEDIDO | EXHIBICION | STOCK.
    tipo: str = "PEDIDO"
    # Transitorio (no es columna): True si al finalizar se generó la
    # estructura de costes del producto desde la producción.
    estructura_generada: Optional[bool] = None
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
    tipo_escala: str
    condicion_cumplida: bool
    cantidad_base: float
    cantidad_esperada: float
    unidad: str
    costo_unitario: float
    # Solo para tipo_escala=CORTE (materiales laminares)
    es_corte: Optional[bool] = None
    ancho_corte_cm: Optional[float] = None
    largo_corte_cm: Optional[float] = None
    cortes_por_lamina: Optional[int] = None
    laminas_equivalentes: Optional[float] = None
    costo_por_corte: Optional[float] = None

class ReferenciaRecetaResponse(BaseModel):
    producto_id: int
    producto_nombre: str
    dimensiones: dict
    seccion_actual: Optional[str] = None
    materiales: List[MaterialReferencia]


# ------------------------------------------------------------
# Pasar a Área (transición controlada)
# ------------------------------------------------------------
class PasarAAreaRequest(BaseModel):
    area_id: int
    empleado_responsable_id: int
    empleados_adicionales_ids: List[int] = []
    observaciones: Optional[str] = None


# ------------------------------------------------------------
# Producto en Crudo (ítem libre: catálogo + stock)
# ------------------------------------------------------------
class CrudoCreate(BaseModel):
    # Único dato obligatorio al crear: el nombre (foto se sube aparte).
    nombre: str = Field(min_length=1, max_length=200)
    area_id: Optional[int] = None
    ubicacion_id: Optional[int] = 1
    cantidad: Optional[float] = Field(0.0, ge=0)


class CrudoResponse(BaseModel):
    id: int
    nombre: str
    area_id: Optional[int] = None
    area: Optional[AreaResponse] = None
    ubicacion_id: int
    cantidad: float
    activo: bool = True
    foto_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Producción de Crudos (segunda producción)
# ------------------------------------------------------------
class ProduccionCrudoCreate(BaseModel):
    crudo_id: int
    cantidad: Optional[float] = Field(1.0, gt=0)
    observaciones: Optional[str] = None


class ProduccionCrudoEstadoUpdate(BaseModel):
    estado: str  # EN_PRODUCCION | COMPLETADA | CANCELADA


class CrudoConsumoCreate(BaseModel):
    material_id: int
    cantidad: float = Field(gt=0)
    solicitante_empleado_id: int
    seccion: Optional[str] = None
    observaciones: Optional[str] = None
    # --- Consumo por CORTE (materiales laminares) ---
    ancho_corte_cm: Optional[float] = Field(None, gt=0)
    largo_corte_cm: Optional[float] = Field(None, gt=0)
    origen_sobrante_id: Optional[int] = None
    sobrante_largo_cm: Optional[float] = Field(None, gt=0)
    sobrante_ancho_cm: Optional[float] = Field(None, gt=0)
    # --- Captura flexible de madera, igual que ConsumoMaterialCreate ---
    unidad_captura: Optional[str] = Field(None, pattern="^(M|CM)$")
    pieza_largo: Optional[float] = Field(None, gt=0)
    pieza_ancho: Optional[float] = Field(None, gt=0)
    pieza_espesor: Optional[float] = Field(None, gt=0)
    # --- Componente y consumo extra ---
    componente: Optional[str] = Field(None, max_length=50)
    es_excedente: Optional[bool] = False
    motivo_exceso: Optional[str] = Field(None, max_length=100)


class CrudoConsumoResponse(BaseModel):
    id: int
    produccion_crudo_id: int
    material_id: int
    material_nombre: Optional[str] = None
    cantidad: float
    costo_unitario: Optional[float] = None
    seccion: Optional[str] = None
    solicitante_empleado_id: Optional[int] = None
    solicitante_nombre: Optional[str] = None
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    fecha: Optional[datetime] = None
    observaciones: Optional[str] = None
    ancho_corte_cm: Optional[float] = None
    largo_corte_cm: Optional[float] = None
    origen_sobrante_id: Optional[int] = None
    laminas_consumidas: Optional[float] = None
    unidad_captura: Optional[str] = None
    pieza_largo: Optional[float] = None
    pieza_ancho: Optional[float] = None
    pieza_espesor: Optional[float] = None
    componente: Optional[str] = None
    es_excedente: Optional[bool] = False
    motivo_exceso: Optional[str] = None

    class Config:
        from_attributes = True


class ProduccionCrudoResponse(BaseModel):
    id: int
    crudo_id: int
    crudo_nombre: Optional[str] = None
    estado: str
    cantidad: float
    costo_total: float
    costo_mano_obra: float = 0
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    observaciones: Optional[str] = None
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    consumos: List[CrudoConsumoResponse] = []
    mano_obras: List["ProduccionCrudoManoObraResponse"] = []

    class Config:
        from_attributes = True


class CrudoUsoResponse(BaseModel):
    id: int
    crudo_id: int
    detalle_pedido_id: int
    cantidad: float
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Mano de obra en producción de crudo
# ------------------------------------------------------------
class ProduccionCrudoManoObraCreate(BaseModel):
    empleado_id: int
    monto: float = Field(ge=0)
    cantidad: Optional[float] = Field(None, gt=0)
    porcentaje_recargo: Optional[float] = Field(0.0, ge=0, le=100)
    listo_nomina: Optional[bool] = True
    observaciones: Optional[str] = None


class ProduccionCrudoManoObraUpdate(BaseModel):
    monto: Optional[float] = Field(None, ge=0)
    cantidad: Optional[float] = Field(None, gt=0)
    porcentaje_recargo: Optional[float] = Field(None, ge=0, le=100)
    listo_nomina: Optional[bool] = None
    observaciones: Optional[str] = None


class ProduccionCrudoManoObraResponse(BaseModel):
    id: int
    produccion_crudo_id: int
    empleado_id: int
    empleado_nombre: Optional[str] = None
    monto: float
    porcentaje_recargo: float
    listo_nomina: bool
    pagado: bool
    observaciones: Optional[str] = None
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


ProduccionCrudoResponse.model_rebuild()
