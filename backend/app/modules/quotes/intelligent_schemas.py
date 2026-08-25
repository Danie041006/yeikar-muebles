"""
intelligent_schemas.py
======================
Schemas Pydantic del COTIZADOR MANUAL de YEIKAR (sin APIs de pago).

Flujo: contexto-exportar → import-structure → recalculate-structure → finalize-structure.

REGLA: la IA de navegador SOLO propone materiales y cantidades (JSON).
       El ERP calcula costos con precios del inventario y guarda.
"""

from pydantic import BaseModel
from typing import Optional


# ---------------------------------------------------------------------------
# Estructura de Costos editable (núcleo del editor)
# ---------------------------------------------------------------------------

class LineaCostoIn(BaseModel):
    temp_id: str
    material_id: Optional[int] = None
    nombre: str
    cantidad: float
    unidad: str
    costo_unitario: float
    costo_total: float
    precio_pendiente: bool
    razon: str
    fuente: str
    es_opcional: bool
    activo: bool
    sugerencias: list[dict] = []
    cantidad_ia_sugerida: Optional[float] = None
    cantidad_referencia: Optional[float] = None
    confianza_cantidad: str = "baja"


class SeccionCostoIn(BaseModel):
    seccion: str
    items: list[LineaCostoIn]
    subtotal: float


class LineaCostoOut(BaseModel):
    temp_id: str
    material_id: Optional[int] = None
    nombre: str
    cantidad: float
    unidad: str
    costo_unitario: float
    costo_total: float
    precio_pendiente: bool
    razon: str
    fuente: str
    es_opcional: bool
    activo: bool
    sugerencias: list[dict] = []
    cantidad_ia_sugerida: Optional[float] = None
    cantidad_referencia: Optional[float] = None
    confianza_cantidad: str = "baja"


class SeccionCostoOut(BaseModel):
    seccion: str
    items: list[LineaCostoOut]
    subtotal: float


class ResumenCostosOut(BaseModel):
    costo_materiales: float
    costo_mano_obra: float
    costo_gastos: float
    costo_produccion: float
    impuesto_porcentaje: float
    impuestos: float
    base_con_impuestos: float
    ganancia_porcentaje: float
    precio_sin_iva: float
    iva_porcentaje: float
    precio_con_iva: float


class GenerateStructureOut(BaseModel):
    producto_base_id: Optional[int] = None
    producto_base_nombre: Optional[str] = None
    score_similitud: float = 0.0
    secciones: list[SeccionCostoOut]
    materiales_sin_precio: int
    resumen: ResumenCostosOut
    # Validación post-import (Fase 4)
    secciones_faltantes: list[str] = []
    desviacion_vs_referencia: Optional[float] = None
    advertencia: Optional[str] = None


# ---------------------------------------------------------------------------
# Importar la estructura JSON pegada por el usuario
# ---------------------------------------------------------------------------

class ImportStructureRequest(BaseModel):
    """Estructura propuesta por una IA de navegador (sin API)."""
    estructura_propuesta: list[dict]
    producto_base_id: Optional[int] = None
    tipo_mueble: str = "otro"
    nuevo_ancho: float = 1.60
    nuevo_largo: float = 1.90
    nuevo_alto: Optional[float] = None
    nuevo_fondo: Optional[float] = None
    dimensiones_referencia: dict = {}
    ganancia_porcentaje: float = 40.0
    iva_porcentaje: float = 0.0
    impuesto_porcentaje: float = 7.0
    pct_mano_obra: float = 15.0
    pct_gastos: float = 10.0


class ImportTextoRequest(BaseModel):
    """Respuesta de la IA en FORMATO EXCEL (tabla por secciones).

    El ERP la convierte al JSON interno y construye la estructura de costos.
    """
    texto: str
    producto_base_id: Optional[int] = None
    tipo_mueble: str = "otro"
    nuevo_ancho: float = 1.60
    nuevo_largo: float = 1.90
    nuevo_alto: Optional[float] = None
    nuevo_fondo: Optional[float] = None
    dimensiones_referencia: dict = {}
    ganancia_porcentaje: float = 40.0
    iva_porcentaje: float = 0.0
    impuesto_porcentaje: float = 7.0
    pct_mano_obra: float = 15.0
    pct_gastos: float = 10.0


class RecalculateStructureRequest(BaseModel):
    secciones: list[SeccionCostoIn]
    ganancia_porcentaje: float = 40.0
    iva_porcentaje: float = 0.0
    impuesto_porcentaje: float = 7.0
    pct_mano_obra: float = 15.0
    pct_gastos: float = 10.0


class FinalizeStructureRequest(BaseModel):
    guardar_como: str = "cotizacion"  # "cotizacion" | "producto"
    # Si es "cotizacion":
    cliente_id: Optional[int] = None
    # Si es "producto":
    nombre_producto: Optional[str] = None
    tipo_producto_id: Optional[int] = None
    # Comunes:
    producto_base_id: Optional[int] = None
    secciones: list[SeccionCostoIn]
    nuevo_ancho: float
    nuevo_largo: float
    nuevo_alto: Optional[float] = None
    nuevo_fondo: Optional[float] = None
    ganancia_porcentaje: float = 40.0
    iva_porcentaje: float = 0.0
    impuesto_porcentaje: float = 7.0
    pct_mano_obra: float = 15.0
    pct_gastos: float = 10.0
    observaciones: Optional[str] = None
    analisis_id: Optional[int] = None


class FinalizeResponse(BaseModel):
    cotizacion_id: int
    total_estimado: float
    pdf_url: str
    mensaje: str


# ---------------------------------------------------------------------------
# Paquete de contexto para la IA de navegador
# ---------------------------------------------------------------------------

class MaterialContextoOut(BaseModel):
    id: int
    nombre: str
    costo_base: float
    unidad: Optional[str] = None
    abreviatura: Optional[str] = None
    sinonimos: list[str] = []


class RecetaContextoOut(BaseModel):
    producto_id: int
    nombre: str
    ancho_base: float
    largo_base: float
    alto_base: Optional[float] = None
    secciones: list[dict]


class PromptContextoOut(BaseModel):
    """Un prompt de la librería del Cotizador IA."""
    id: str
    titulo: str
    descripcion: str
    instrucciones: str


class ContextoExportarOut(BaseModel):
    """Paquete de contexto para una IA de navegador (modo manual sin API)."""
    producto_base_id: Optional[int] = None
    producto_base_nombre: Optional[str] = None
    inventario: list[MaterialContextoOut]
    receta_similar: Optional[RecetaContextoOut] = None
    instrucciones: str          # prompt maestro listo para pegar
    prompts: list[PromptContextoOut] = []   # librería de prompts especializados
    texto: str                  # paquete completo (markdown) para copiar/descargar
