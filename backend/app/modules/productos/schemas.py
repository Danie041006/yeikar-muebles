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

class ProductoResponse(ProductoBase):
    id: int
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
    costo_base: float
    activo: Optional[bool] = True

class MaterialCreate(MaterialBase):
    pass

class MaterialUpdate(BaseModel):
    nombre: Optional[str] = None
    unidad_medida_id: Optional[int] = None
    costo_base: Optional[float] = None
    activo: Optional[bool] = None

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