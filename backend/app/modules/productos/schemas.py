from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.modules.catalogos.schemas import TipoProductoResponse, UnidadMedidaResponse, MonedaResponse, CategoriaInventarioResponse
from app.modules.adjuntos.schemas import AdjuntoInfo

# ------------------------------------------------------------
# Producto
# ------------------------------------------------------------
class ProductoBase(BaseModel):
    nombre: str
    codigo: Optional[str] = None
    tipo_producto_id: int
    descripcion: Optional[str] = None
    activo: Optional[bool] = True
    # Dimensiones base OPCIONALES (null si aún no se conocen; el motor de
    # costos asume 1.60×1.90 al calcular cuando faltan)
    ancho_base: Optional[float] = None
    largo_base: Optional[float] = None
    alto_base: Optional[float] = None
    stock_minimo: Optional[float] = 8.0
    es_reventa: Optional[bool] = False
    # Pieza de exhibición: se fabrica, vive en el stock del showroom y su venta
    # descuenta ese stock al facturar (tratada como reventa en la venta).
    es_exhibicion: Optional[bool] = False
    # Moneda de los precios de referencia (COP=1 por defecto). Los productos de
    # reventa suelen crearse en USD.
    moneda_id: Optional[int] = 1
    # Categoría para el desglose del inventario (COLCHONES, ELECTRODOMÉSTICOS...)
    categoria_inventario_id: Optional[int] = None

class ProductoCreate(ProductoBase):
    # Precios de referencia en la moneda declarada (moneda_id).
    precio_costo_base: Optional[float] = None
    precio_venta_base: Optional[float] = None

class ProductoUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo: Optional[str] = None
    tipo_producto_id: Optional[int] = None
    descripcion: Optional[str] = None
    activo: Optional[bool] = None
    ancho_base: Optional[float] = None
    largo_base: Optional[float] = None
    alto_base: Optional[float] = None
    stock_minimo: Optional[float] = None
    es_reventa: Optional[bool] = None
    es_exhibicion: Optional[bool] = None
    categoria_inventario_id: Optional[int] = None
    moneda_id: Optional[int] = None
    precio_costo_base: Optional[float] = None
    precio_venta_base: Optional[float] = None

class ProductoResponse(ProductoBase):
    id: int
    precio_costo_base: Optional[float] = None
    precio_venta_base: Optional[float] = None
    created_at: Optional[datetime] = None
    # Fotos de referencia del mueble (adjuntos tipo PRODUCTO)
    fotos: List["AdjuntoInfo"] = []
    moneda: Optional[MonedaResponse] = None

    class Config:
        from_attributes = True
    updated_at: Optional[datetime] = None
    tipo_producto: Optional[TipoProductoResponse] = None
    categoria_inventario: Optional[CategoriaInventarioResponse] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Material (DEFINIR ANTES de ProductoMaterialResponse)
# ------------------------------------------------------------
DEPARTAMENTOS_VALIDOS = {
    "EBANISTERIA",
    "PREPARACION",
    "PINTURA",
    "TAPICERIA",
    "VIDRIERIA",
    "TERMINACION",
}

