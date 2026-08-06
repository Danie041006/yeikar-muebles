from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.modules.catalogos.schemas import TipoProductoResponse, UnidadMedidaResponse

# ------------------------------------------------------------
# Producto
# ------------------------------------------------------------
class ProductoBase(BaseModel):
    nombre: str
    codigo: Optional[str] = None
    tipo_producto_id: int
    descripcion: Optional[str] = None
    activo: Optional[bool] = True
    ancho_base: Optional[float] = 1.60
    largo_base: Optional[float] = 1.90
    alto_base: Optional[float] = None
    stock_minimo: Optional[float] = 8.0
    es_reventa: Optional[bool] = False

class ProductoCreate(ProductoBase):
    pass

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

class ProductoResponse(ProductoBase):
    id: int
    precio_costo_base: Optional[float] = None
    precio_venta_base: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tipo_producto: Optional[TipoProductoResponse] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Material (DEFINIR ANTES de ProductoMaterialResponse)
# ------------------------------------------------------------
class MaterialBase(BaseModel):
    nombre: str
    unidad_medida_id: int
    costo_base: Optional[float] = 0.0
    activo: Optional[bool] = True
    stock_minimo: Optional[float] = 8.0

class MaterialCreate(MaterialBase):
    pass

class MaterialUpdate(BaseModel):
    nombre: Optional[str] = None
    unidad_medida_id: Optional[int] = None
    costo_base: Optional[float] = None
    activo: Optional[bool] = None
    stock_minimo: Optional[float] = None

class MaterialResponse(MaterialBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    unidad_medida: Optional[UnidadMedidaResponse] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# ProductoMaterial (receta paramétrica) - AHORA SÍ PUEDE USAR MaterialResponse
# ------------------------------------------------------------
class ProductoMaterialBase(BaseModel):
    material_id: int
    cantidad_base: float
    tipo_escala: str  # FIJO | LINEAL | AREA | ESPACIADO | POR_RANGO | FORMULA
    seccion: str = "EBANISTERIA"
    distancia_pauta_cm: Optional[float] = None
    tornillos_por_pieza: Optional[int] = None
    condicion_activacion: Optional[Dict[str, Any]] = None
    rangos: Optional[List[Dict[str, Any]]] = None
    formula_personalizada: Optional[str] = None
    es_fijo_override: Optional[bool] = False
    observaciones: Optional[str] = None

class ProductoMaterialCreate(ProductoMaterialBase):
    pass

class ProductoMaterialUpdate(BaseModel):
    material_id: Optional[int] = None
    cantidad_base: Optional[float] = None
    tipo_escala: Optional[str] = None
    seccion: Optional[str] = None
    distancia_pauta_cm: Optional[float] = None
    tornillos_por_pieza: Optional[int] = None
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
    secciones: List[SeccionProductoResponse]