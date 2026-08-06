"""
structure_builder.py
====================
Corazón del Cotizador Inteligente v2.

Toma la propuesta de estructura de la IA + la receta histórica del producto
más similar + los precios actuales del inventario, y produce una estructura
de costos editable organizada por secciones de producción
(EBANISTERÍA, PINTURA, NOCHEROS, TAPICERÍA, etc.).

Principio: La IA propone → el histórico refina → el inventario pone precios → el vendedor edita.
"""

import uuid
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.productos.model import (
    Producto,
    ProductoMaterial,
    Material,
    MaterialSinonimo,
)
from app.modules.quotes.similarity_engine import buscar_similares, SimilarityResult
from app.modules.quotes.vision_provider import FurnitureAttributes, VOCABULARIO_PREGUNTAS


# ---------------------------------------------------------------------------
# Constantes de secciones de producción
# ---------------------------------------------------------------------------

# Palabras clave para detectar a qué sección pertenece cada material
SECCION_KEYWORDS: dict[str, list[str]] = {
    "EBANISTERÍA": [
        "madera", "mdf", "mff", "melamina", "tabla", "lamina", "lámina",
        "colbon", "grapas", "clavillos", "tornillos", "ganchos", "bisagras",
        "correderas", "corredera", "perno", "pernos", "taco", "tacos",
        "union", "unión", "ensamble", "triplex", "aglomerado", "somier",
        "listones", "cabecero", "larguero", "travesaño", "piecero",
    ],
    "MANO DE OBRA": [
        "m.o", "mano de obra", "mano obra", "ebanisteria m.o", "tapiceria m.o",
        "pintura m.o", "labor", "instalacion", "instalación", "armado",
    ],
    "PINTURA": [
        "pintura", "sellador", "lija", "laca", "preparado", "thinner",
        "base", "anticorrosivo", "barniz", "tinte", "diluyente",
        "pistolada", "pistoletazo",
    ],
    "TAPICERÍA": [
        "tela", "tapiz", "espuma", "foam", "capitone", "capitoné",
        "hilo", "cremallera", "zipper", "velcro", "galon", "galón",
        "botones", "nylon", "tafeta", "polipiel", "cuero", "guata",
        "relleno",
    ],
    "HERRAJES": [
        "herraje", "jala", "jalón", "manija", "manigueta", "tirador",
        "cerradura", "candado", "chapa", "pivote", "riel", "rail",
        "correderá", "guia", "guía", "tope", "topes",
        "pata metalica", "patas metalicas",
    ],
    "TERMINACIÓN": [
        "moldura", "filete", "cenefa", "cinta", "perfil", "angulo",
        "ángulo", "esquinero", "tapacanto", "borde", "silicona",
        "masilla", "masillado", "porcelana",
    ],
    "NOCHEROS": [
        "nochero", "mesita", "mesa de noche", "velador",
    ],
    "ILUMINACIÓN": [
        "led", "luz", "luces", "tira led", "transformador", "difusor", "bombillo",
    ],
}

SECCION_DEFAULT = "EBANISTERÍA"
SECCIONES_ORDEN = [
    "EBANISTERÍA", "MANO DE OBRA", "PINTURA", "TAPICERÍA",
    "HERRAJES", "TERMINACIÓN", "NOCHEROS", "ILUMINACIÓN", "OTROS"
]


# ---------------------------------------------------------------------------
# Data classes internas
# ---------------------------------------------------------------------------

class LineaCosto:
    """Línea individual de costo en la estructura editable."""

    def __init__(
        self,
        nombre: str,
        cantidad: float,
        unidad: str,
        costo_unitario: float,
        material_id: Optional[int] = None,
        precio_pendiente: bool = False,
        razon: str = "",
        fuente: str = "ia",          # "ia", "historico", "ia+historico", "manual"
        es_opcional: bool = False,
        activo: bool = True,
        seccion: str = SECCION_DEFAULT,
        observaciones_historico: Optional[str] = None,
    ):
        self.temp_id = str(uuid.uuid4())[:8]
        self.material_id = material_id
        self.nombre = nombre
        self.cantidad = round(float(cantidad), 4)
        self.unidad = unidad
        self.costo_unitario = round(float(costo_unitario), 2)
        self.costo_total = round(self.cantidad * self.costo_unitario, 2)
        self.precio_pendiente = precio_pendiente
        self.razon = razon
        self.fuente = fuente
        self.es_opcional = es_opcional
        self.activo = activo
        self.seccion = seccion
        self.observaciones_historico = observaciones_historico

    def recalcular(self):
        self.costo_total = round(self.cantidad * self.costo_unitario, 2)

    def to_dict(self) -> dict:
        return {
            "temp_id": self.temp_id,
            "material_id": self.material_id,
            "nombre": self.nombre,
            "cantidad": self.cantidad,
            "unidad": self.unidad,
            "costo_unitario": self.costo_unitario,
            "costo_total": self.costo_total,
            "precio_pendiente": self.precio_pendiente,
            "razon": self.razon,
            "fuente": self.fuente,
            "es_opcional": self.es_opcional,
            "activo": self.activo,
            "seccion": self.seccion,
        }


