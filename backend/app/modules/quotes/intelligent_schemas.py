"""
intelligent_schemas.py
======================
Schemas Pydantic para el Motor de Cotización Inteligente (IQE) de YEIKAR.

REGLA: La IA NUNCA calcula precios ni cantidades.
       Los schemas de entrada/salida reflejan esa separación de responsabilidades.
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, Any
from decimal import Decimal


# ---------------------------------------------------------------------------
# Respuesta del análisis de imagen (CAPA 2: Attribute Extractor)
# ---------------------------------------------------------------------------

class PreguntaOpcionOut(BaseModel):
    """Una opción de una pregunta dinámica (select/multi)."""
    valor: str
    etiqueta: str


class PreguntaFaltanteOut(BaseModel):
    """
    Pregunta que la IA hace al vendedor porque no pudo responderla desde la
    imagen pero SÍ afecta la estructura de costos. La clave DEBE pertenecer
    al vocabulario que el motor de costos sabe consumir.
    """
    clave: str
    pregunta: str
    tipo: str = "texto"       # select | multi | si_no | numero | texto
    opciones: list[PreguntaOpcionOut] = []
    requerida: bool = False
    por_que: str = ""


class FurnitureAttributesOut(BaseModel):
    """JSON de atributos que devuelve la IA tras analizar la foto."""
    tipo_mueble: str = "otro"
    familia_probable: Optional[str] = None
    estilo_general: Optional[str] = None
    tipo_patas: Optional[str] = None
    tiene_tapiceria: bool = False
    tiene_luces: bool = False
    nivel_confianza: float = 0.0
    observaciones: Optional[str] = None
    atributos_extra: dict = {}          # Campos específicos del tipo (nocheros, puertas, etc.)
    requiere_revision_humana: bool = False
    estructura_propuesta: list[dict] = []
    analisis_id: Optional[int] = None
    # Conciencia del modelo (v2)
    percepcion: Optional[str] = None
    dimensiones_referencia: dict = {}
    preguntas_faltantes: list[PreguntaFaltanteOut] = []


# ---------------------------------------------------------------------------
# Búsqueda de estructuras similares (CAPA 3: Similarity Engine)
# ---------------------------------------------------------------------------

class SimilarityResultOut(BaseModel):
    """Una estructura histórica en el Top N de similitud."""
    producto_id: int
    nombre: str
    tipo_mueble: str
    score: float
    score_pct: int
    coincidencias: list[str]
    diferencias: list[str]
    ancho_base: Optional[float] = None
    largo_base: Optional[float] = None
    tiene_receta: bool
    es_estructura_nueva: bool = False   # True si score < 0.40 (no hay histórico similar)

class FindSimilarRequest(BaseModel):
    """
    Atributos validados por el vendedor para buscar estructuras similares.
    Funciona para CUALQUIER tipo de mueble que fabrica YEIKAR.
    """
    tipo_mueble: str = "cama"           # Ver TIPOS_MUEBLE_VALIDOS en vision_provider.py
    familia_probable: Optional[str] = None
    estilo_general: Optional[str] = None
    tipo_patas: Optional[str] = None
    tiene_tapiceria: bool = False
    tiene_luces: bool = False
    atributos_extra: dict = {}          # {"tiene_nocheros": True, "tiene_espejo": False, ...}
    top_n: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="before")
    @classmethod
    def _normalizar_atributos_extra(cls, data: Any) -> Any:
        """Acepta tiene_nocheros / tiene_espejo en la raíz (compatibilidad con tests y UI legacy)."""
        if not isinstance(data, dict):
            return data
        extra = dict(data.get("atributos_extra") or {})
        for key in ("tiene_nocheros", "tiene_espejo", "tiene_cajones", "cantidad_puertas_aproximada"):
            if key in data and data[key] is not None:
                extra[key] = data[key]
        data["atributos_extra"] = extra
        return data

class FindSimilarResponse(BaseModel):
    resultados: list[SimilarityResultOut]
    tipo_mueble_buscado: str = "cama"
    hay_resultados: bool = True
    mensaje: Optional[str] = None


# ---------------------------------------------------------------------------
# Creación del borrador editable (CAPA 4: Recipe Engine → CAPA 5: Cost Engine)
# ---------------------------------------------------------------------------

class CreateDraftRequest(BaseModel):
    """Datos necesarios para crear un borrador de cotización a partir de una plantilla."""
    producto_base_id: int
    cotizacion_id: Optional[int] = None   # Si ya existe una cotización, vincular
    detalle_cotizacion_id: Optional[int] = None  # Si ya existe el detalle, actualizar
    nuevo_ancho: Decimal = Field(default=Decimal("1.60"), gt=0)
    nuevo_largo: Decimal = Field(default=Decimal("1.90"), gt=0)
    ganancia_porcentaje: Decimal = Field(default=Decimal("40"))
    iva_porcentaje: Decimal = Field(default=Decimal("0"))
    pct_mano_obra: Decimal = Field(default=Decimal("15"))
    pct_gastos: Decimal = Field(default=Decimal("10"))
    atributos: Optional[dict] = Field(default={})

class MaterialLineaOut(BaseModel):
    """Una línea de material en el borrador editable."""
    id: Optional[int] = None          # ID en cotizacion_detalle_material (si ya guardado)
    material_id: Optional[int] = None
    nombre: str
    tipo_escala: str
    cantidad_base: float
    cantidad_calculada: float
    unidad: str
    costo_unitario: float
    costo_total: float
    activo: bool = True
    observaciones: Optional[str] = None

class DraftOut(BaseModel):
    """Borrador completo de cotización listo para edición en el frontend."""
    producto_base_id: int
    producto_base_nombre: str
    nuevo_ancho: float
    nuevo_largo: float
    materiales: list[MaterialLineaOut]
    costo_materiales: float
    costo_mano_obra: float
    costo_gastos: float
    costo_produccion: float
    ganancia_porcentaje: float
    precio_sin_iva: float
    iva_porcentaje: float
    precio_con_iva: float


# ---------------------------------------------------------------------------
# Recálculo en tiempo real (CAPA 5: Cost Engine)
# ---------------------------------------------------------------------------

class MaterialLineaIn(BaseModel):
    """Línea de material enviada desde el frontend para recalcular."""
    material_id: Optional[int] = None
    cantidad_calculada: float
    activo: bool = True
    nombre: Optional[str] = None        # Para insumos libres sin material de inventario
    costo_unitario: Optional[float] = None  # Para insumos libres (si no, se usa el del inventario)

class RecalculateRequest(BaseModel):
    """Payload para recalcular el borrador con los cambios del vendedor."""
    producto_base_id: int
    nuevo_ancho: Decimal
    nuevo_largo: Decimal
    materiales: list[MaterialLineaIn]
    ganancia_porcentaje: Decimal = Decimal("40")
    iva_porcentaje: Decimal = Decimal("0")
    pct_mano_obra: Decimal = Decimal("15")
    pct_gastos: Decimal = Decimal("10")
    atributos: Optional[dict] = Field(default={})


# ---------------------------------------------------------------------------
# Persistencia final (CAPA 7: Persistence)
# ---------------------------------------------------------------------------

class FinalizeRequest(BaseModel):
    """Payload para guardar definitivamente la cotización."""
    cliente_id: int
    producto_base_id: int
    nuevo_ancho: Decimal
    nuevo_largo: Decimal
    materiales: list[MaterialLineaIn]
    ganancia_porcentaje: Decimal = Decimal("40")
    iva_porcentaje: Decimal = Decimal("0")
    pct_mano_obra: Decimal = Field(default=Decimal("15"))
    pct_gastos: Decimal = Field(default=Decimal("10"))
    observaciones: Optional[str] = None
    analisis_id: Optional[int] = None
    atributos: Optional[dict] = Field(default={})

class FinalizeResponse(BaseModel):
    """Respuesta tras finalizar y guardar la cotización."""
    cotizacion_id: int
    total_estimado: float
    pdf_url: str
    mensaje: str


# ---------------------------------------------------------------------------
# Estructura de Costos Editable con IA (v2)
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

class SeccionCostoOut(BaseModel):
    seccion: str
    items: list[LineaCostoOut]
    subtotal: float

class ResumenCostosOut(BaseModel):
    costo_materiales: float
    costo_mano_obra: float
    costo_gastos: float
    costo_produccion: float
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

class GenerateStructureRequest(BaseModel):
    tipo_mueble: str
    atributos: dict
    estructura_propuesta: list[dict]
    nuevo_ancho: float
    nuevo_largo: float
    nuevo_alto: Optional[float] = None
    nuevo_fondo: Optional[float] = None
    respuestas: dict = {}               # Respuestas del vendedor a las preguntas de la IA
    dimensiones_referencia: dict = {}   # Medidas que la IA asumió al proponer cantidades
    ganancia_porcentaje: float = 40.0
    iva_porcentaje: float = 0.0
    pct_mano_obra: float = 15.0
    pct_gastos: float = 10.0

class RecalculateStructureRequest(BaseModel):
    secciones: list[SeccionCostoIn]
    ganancia_porcentaje: float = 40.0
    iva_porcentaje: float = 0.0
    pct_mano_obra: float = 15.0
    pct_gastos: float = 10.0

class FinalizeStructureRequest(BaseModel):
    guardar_como: str = "cotizacion" # "cotizacion" | "producto"
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
    pct_mano_obra: float = 15.0
    pct_gastos: float = 10.0
    observaciones: Optional[str] = None
    analisis_id: Optional[int] = None