class MaterialBase(BaseModel):
    nombre: str
    unidad_medida_id: int
    costo_base: Optional[float] = Field(0.0, ge=0)
    activo: Optional[bool] = True
    stock_minimo: Optional[float] = Field(8.0, ge=0)
    # Dimensiones de la lámina completa en cm (solo materiales laminares)
    largo_cm: Optional[float] = Field(None, gt=0)
    ancho_cm: Optional[float] = Field(None, gt=0)
    categoria_inventario_id: Optional[int] = None
    # Departamento del taller (NULL = transversal/general). Tendido → EBANISTERIA.
    departamento: Optional[str] = None

    @field_validator("departamento")
    @classmethod
    def _validar_departamento(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if v not in DEPARTAMENTOS_VALIDOS:
            raise ValueError(f"Departamento inválido: {v}")
        return v

class MaterialCreate(MaterialBase):
    pass

class MaterialUpdate(BaseModel):
    nombre: Optional[str] = None
    unidad_medida_id: Optional[int] = None
    costo_base: Optional[float] = Field(None, ge=0)
    activo: Optional[bool] = None
    stock_minimo: Optional[float] = Field(None, ge=0)
    largo_cm: Optional[float] = Field(None, gt=0)
    ancho_cm: Optional[float] = Field(None, gt=0)
    categoria_inventario_id: Optional[int] = None
    departamento: Optional[str] = None

    @field_validator("departamento")
    @classmethod
    def _validar_departamento(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if v not in DEPARTAMENTOS_VALIDOS:
            raise ValueError(f"Departamento inválido: {v}")
        return v

class MaterialResponse(MaterialBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    unidad_medida: Optional[UnidadMedidaResponse] = None

    class Config:
        from_attributes = True

    @property
    def es_laminar(self) -> bool:
        return self.largo_cm is not None and self.ancho_cm is not None


class MaterialFusionIn(BaseModel):
    material_origen_id: int
    material_destino_id: int
    # Opcional: costo que queda en el material sobreviviente tras la fusión.
    costo_base: Optional[float] = Field(None, ge=0)

# ------------------------------------------------------------
# ProductoMaterial (receta paramétrica) - AHORA SÍ PUEDE USAR MaterialResponse
# ------------------------------------------------------------
class ProductoMaterialBase(BaseModel):
    material_id: int
    cantidad_base: float = Field(gt=0)
    tipo_escala: str  # FIJO | LINEAL | AREA | ESPACIADO | POR_RANGO | FORMULA | CORTE
    seccion: str = "EBANISTERIA"
    distancia_pauta_cm: Optional[float] = Field(None, ge=0)
    tornillos_por_pieza: Optional[int] = Field(None, ge=0)
    # Solo para CORTE (materiales laminares): medidas del corte en cm
    ancho_corte_cm: Optional[float] = Field(None, gt=0)
    largo_corte_cm: Optional[float] = Field(None, gt=0)
    condicion_activacion: Optional[Dict[str, Any]] = None
    rangos: Optional[List[Dict[str, Any]]] = None
    formula_personalizada: Optional[str] = None
    es_fijo_override: Optional[bool] = False
    observaciones: Optional[str] = None

class ProductoMaterialCreate(ProductoMaterialBase):
    pass

class ProductoMaterialUpdate(BaseModel):
    material_id: Optional[int] = None
    cantidad_base: Optional[float] = Field(None, gt=0)
    tipo_escala: Optional[str] = None
    seccion: Optional[str] = None
    distancia_pauta_cm: Optional[float] = Field(None, ge=0)
    tornillos_por_pieza: Optional[int] = Field(None, ge=0)
    ancho_corte_cm: Optional[float] = Field(None, gt=0)
    largo_corte_cm: Optional[float] = Field(None, gt=0)
    condicion_activacion: Optional[Dict[str, Any]] = None
    rangos: Optional[List[Dict[str, Any]]] = None
    formula_personalizada: Optional[str] = None
    es_fijo_override: Optional[bool] = None
    observaciones: Optional[str] = None

class ProductoMaterialResponse(ProductoMaterialBase):
    id: int
    producto_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    material: Optional[MaterialResponse] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Esquemas para Recetas por Secciones (Jerárquicas)
# ------------------------------------------------------------
class ElementoSeccionUpdate(BaseModel):
    """Asociar/editar un insumo de sección (resuelve PENDIENTE/AMBIGUO).

    - material_id_normalizado → MAPEADO (o PENDIENTE si se envía null).
    - registrar_sinonimo=True → guarda nombre_insumo_original como sinónimo
      del material para que el próximo import matchee exacto.
    """
    nombre_insumo_original: Optional[str] = Field(None, min_length=2)
    material_id_normalizado: Optional[int] = None
    cantidad: Optional[float] = Field(None, gt=0)
    unidad_medida: Optional[str] = None
    precio_unitario: Optional[float] = Field(None, ge=0)
    observaciones: Optional[str] = None
    registrar_sinonimo: Optional[bool] = False


class PoliticaSeccionBase(BaseModel):
    mano_obra_base: float = 0.0
    pct_liquidacion_mo: float = 5.0
    pct_gastos_seccion: float = 10.0
    costo_fabricacion: Optional[float] = None
    pct_trabajadores: Optional[float] = None
    pct_negocio: Optional[float] = None

class PoliticaSeccionCreate(PoliticaSeccionBase):
    pass

class PoliticaSeccionUpdate(BaseModel):
    mano_obra_base: Optional[float] = None
    pct_liquidacion_mo: Optional[float] = None
    pct_gastos_seccion: Optional[float] = None
    costo_fabricacion: Optional[float] = None
    pct_trabajadores: Optional[float] = None
    pct_negocio: Optional[float] = None

class PoliticaSeccionResponse(PoliticaSeccionBase):
    id: int
    seccion_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ElementoSeccionBase(BaseModel):
    nombre_insumo_original: str
    material_id_normalizado: Optional[int] = None
    estado_resolucion: Optional[str] = "PENDIENTE"
    cantidad: float = 1.0
    unidad_medida: Optional[str] = None
    observaciones: Optional[str] = None
    precio_unitario: Optional[float] = None
    costo_subtotal: Optional[float] = None

class ElementoSeccionCreate(ElementoSeccionBase):
    seccion_id: int

class ElementoSeccionResponse(ElementoSeccionBase):
    id: int
    seccion_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# CostoProduccionSeccion — múltiples costos por sección
# ------------------------------------------------------------
class CostoProduccionSeccionBase(BaseModel):
    nombre: str
    porcentaje: Optional[float] = None
    costo_base: float = 0.0

class CostoProduccionSeccionCreate(CostoProduccionSeccionBase):
    seccion_id: int

class CostoProduccionSeccionUpdate(BaseModel):
    nombre: Optional[str] = None
    porcentaje: Optional[float] = None
    costo_base: Optional[float] = None

class CostoProduccionSeccionResponse(CostoProduccionSeccionBase):
    id: int
    seccion_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SeccionProductoCreate(BaseModel):
    producto_id: int
    nombre: str
    orden: Optional[int] = 1
    costo_fabricacion: Optional[float] = None
    pct_trabajadores: Optional[float] = None
    pct_negocio: Optional[float] = None
    mano_obra_base: Optional[float] = None
    pct_liquidacion_mo: Optional[float] = None
    pct_gastos_seccion: Optional[float] = None

class SeccionProductoResponse(BaseModel):
    id: int
    producto_id: int
    nombre: str
    orden: int
    elementos: List[ElementoSeccionResponse] = []
    politica: Optional[PoliticaSeccionResponse] = None
    costos_produccion: List[CostoProduccionSeccionResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RecalculateCustomRecipeRequest(BaseModel):
    ganancia: float = 40.0
    impuesto: float = 7.0
    secciones: List[SeccionProductoResponse]

# ------------------------------------------------------------
# Importación de estructura de costos pegada desde Excel
# ------------------------------------------------------------
class ImportarEstructuraTextoIn(BaseModel):
    texto: str = Field(..., min_length=10, description="Filas copiadas de la hoja de Excel")
    nombre: Optional[str] = Field(None, max_length=150)
    tipo_producto_id: Optional[int] = None
    nuevo_tipo_producto: Optional[str] = Field(None, max_length=80)
    ancho: float = Field(1.60, gt=0)
    largo: float = Field(1.90, gt=0)
    ganancia_porcentaje: float = Field(40.0, ge=0, le=999)
    impuesto_porcentaje: float = Field(7.0, ge=0, le=100)
    dry_run: bool = True