class SeccionCosto:
    """Sección de producción (Ebanistería, Pintura, etc.)."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.items: list[LineaCosto] = []

    @property
    def subtotal(self) -> float:
        return round(sum(
            item.costo_total for item in self.items
            if item.activo and not item.precio_pendiente
        ), 2)

    def to_dict(self) -> dict:
        return {
            "seccion": self.nombre,
            "items": [item.to_dict() for item in self.items],
            "subtotal": self.subtotal,
        }


# ---------------------------------------------------------------------------
# Utilidades: búsqueda de materiales en inventario
# ---------------------------------------------------------------------------

def _similitud_nombre(a: str, b: str) -> float:
    """Similitud de cadenas normalizada (0.0 a 1.0)."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _buscar_material_inventario(
    db: Session,
    nombre_buscado: str,
    umbral: float = 0.60,
) -> Optional[Material]:
    """
    Busca el material más parecido al nombre dado en la tabla material
    y en la tabla material_sinonimo.

    Estrategia:
      1. Coincidencia exacta (normalizada)
      2. Coincidencia en sinónimos
      3. Similitud de cadena ≥ umbral

    Retorna el Material con mayor similitud, o None si no hay match.
    """
    nombre_norm = nombre_buscado.lower().strip()

    # 1. Buscar todos los materiales
    todos: list[Material] = db.query(Material).filter(Material.activo == True).all()

    mejor_match: Optional[Material] = None
    mejor_score = 0.0

    for mat in todos:
        # Score por nombre del material
        score = _similitud_nombre(nombre_norm, mat.nombre)
        if score > mejor_score:
            mejor_score = score
            mejor_match = mat

        # Score por sinónimos
        for sin in db.query(MaterialSinonimo).filter(
            MaterialSinonimo.material_id == mat.id
        ).all():
            score_sin = _similitud_nombre(nombre_norm, sin.sinonimo)
            if score_sin > mejor_score:
                mejor_score = score_sin
                mejor_match = mat

    if mejor_score >= umbral:
        return mejor_match
    return None


def _detectar_seccion(nombre_material: str) -> str:
    """Detecta a qué sección de producción pertenece un material por su nombre."""
    nombre_lower = nombre_material.lower()
    for seccion, keywords in SECCION_KEYWORDS.items():
        for kw in keywords:
            if kw in nombre_lower:
                return seccion
    return SECCION_DEFAULT


# ---------------------------------------------------------------------------
# Función principal: build_cost_structure
# ---------------------------------------------------------------------------

def build_cost_structure(
    db: Session,
    attrs: FurnitureAttributes,
    estructura_ia: list[dict],   # lista de secciones propuestas por la IA
    nuevo_ancho: float,
    nuevo_largo: float,
    nuevo_alto: Optional[float] = None,
    nuevo_fondo: Optional[float] = None,
    respuestas: Optional[dict] = None,
    dimensiones_referencia: Optional[dict] = None,
    ganancia_porcentaje: float = 40.0,
    iva_porcentaje: float = 0.0,
    pct_mano_obra: float = 15.0,
    pct_gastos: float = 10.0,
    top_n_similar: int = 3,
) -> dict:
    """
    Construye la estructura de costos editable fusionando:
      1. Propuesta de la IA (estructura_ia)
      2. Receta del producto histórico más similar
      3. Precios actuales del inventario

    Parámetros
    ----------
    db             : Sesión de SQLAlchemy
    attrs          : Atributos del mueble (validados por el vendedor)
    estructura_ia  : Lista de secciones con items propuestos por la IA
      Formato: [{"seccion": "EBANISTERÍA", "items": [{"nombre_material": ..., ...}]}]
    nuevo_ancho    : Ancho deseado en metros
    nuevo_largo    : Largo deseado en metros
    nuevo_alto     : Altura deseada en metros (opcional)
    nuevo_fondo    : Fondo/profundidad deseada en metros (opcional)
    respuestas     : Respuestas del vendedor a las preguntas de la IA
                     (claves del VOCABULARIO_PREGUNTAS)
    dimensiones_referencia : Medidas que la IA asumió al proponer cantidades
                     (para reescalar cantidades IA si no hay receta histórica)

    Retorna
    -------
    Dict con:
      - producto_base_id, producto_base_nombre, score_similitud
      - secciones: lista de SeccionCosto serializada
      - materiales_sin_precio: int
      - resumen: {costo_materiales, costo_total_seccion_X, ...}
    """

    respuestas = respuestas or {}
    dimensiones_referencia = dimensiones_referencia or {}
    nuevo_alto = float(nuevo_alto) if nuevo_alto else None
    nuevo_fondo = float(nuevo_fondo) if nuevo_fondo else None

    # 1. Buscar producto histórico más similar
    similares: list[SimilarityResult] = buscar_similares(db=db, attrs=attrs, top_n=top_n_similar)
    mejor_similar = similares[0] if similares else None

    # Cargar la receta histórica del más similar
    receta_historica: list[ProductoMaterial] = []
    producto_base: Optional[Producto] = None
    ancho_base_hist = Decimal("1.60")
    largo_base_hist = Decimal("1.90")
    alto_base_hist: Optional[Decimal] = None

    if mejor_similar:
        producto_base = db.query(Producto).filter(
            Producto.id == mejor_similar.producto_id
        ).first()
        if producto_base:
            receta_historica = list(producto_base.materiales)
            ancho_base_hist = producto_base.ancho_base or Decimal("1.60")
            largo_base_hist = producto_base.largo_base or Decimal("1.90")
            alto_base_hist = producto_base.alto_base

    ancho_nuevo = Decimal(str(nuevo_ancho))
    largo_nuevo = Decimal(str(nuevo_largo))
    alto_nuevo = Decimal(str(nuevo_alto)) if nuevo_alto else None

    # Índice de la receta histórica por nombre normalizado
    historico_por_nombre: dict[str, ProductoMaterial] = {}
    for pm in receta_historica:
        nombre_mat = pm.material.nombre if pm.material else ""
        historico_por_nombre[nombre_mat.lower().strip()] = pm

    # 2. Procesar ítems de la IA y fusionar con histórico
    secciones_dict: dict[str, SeccionCosto] = {}
    nombres_ya_agregados: set[str] = set()

    # Flatten de items de IA con su sección
    items_ia: list[tuple[str, dict]] = []
    for seccion_ia in (estructura_ia or []):
        nombre_seccion = seccion_ia.get("seccion", SECCION_DEFAULT).upper()
        for item in seccion_ia.get("items", []):
            items_ia.append((nombre_seccion, item))

    for seccion_nombre, item_ia in items_ia:
        nombre_mat = item_ia.get("nombre_material", "").strip()
        if not nombre_mat:
            continue

        nombre_norm = nombre_mat.lower().strip()

        # Detectar sección real.
        # Si la IA ya asignó una sección válida, respetarla.
        # "MANO DE OBRA" nunca se reclasifica por keyword porque sus
        # líneas contienen palabras como "ebanisteria", "tapiceria", etc.
        if seccion_nombre in SECCION_KEYWORDS:
            seccion_final = seccion_nombre
        else:
            seccion_detectada = _detectar_seccion(nombre_mat)
            seccion_final = seccion_detectada

        # Buscar en inventario
        mat_inv = _buscar_material_inventario(db, nombre_mat)

        # Buscar en histórico
        pm_hist: Optional[ProductoMaterial] = None
        for hist_nombre, pm in historico_por_nombre.items():
            if _similitud_nombre(nombre_norm, hist_nombre) >= 0.65:
                pm_hist = pm
                break

        # Calcular cantidad
        cantidad_ia = float(item_ia.get("cantidad_sugerida") or 1.0)

        if pm_hist:
            # Escalar la cantidad histórica según nuevas dimensiones
            cantidad_escalada = _escalar_cantidad(
                pm_hist, ancho_base_hist, largo_base_hist, ancho_nuevo, largo_nuevo,
                alto_base_hist, alto_nuevo,
            )
            cantidad_final = float(cantidad_escalada)
            fuente = "ia+historico"
            razon = item_ia.get("razon", f"Componente estándar de {attrs.tipo_mueble}")
        else:
            # Sin receta histórica: reescalar la cantidad que propuso la IA
            # (calculada para dimensiones_referencia) hacia las medidas reales.
            cantidad_final = _reescalar_cantidad_ia(
                cantidad_ia,
                unidad=item_ia.get("unidad", "UN"),
                dimensiones_referencia=dimensiones_referencia,
                ancho_nuevo=nuevo_ancho,
                largo_nuevo=nuevo_largo,
                alto_nuevo=nuevo_alto,
            )
            fuente = "ia"
            razon = item_ia.get("razon", "Propuesto por análisis de imagen")

        # Precio del inventario
        costo_unit = 0.0
        precio_pendiente = True
        material_id = None
        unidad = item_ia.get("unidad", "UN")

        if mat_inv:
            costo_unit = float(mat_inv.costo_base)
            precio_pendiente = False
            material_id = mat_inv.id
            unidad = mat_inv.unidad_medida.nombre if mat_inv.unidad_medida else unidad

        # Crear línea
        linea = LineaCosto(
            nombre=nombre_mat.upper(),
            cantidad=cantidad_final,
            unidad=unidad,
            costo_unitario=costo_unit,
            material_id=material_id,
            precio_pendiente=precio_pendiente,
            razon=razon,
            fuente=fuente,
            es_opcional=bool(item_ia.get("es_opcional", False)),
            activo=True,
            seccion=seccion_final,
        )

        if seccion_final not in secciones_dict:
            secciones_dict[seccion_final] = SeccionCosto(seccion_final)
        secciones_dict[seccion_final].items.append(linea)
        nombres_ya_agregados.add(nombre_norm)

    # 3. Agregar materiales del histórico que la IA no mencionó
    for pm in receta_historica:
        if not pm.material:
            continue
        nombre_mat = pm.material.nombre
        nombre_norm = nombre_mat.lower().strip()

        # Ya fue procesado por la IA
        if any(_similitud_nombre(nombre_norm, n) >= 0.65 for n in nombres_ya_agregados):
            continue

        # Nocheros: poner en su sección, marcar como opcional
        es_nochero = (pm.observaciones or "").upper().find("NOCHERO") >= 0
        seccion_final = "NOCHEROS" if es_nochero else _detectar_seccion(nombre_mat)

        cantidad_escalada = float(_escalar_cantidad(
            pm, ancho_base_hist, largo_base_hist, ancho_nuevo, largo_nuevo,
            alto_base_hist, alto_nuevo,
        ))

        costo_unit = float(pm.material.costo_base) if pm.material else 0.0
        material_id = pm.material_id

        linea = LineaCosto(
            nombre=nombre_mat.upper(),
            cantidad=cantidad_escalada,
            unidad=pm.material.unidad_medida.nombre if pm.material and pm.material.unidad_medida else "UN",
            costo_unitario=costo_unit,
            material_id=material_id,
            precio_pendiente=False,
            razon="Incluido en estructura histórica similar",
            fuente="historico",
            es_opcional=es_nochero,
            activo=not es_nochero,  # nocheros desactivados por defecto
            seccion=seccion_final,
            observaciones_historico=pm.observaciones,
        )

        if seccion_final not in secciones_dict:
            secciones_dict[seccion_final] = SeccionCosto(seccion_final)
        secciones_dict[seccion_final].items.append(linea)
        nombres_ya_agregados.add(nombre_norm)

    # 4. Aplicar las respuestas del vendedor a las preguntas de la IA.
    #    Ajusta secciones/líneas/multipladores según lo que el vendedor confirmó.
    if respuestas:
        _aplicar_respuestas(db, secciones_dict, respuestas, attrs)

    # 5. Ordenar secciones según SECCIONES_ORDEN y serializar
    secciones_ordenadas: list[SeccionCosto] = []
    for nombre in SECCIONES_ORDEN:
        if nombre in secciones_dict:
            secciones_ordenadas.append(secciones_dict[nombre])
    # Secciones que la IA propuso pero no están en el orden estándar → OTROS
    otros = SeccionCosto("OTROS")
    for nombre, sec in secciones_dict.items():
        if nombre not in SECCIONES_ORDEN:
            for item in sec.items:
                item.seccion = "OTROS"
                otros.items.append(item)
    if otros.items:
        secciones_ordenadas.append(otros)

    secciones_out = [s.to_dict() for s in secciones_ordenadas]

    # 6. Resumen de totales
    materiales_sin_precio = sum(
        1 for s in secciones_ordenadas
        for item in s.items
        if item.precio_pendiente and item.activo
    )

    costo_materiales = sum(s.subtotal for s in secciones_ordenadas)

    # Calcular desglose completo ERP
    from decimal import Decimal as D
    costo_mat_dec = D(str(costo_materiales))
    pct_mo_dec = D(str(pct_mano_obra)) / D("100")
    pct_g_dec = D(str(pct_gastos)) / D("100")
    costo_mo = costo_mat_dec * pct_mo_dec
    costo_g = costo_mat_dec * pct_g_dec
    costo_prod = costo_mat_dec + costo_mo + costo_g
    precio_sin_iva = costo_prod * (D("1") + D(str(ganancia_porcentaje)) / D("100"))
    precio_con_iva = precio_sin_iva * (D("1") + D(str(iva_porcentaje)) / D("100"))

    resumen = {
        "costo_materiales": float(round(costo_mat_dec, 2)),
        "costo_mano_obra": float(round(costo_mo, 2)),
        "costo_gastos": float(round(costo_g, 2)),
        "costo_produccion": float(round(costo_prod, 2)),
        "ganancia_porcentaje": float(ganancia_porcentaje),
        "precio_sin_iva": float(round(precio_sin_iva, 2)),
        "iva_porcentaje": float(iva_porcentaje),
        "precio_con_iva": float(round(precio_con_iva, 2)),
        "total_items": sum(len(s.items) for s in secciones_ordenadas),
        "total_activos": sum(
            1 for s in secciones_ordenadas
            for item in s.items
            if item.activo
        ),
    }

    return {
        "producto_base_id": mejor_similar.producto_id if mejor_similar else None,
        "producto_base_nombre": mejor_similar.nombre if mejor_similar else None,
        "score_similitud": mejor_similar.score if mejor_similar else 0.0,
        "secciones": secciones_out,
        "materiales_sin_precio": materiales_sin_precio,
        "resumen": resumen,
    }


# ---------------------------------------------------------------------------
# Escalar cantidad histórica
# ---------------------------------------------------------------------------

def _escalar_cantidad(
    pm: ProductoMaterial,
    ancho_base: Decimal,
    largo_base: Decimal,
    ancho_nuevo: Decimal,
    largo_nuevo: Decimal,
    alto_base: Optional[Decimal] = None,
    alto_nuevo: Optional[Decimal] = None,
) -> Decimal:
    """Escala la cantidad base del material según el tipo de escala."""
    tipo = (pm.tipo_escala or "FIJO").upper()
    cantidad = pm.cantidad_base or Decimal("0")

    if tipo == "FIJO":
        return cantidad

    if tipo == "LINEAL":
        if largo_base and largo_base > 0:
            return (cantidad * largo_nuevo / largo_base).quantize(Decimal("0.0001"))
        return cantidad

    if tipo == "AREA":
        area_base = ancho_base * largo_base
        area_nueva = ancho_nuevo * largo_nuevo
        if area_base and area_base > 0:
            return (cantidad * area_nueva / area_base).quantize(Decimal("0.0001"))
        return cantidad

    if tipo == "VOLUMEN":
        # Costo proporcional al volumen (ancho × largo × alto).
        # Se usa cuando el material escala con la tridimensionalidad real
        # (ej. espuma, rellenos, estructuras internas).
        vol_base = ancho_base * largo_base
        vol_nuevo = ancho_nuevo * largo_nuevo
        if alto_base and alto_nuevo and alto_base > 0:
            vol_base = vol_base * alto_base
            vol_nuevo = vol_nuevo * alto_nuevo
        if vol_base and vol_base > 0:
            return (cantidad * vol_nuevo / vol_base).quantize(Decimal("0.0001"))
        return cantidad

    if tipo == "ESPACIADO":
        if pm.distancia_pauta_cm and pm.distancia_pauta_cm > 0:
            perimetro = 2 * (largo_nuevo + ancho_nuevo) * 100  # a cm
            n = perimetro / pm.distancia_pauta_cm
            tornillos = pm.tornillos_por_pieza or 1
            return Decimal(str(round(float(n) * tornillos, 0)))
        return cantidad

    if tipo == "POR_RANGO":
        rangos = pm.rangos or []
        for rango in rangos:
            if largo_nuevo <= Decimal(str(rango.get("max", 999))):
                return Decimal(str(rango.get("cantidad", cantidad)))
        return cantidad

    return cantidad


# ---------------------------------------------------------------------------
# Reescalar cantidad IA sin receta histórica
# ---------------------------------------------------------------------------

def _reescalar_cantidad_ia(
    cantidad_ia: float,
    unidad: str = "UN",
    dimensiones_referencia: Optional[dict] = None,
    ancho_nuevo: Optional[float] = None,
    largo_nuevo: Optional[float] = None,
    alto_nuevo: Optional[float] = None,
) -> float:
    """
    Reescala la cantidad que propuso la IA hacia las medidas reales del proyecto.

    La IA calcula cantidades asumiendo unas dimensiones de referencia
    (dimensiones_referencia). Si el vendedor indicó otras medidas, las
    cantidades de materiales que escalan (línea, superficie, volumen) deben
    ajustarse proporcionalmente; las piezas (UN) y herrajes se mantienen.

    Unidades lineales/superficie (M, M2) escalan; piezas (UN) no escalan.
    """
    if not cantidad_ia or cantidad_ia <= 0:
        return cantidad_ia or 1.0

    unidad_norm = (unidad or "UN").upper()
    ref = dimensiones_referencia or {}
    ancho_ref = _as_float(ref.get("ancho"))
    largo_ref = _as_float(ref.get("largo"))
    alto_ref = _as_float(ref.get("alto"))

    tiene_ref = ancho_ref and largo_ref
    tiene_nuevo = (ancho_nuevo or 0) > 0 and (largo_nuevo or 0) > 0

    if not tiene_ref or not tiene_nuevo:
        return round(cantidad_ia, 4)

    # Escala por longitud
    if unidad_norm in ("M", "ML", "L"):
        if largo_ref > 0:
            return round(cantidad_ia * largo_nuevo / largo_ref, 4)
        return round(cantidad_ia, 4)

    # Escala por superficie (ancho × largo)
    if unidad_norm in ("M2", "MT2", "PIEZA2", "PAQUETE"):
        area_ref = ancho_ref * largo_ref
        area_nueva = ancho_nuevo * largo_nuevo
        if area_ref > 0:
            return round(cantidad_ia * area_nueva / area_ref, 4)
        return round(cantidad_ia, 4)

    # Escala por volumen (ancho × largo × alto)
    if unidad_norm in ("M3", "MT3"):
        vol_ref = ancho_ref * largo_ref * (alto_ref or 1)
        vol_nueva = ancho_nuevo * largo_nuevo * (alto_nuevo or alto_ref or 1)
        if vol_ref > 0:
            return round(cantidad_ia * vol_nueva / vol_ref, 4)
        return round(cantidad_ia, 4)

    # Piezas y herrajes: no escalan por dimensiones (se repiten 1:1)
    return round(cantidad_ia, 4)


def _as_float(valor) -> Optional[float]:
    """Convierte un valor (número o str) a float sin lanzar."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Aplicar respuestas del vendedor a las preguntas de la IA
# ---------------------------------------------------------------------------

_TERMINOS_TABLERO = ("mdf", "melamina", "tablero", "madera", "triplex", "aglomerado")

# clave de respuesta -> (sección destino, términos de búsqueda para localizar líneas)
_RESPUESTAS_SECCION = {
    "tiene_tapizado": ("TAPICERÍA", ("tela", "tapiz", "espuma", "foam", "cuero", "polipiel")),
    "tiene_espuma": ("TAPICERÍA", ("espuma", "foam")),
    "tiene_vidrio": ("TERMINACIÓN", ("vidrio",)),
    "tiene_metal": ("HERRAJES", ("metal", "perfil metal", "angulo", "ángulo")),
    "tiene_led": ("ILUMINACIÓN", ("led", "luz", "bombillo")),
    "tiene_espejos": ("TERMINACIÓN", ("espejo",)),
}

# acabado confirmado -> término de material a garantizar en PINTURA
_ACABADO_TERMINO = {
    "pintura": "pintura",
    "laca": "laca",
    "barniz": "barniz",
    "natural": "sellador",
    "tinte": "tinte",
    "duco": "pintura",
}

# piezas por proceso de fabricación -> (nombre de línea, término de búsqueda)
_PIEZAS_PROCESO = {
    "piezas_cnc": ("CORTE CNC", "corte"),
    "piezas_torno": ("TORNEADO", "torno"),
    "piezas_doblado": ("DOBLADO DE METAL", "doblado"),
    "piezas_curvas": ("PIEZAS CURVAS", "curvado"),
}


def _normalizar_respuesta(valor) -> str:
    """Normaliza el valor de una respuesta a string en minúsculas."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "si" if valor else "no"
    if isinstance(valor, (int, float)):
        return str(valor)
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor).lower()
    return str(valor).strip().lower()


def _es_si(valor) -> bool:
    return _normalizar_respuesta(valor) in ("si", "sí", "true", "1", "yes", "verdadero")


def _es_no(valor) -> bool:
    return _normalizar_respuesta(valor) in ("no", "false", "0", "ninguno", "ninguna", "n/a")


def _iter_lineas(secciones_dict: dict[str, SeccionCosto]):
    for sec in secciones_dict.values():
        for linea in sec.items:
            yield linea


def _buscar_lineas_por_termino(
    secciones_dict: dict[str, SeccionCosto],
    terminos: tuple[str, ...],
    seccion: Optional[str] = None,
) -> list[LineaCosto]:
    """Devuelve líneas cuyo nombre contenga alguno de los términos."""
    res: list[LineaCosto] = []
    for nombre_sec, sec in secciones_dict.items():
        if seccion and nombre_sec != seccion:
            continue
        for linea in sec.items:
            nombre = linea.nombre.lower()
            if any(t in nombre for t in terminos):
                res.append(linea)
    return res


def _agregar_linea(
    secciones_dict: dict[str, SeccionCosto],
    seccion: str,
    nombre: str,
    cantidad: float,
    unidad: str,
    razon: str,
    db: Optional[Session] = None,
    precio_pendiente: bool = True,
    terminos_inventario: Optional[tuple[str, ...]] = None,
) -> None:
    """Agrega una línea a una sección, buscando precio real en inventario si se puede."""
    costo_unit = 0.0
    material_id = None
    if db and terminos_inventario:
        for termino in terminos_inventario:
            mat = _buscar_material_inventario(db, termino)
            if mat:
                costo_unit = float(mat.costo_base)
                precio_pendiente = False
                material_id = mat.id
                unidad = mat.unidad_medida.nombre if mat.unidad_medida else unidad
                break

    linea = LineaCosto(
        nombre=nombre,
        cantidad=cantidad,
        unidad=unidad,
        costo_unitario=costo_unit,
        material_id=material_id,
        precio_pendiente=precio_pendiente,
        razon=razon,
        fuente="respuesta",
        activo=True,
        seccion=seccion,
    )
    if seccion not in secciones_dict:
        secciones_dict[seccion] = SeccionCosto(seccion)
    secciones_dict[seccion].items.append(linea)


def _aplicar_respuestas(
    db: Session,
    secciones_dict: dict[str, SeccionCosto],
    respuestas: dict,
    attrs: FurnitureAttributes,
) -> None:
    """
    Aplica las respuestas del vendedor a las preguntas dinámicas de la IA.

    Cada clave en `respuestas` corresponde a un campo del VOCABULARIO_PREGUNTAS.
    Las respuestas pueden:
      - Corregir el material principal y su espesor (afecta precio real)
      - Activar/desactivar secciones completas (tapizado, vidrio, LED, espejos…)
      - Agregar procesos de fabricación (CNC, torno, doblado, curvas)
      - Escalar estructuras reforzadas y partes ocultas
    """
    respuestas = {k: v for k, v in (respuestas or {}).items() if k in VOCABULARIO_PREGUNTAS}
    if not respuestas:
        return

    # --- Material principal -------------------------------------------------
    valor = _normalizar_respuesta(respuestas.get("material_principal"))
    if valor and valor not in ("si", "no", "ninguno"):
        lineas_tablero = _buscar_lineas_por_termino(secciones_dict, _TERMINOS_TABLERO)
        if lineas_tablero:
            # Localizar la línea más representativa (el tablero principal)
            target = max(lineas_tablero, key=lambda l: len(l.nombre))
            target.nombre = valor.upper()
            target.razon = f"Material principal confirmado por vendedor: {valor}"
            target.fuente = "respuesta"
            mat = _buscar_material_inventario(db, valor)
            if mat:
                target.material_id = mat.id
                target.costo_unitario = float(mat.costo_base)
                target.precio_pendiente = False
                target.unidad = mat.unidad_medida.nombre if mat.unidad_medida else target.unidad
            target.recalcular()
        else:
            _agregar_linea(
                secciones_dict, "EBANISTERÍA", valor.upper(), 1.0, "UN",
                f"Material principal confirmado por vendedor: {valor}",
                db=db, terminos_inventario=(valor,),
            )

    # --- Espesor de tablero -------------------------------------------------
    espesor = _normalizar_respuesta(respuestas.get("espesor_tablero"))
    if espesor:
        if espesor.isdigit():
            espesor = f"{espesor}mm"
        if "mm" in espesor or espesor.isdigit():
            lineas_tablero = _buscar_lineas_por_termino(secciones_dict, _TERMINOS_TABLERO)
            for linea in lineas_tablero:
                if espesor not in linea.nombre.lower():
                    linea.nombre = f"{linea.nombre} {espesor.upper()}"
                    linea.razon = f"Espesor de tablero confirmado: {espesor}"
                mat = _buscar_material_inventario(db, linea.nombre)
                if mat:
                    linea.material_id = mat.id
                    linea.costo_unitario = float(mat.costo_base)
                    linea.precio_pendiente = False
                    linea.unidad = mat.unidad_medida.nombre if mat.unidad_medida else linea.unidad
                linea.recalcular()

    # --- Acabado ------------------------------------------------------------
    acabado = _normalizar_respuesta(respuestas.get("acabado"))
    if acabado and acabado in _ACABADO_TERMINO:
        termino = _ACABADO_TERMINO[acabado]
        existentes = _buscar_lineas_por_termino(secciones_dict, (termino,), seccion="PINTURA")
        if not existentes:
            _agregar_linea(
                secciones_dict, "PINTURA", termino.upper(), 1.0, "UN",
                f"Acabado confirmado por vendedor: {acabado}",
                db=db, terminos_inventario=(termino,),
            )

    # --- Características sí/no por sección ----------------------------------
    for clave, (seccion, terminos) in _RESPUESTAS_SECCION.items():
        if clave not in respuestas:
            continue
        if _es_no(respuestas[clave]):
            # Desactivar las líneas de esa sección que la IA propuso
            for linea in _buscar_lineas_por_termino(secciones_dict, terminos, seccion=seccion):
                linea.activo = False
                linea.razon = f"Desactivado: vendedor confirmó que no aplica ({clave})"
        elif _es_si(respuestas[clave]):
            # Garantizar al menos una línea representativa si la IA no propuso nada
            if not _buscar_lineas_por_termino(secciones_dict, terminos, seccion=seccion):
                nombre_linea = terminos[0].upper() if terminos else seccion
                _agregar_linea(
                    secciones_dict, seccion, nombre_linea, 1.0, "UN",
                    f"Confirmado por vendedor: {clave}",
                    db=db, terminos_inventario=terminos,
                )

    # --- Herrajes -----------------------------------------------------------
    if "herrajes" in respuestas and _es_no(respuestas["herrajes"]):
        for linea in _buscar_lineas_por_termino(secciones_dict, ("jala", "jalón", "manija", "tirador", "cerradura", "bisagra"), seccion="HERRAJES"):
            linea.activo = False
            linea.razon = "Desactivado: vendedor confirmó que no lleva herrajes"

    # --- Estructura reforzada -----------------------------------------------
    if "estructura_reforzada" in respuestas and _es_si(respuestas["estructura_reforzada"]):
        for linea in _buscar_lineas_por_termino(secciones_dict, _TERMINOS_TABLERO + ("listones", "cabecero", "larguero", "travesaño")):
            linea.cantidad = round(linea.cantidad * 1.15, 4)
            linea.razon = f"{linea.razon} · estructura reforzada confirmada"
            linea.recalcular()

    # --- Procesos de fabricación (piezas CNC, torno, etc.) ------------------
    for clave, (nombre_linea, terminos) in _PIEZAS_PROCESO.items():
        if clave not in respuestas:
            continue
        cantidad_proceso = _as_float(respuestas[clave]) or 0.0
        if cantidad_proceso > 0:
            _agregar_linea(
                secciones_dict, "EBANISTERÍA", nombre_linea, cantidad_proceso, "PIEZA",
                f"{cantidad_proceso:g} piezas de {nombre_linea.lower()} confirmadas por vendedor",
            )

    # --- Partes ocultas ------------------------------------------------------
    if "partes_ocultas" in respuestas and _es_si(respuestas["partes_ocultas"]):
        _agregar_linea(
            secciones_dict, "EBANISTERÍA", "REFUERZO PARTES OCULTAS", 1.0, "UN",
            "Partes ocultas confirmadas por vendedor (refuerzos internos)",
        )

    # --- Medidas conocidas ---------------------------------------------------
    if "medidas_conocidas" in respuestas and _es_no(respuestas["medidas_conocidas"]):
        for linea in _iter_lineas(secciones_dict):
            if "estimada" not in linea.razon.lower():
                linea.razon = f"{linea.razon} · dimensiones estimadas por IA"


# ---------------------------------------------------------------------------
# Recalcular estructura editada por el vendedor
# ---------------------------------------------------------------------------

def recalculate_structure(
    db: Session,
    secciones_editadas: list[dict],
    ganancia_porcentaje: float = 40.0,
    iva_porcentaje: float = 0.0,
    pct_mano_obra: float = 15.0,
    pct_gastos: float = 10.0,
) -> dict:
    """
    Recalcula los totales de una estructura editada por el vendedor.

    Recibe las secciones con ítems (posiblemente con cantidades y precios
    modificados) y devuelve los mismos con totales actualizados.

    Si un ítem tiene material_id, refresca el precio del inventario.
    Si el ítem tiene precio_pendiente=True, usa el costo_unitario enviado por el frontend.
    """
    secciones_out = []
    costo_total = 0.0
    materiales_sin_precio = 0

    for seccion in secciones_editadas:
        items_out = []
        for item in seccion.get("items", []):
            material_id = item.get("material_id")
            costo_unit = float(item.get("costo_unitario", 0))
            precio_pendiente = bool(item.get("precio_pendiente", True))

            # Refrescar precio del inventario si tiene material_id
            if material_id and not precio_pendiente:
                mat = db.query(Material).filter(Material.id == material_id).first()
                if mat:
                    costo_unit = float(mat.costo_base)

            cantidad = float(item.get("cantidad", 0))
            costo_total_item = round(cantidad * costo_unit, 2) if item.get("activo", True) else 0.0

            if precio_pendiente and item.get("activo", True):
                materiales_sin_precio += 1

            if item.get("activo", True):
                costo_total += costo_total_item

            items_out.append({
                **item,
                "costo_unitario": costo_unit,
                "costo_total": costo_total_item,
            })

        subtotal = round(sum(
            i["costo_total"] for i in items_out if i.get("activo", True)
        ), 2)

        secciones_out.append({
            **seccion,
            "items": items_out,
            "subtotal": subtotal,
        })

    # Calcular desglose completo ERP
    from decimal import Decimal as D
    costo_mat_dec = D(str(costo_total))
    pct_mo_dec = D(str(pct_mano_obra)) / D("100")
    pct_g_dec = D(str(pct_gastos)) / D("100")
    costo_mo = costo_mat_dec * pct_mo_dec
    costo_g = costo_mat_dec * pct_g_dec
    costo_prod = costo_mat_dec + costo_mo + costo_g
    precio_sin_iva = costo_prod * (D("1") + D(str(ganancia_porcentaje)) / D("100"))
    precio_con_iva = precio_sin_iva * (D("1") + D(str(iva_porcentaje)) / D("100"))

    resumen = {
        "costo_materiales": float(round(costo_mat_dec, 2)),
        "costo_mano_obra": float(round(costo_mo, 2)),
        "costo_gastos": float(round(costo_g, 2)),
        "costo_produccion": float(round(costo_prod, 2)),
        "ganancia_porcentaje": float(ganancia_porcentaje),
        "precio_sin_iva": float(round(precio_sin_iva, 2)),
        "iva_porcentaje": float(iva_porcentaje),
        "precio_con_iva": float(round(precio_con_iva, 2)),
        "materiales_sin_precio": materiales_sin_precio,
    }

    return {
        "secciones": secciones_out,
        "materiales_sin_precio": materiales_sin_precio,
        "resumen": resumen,
    }
