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

import re
import unicodedata
import uuid
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Optional
from sqlalchemy.orm import Session, selectinload

from app.modules.productos.model import (
    Producto,
    ProductoMaterial,
    Material,
    MaterialSinonimo,
    SeccionProducto,
    ElementoSeccion,
    CostoProduccionSeccion,
)
from app.modules.productos import service as service_productos
from app.modules.quotes.similarity_engine import buscar_similares, SimilarityResult
from app.modules.quotes.atributos import FurnitureAttributes, VOCABULARIO_PREGUNTAS, ANATOMIA_POR_TIPO
from app.modules.productos.medidas_colchon import medidas_desde_nombre


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
    "TENDIDO": [
        "tendido", "somier", "colchonero", "base de cama", "liston de tendido",
        "listón de tendido", "soporte de colchon",
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
        "cola de pato", "colapato",
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
    "TENDIDO", "HERRAJES", "TERMINACIÓN",
    "NOCHEROS", "ILUMINACIÓN", "OTROS"
]

# Mapeo de la sección almacenada en la receta (sin acentos, del Excel)
# a la sección canónica del cotizador (con acentos).
# COLA_DE_PATO no tiene entrada: su técnica (doblado de tela) es labor de
# TERMINACIÓN y se mapea ahí explícitamente en _seccion_canonica.
SECCION_RECETA_A_CANONICA: dict[str, str] = {
    "EBANISTERIA": "EBANISTERÍA",
    "TENDIDO": "TENDIDO",
    "PINTURA": "PINTURA",
    "TAPICERIA": "TAPICERÍA",
    "TERMINACION": "TERMINACIÓN",
    "NOCHEROS": "NOCHEROS",
    "MANO_DE_OBRA": "MANO DE OBRA",
}

# Palabras que identifican líneas de MANO DE OBRA / pago a contratista.
# Estas líneas NO se matchean por fuzzy contra insumos físicos (evita
# "HECHURA" → "ENCHUFE") y NO bloquean el finalizado: su costo lo cubren
# los porcentajes de mano de obra del ERP. Nada se borra de la BD.
_LABOR_NOMBRE_KEYWORDS = (
    "hechura", "preparado", "tapizado", "montaje", "embalaje", "postura",
    "armado", "instalacion", "instalación", "mano de obra", "m.o",
    "pago al contratista", "tabulaci", "corte y pulida", "corte y npulida",
    "luis alfonso", "samblaste", "cola de pato", "colapato",
)
_LABOR_UNIDAD_KEYWORDS = (
    "con el 5%", "5% de m.o", "10% de m.o", "0.05", "pago al co",
    "mano de obra", "luis alfonso",
)


def _es_linea_labor(nombre: str, unidad: Optional[str] = None) -> bool:
    """True si la línea es mano de obra / pago a contratista (no un insumo físico)."""
    n = (nombre or "").lower()
    if any(kw in n for kw in _LABOR_NOMBRE_KEYWORDS):
        return True
    if unidad:
        u = (unidad or "").lower()
        if any(kw in u for kw in _LABOR_UNIDAD_KEYWORDS):
            return True
    return False


def _es_placeholder_matcheo(mat) -> bool:
    """True si el material es un placeholder que NO debe usarse para matchear.

    Excluye SOLO lo realmente inválido: materiales de prueba y filas-total.
    NO excluye líneas de mano de obra / contratistas (son costos reales).
    """
    n = (mat.nombre or "").lower().strip()
    if n.startswith("test"):
        return True
    if n.startswith(("total ", "subtotal ", "costo de ", "coste de ",
                     "gastos ", "gasos ", "materia prima", "precio ",
                     "ganancia ", "nombre del producto")):
        return True
    return False


def _nombre_prueba(nombre: str) -> bool:
    n = (nombre or "").lower().strip()
    return n.startswith(("test", "prueb"))


_ACCENT_MAP = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")


def _normn(valor: str) -> str:
    """Normaliza para comparar secciones: minúsculas, sin acentos, sin símbolos."""
    s = (valor or "").lower().translate(_ACCENT_MAP)
    return "".join(ch for ch in s if ch.isalnum())


def _base_seccion(nombre: Optional[str]) -> str:
    """Parte base de una sección (antes del paréntesis de la pieza)."""
    if not nombre:
        return SECCION_DEFAULT
    base = nombre.split("(")[0].strip()
    return base or nombre.strip()


def _es_seccion_valida(nombre: Optional[str]) -> bool:
    """True si la sección (con o sin pieza) corresponde a una sección conocida."""
    return _base_seccion(nombre) in SECCION_KEYWORDS


def _seccion_canonica(nombre: Optional[str]) -> str:
    """Convierte el nombre de una sección (del Excel jerárquico o de la receta)
    a la sección canónica del cotizador (con acentos), CONSERVANDO la pieza
    entre paréntesis cuando existe.

    Ej: "EBANISTERÍA (CAMA)" → EBANISTERÍA (CAMA) · "PINTURA (NOCHEROS)" →
        PINTURA (NOCHEROS) · "NOCHEROS EN CRUDO" → NOCHEROS ·
        "COLA_DE_PATO" / "COLAPATO" → TERMINACIÓN · None → EBANISTERÍA.
    """
    if not nombre:
        return SECCION_DEFAULT
    pieza = None
    m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", nombre.strip())
    if m:
        base, pieza = m.group(1).strip(), m.group(2).strip()
    else:
        base = nombre.strip()
    base = base or nombre.strip()

    bn = _normn(base)
    base_canonica = SECCION_DEFAULT
    if "colapato" in bn or "coladepato" in bn:
        # La "cola de pato" es una línea de labor de acabado: TERMINACIÓN
        base_canonica = "TERMINACIÓN"
    else:
        for can in SECCIONES_ORDEN:
            cn = _normn(can)
            if cn == bn or (len(cn) >= 5 and cn in bn):
                base_canonica = can
                break
        else:
            for clave, valor in SECCION_RECETA_A_CANONICA.items():
                cn = _normn(clave)
                if cn == bn or (len(cn) >= 5 and cn in bn):
                    base_canonica = valor
                    break

    if pieza:
        return f"{base_canonica} ({pieza.upper()})"
    return base_canonica


# Cargas eager para la receta completa de un producto (plana + jerárquica)
_RECETA_EAGER = (
    selectinload(Producto.materiales),
    selectinload(Producto.secciones)
    .selectinload(SeccionProducto.elementos)
    .selectinload(ElementoSeccion.material_normalizado),
)


def _linea_desde_elemento(el: ElementoSeccion):
    """Convierte un ElementoSeccion (estructura jerárquica del Excel) en una
    línea de receta equivalente a ProductoMaterial (tipo_escala FIJO)."""
    from types import SimpleNamespace
    mat = el.material_normalizado
    if not mat:
        return None
    return SimpleNamespace(
        material=mat,
        material_id=mat.id,
        cantidad_base=el.cantidad if el.cantidad is not None else Decimal("1"),
        tipo_escala="FIJO",
        seccion=_seccion_canonica(el.seccion.nombre if el.seccion else None),
        observaciones=el.observaciones or f"Sección: {el.seccion.nombre if el.seccion else ''}",
        unidad_receta=el.unidad_medida,
        costo_unitario_historico=el.precio_unitario,
        costo_total_historico=el.costo_subtotal,
        distancia_pauta_cm=None,
        tornillos_por_pieza=None,
        rangos=None,
    )


def _receta_historica_completa(producto: Producto) -> list:
    """Receta histórica completa de un producto: filas planas (ProductoMaterial)
    + elementos de la estructura jerárquica (la que se importó del Excel)."""
    lineas: list = list(producto.materiales)
    for sec in producto.secciones:
        for el in sec.elementos:
            linea = _linea_desde_elemento(el)
            if linea is not None:
                lineas.append(linea)
    return lineas


def _encontrar_referencia_por_tipo(db: Session, tipo_mueble: str, max_n: int = 1) -> list[Producto]:
    """Productos reales del tipo indicado para usar como referencia.

    Prioriza: tipo exacto en mueble_atributos → nombre contiene el tipo →
    más insumos (receta plana + estructura jerárquica del Excel).
    Excluye productos de prueba. Para "otro" devuelve [].
    """
    from app.modules.productos.model import MuebleAtributos
    tipo = (tipo_mueble or "otro").lower().strip()
    if tipo == "otro":
        return []

    base_ids: set = set()
    if tipo:
        atribs = db.query(MuebleAtributos).filter(MuebleAtributos.tipo_mueble == tipo).all()
        base_ids = {a.producto_id for a in atribs}

    productos = db.query(Producto).options(*_RECETA_EAGER).all()

    def con_insumos(p: Producto) -> bool:
        if any(pm.material_id for pm in p.materiales):
            return True
        return any(el.material_id_normalizado for sec in p.secciones for el in sec.elementos)

    # Solo productos que realmente coinciden con el tipo (por atributos o nombre)
    reales = [
        p for p in productos
        if not _nombre_prueba(p.nombre) and con_insumos(p)
        and (p.id in base_ids or tipo in (p.nombre or "").lower())
    ]
    if not reales:
        return []

    def puntuar(p: Producto) -> float:
        s = 0.0
        if p.id in base_ids:
            s += 3.0
        nombre = (p.nombre or "").lower()
        if tipo in nombre:
            s += 2.0
        n_insumos = len([m for m in p.materiales if m.material_id])
        n_insumos += sum(1 for sec in p.secciones for el in sec.elementos if el.material_id_normalizado)
        s += min(n_insumos / 50.0, 1.0)
        return s

    reales.sort(key=puntuar, reverse=True)
    return reales[:max_n]


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
        sugerencias: Optional[list[dict]] = None,
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
        self.sugerencias = sugerencias or []
        self.cantidad_ia_sugerida: Optional[float] = None
        self.cantidad_referencia: Optional[float] = None
        self.confianza_cantidad = "baja"

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
            "sugerencias": self.sugerencias,
            "cantidad_ia_sugerida": self.cantidad_ia_sugerida,
            "cantidad_referencia": self.cantidad_referencia,
            "confianza_cantidad": self.confianza_cantidad,
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


_NOMBRE_STOPWORDS = frozenset({"de", "del", "la", "el", "los", "las", "y", "en", "para"})
_TOKEN_ALIASES = {
    "lamina": "lam",
    "laminas": "lam",
    "people": "peope",
    "gazata": "cazata",
}
_PARENTESIS_VARIANTE = re.compile(r"\(\s*\d+\s*\)$")
_MEDIDA_COMPUESTA = re.compile(
    r"\b\d+(?:[.,]\d+)?(?:\s*[xX*]\s*\d+(?:[.,]\d+)?){1,3}\b"
)
_MEDIDA_FRACCION = re.compile(r"\b\d[\d.,]{2,}\s*/\s*\d[\d.,]{2,}\b")
_NUMERO_NOMBRE = re.compile(r"\d+(?:[.,]\d+)?")


def _normalizar_texto_material(nombre: str) -> str:
    texto = unicodedata.normalize("NFD", nombre or "")
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    texto = texto.lower().replace("½", "1/2")
    texto = re.sub(r"[\"'`´]", "", texto)
    texto = _PARENTESIS_VARIANTE.sub("", texto)
    texto = _MEDIDA_COMPUESTA.sub(" ", texto)
    texto = _MEDIDA_FRACCION.sub(" ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _partes_nombre_material(nombre: str) -> tuple[set[str], tuple[str, ...], str]:
    texto = _normalizar_texto_material(nombre)
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+(?:/[a-z0-9]+)?", texto):
        token = _TOKEN_ALIASES.get(token, token)
        if token not in _NOMBRE_STOPWORDS:
            tokens.add(token)
    numeros = tuple(_NUMERO_NOMBRE.findall(texto))
    return tokens, numeros, texto


def _similitud_nombre(a: str, b: str) -> float:
    """Compara nombres preservando espesores y tolerando especificaciones."""
    tokens_a, numeros_a, texto_a = _partes_nombre_material(a)
    tokens_b, numeros_b, texto_b = _partes_nombre_material(b)
    if not tokens_a or not tokens_b:
        return 0.0
    if texto_a == texto_b:
        return 1.0

    interseccion = len(tokens_a & tokens_b)
    dice = (2 * interseccion) / (len(tokens_a) + len(tokens_b))
    secuencia = SequenceMatcher(None, texto_a, texto_b).ratio()
    puntuacion = max(dice, secuencia)
    if numeros_a and numeros_b and numeros_a != numeros_b:
        return puntuacion * 0.35
    return puntuacion


def _partes_seccion(nombre: Optional[str]) -> tuple[str, str]:
    texto = _normalizar_texto_material(nombre or "")
    match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", texto)
    if not match:
        return texto, ""
    return match.group(1).strip(), match.group(2).strip()


def _compatibilidad_seccion(propuesta: str, historica: str) -> float:
    propuesta_base, propuesta_pieza = _partes_seccion(propuesta)
    historica_base, historica_pieza = _partes_seccion(historica)
    if not propuesta_base or not historica_base:
        return 0.0
    if propuesta_base == historica_base and propuesta_pieza == historica_pieza:
        return 1.0
    if propuesta_pieza and propuesta_pieza == historica_pieza:
        return 0.95
    if propuesta_base == historica_base:
        if not propuesta_pieza and historica_pieza in ("cama", "mesa", "sofa"):
            return 0.90
        if not historica_pieza:
            return 0.85
        return 0.78
    if propuesta_base == "nocheros" and historica_pieza == "nocheros":
        return 0.95
    return 0.0


def _buscar_linea_historica(
    receta: list,
    nombre_buscado: str,
    seccion_buscada: str,
    indices_usados: set[int],
) -> tuple[Optional[int], Optional[object]]:
    mejor: Optional[tuple[float, int, object]] = None
    for indice, linea in enumerate(receta):
        if indice in indices_usados or not linea.material:
            continue
        similitud = _similitud_nombre(nombre_buscado, linea.material.nombre)
        compatibilidad = _compatibilidad_seccion(seccion_buscada, linea.seccion)
        if similitud < 0.65 or compatibilidad == 0.0:
            continue
        puntuacion = similitud * compatibilidad
        candidato = (puntuacion, indice, linea)
        if mejor is None or candidato[0] > mejor[0]:
            mejor = candidato
    if mejor is None:
        return None, None
    return mejor[1], mejor[2]


def _es_linea_de_nocheros(seccion: str, observaciones: Optional[str] = None) -> bool:
    texto = f"{seccion} {observaciones or ''}".upper()
    return "NOCHERO" in texto


def _estructura_incluye_nocheros(attrs: FurnitureAttributes, estructura: list[dict]) -> bool:
    if attrs.tiene_nocheros():
        return True
    return any(
        "NOCHERO" in str(seccion.get("seccion", "")).upper()
        for seccion in estructura
    )


def _razon_con_referencia(razon: str, cantidad_ia: float, cantidad_historica: float) -> str:
    base = razon or "Componente de la receta histórica"
    if cantidad_ia <= 0 or cantidad_historica <= 0:
        return base
    diferencia = abs(cantidad_ia - cantidad_historica) / cantidad_historica
    if diferencia < 0.25:
        return base
    return f"{base} · receta real: {cantidad_historica:g}; IA: {cantidad_ia:g}"


# ---------------------------------------------------------------------------
# Estimador estadístico de cantidades (Fase 2 · Bloque 3)
# ---------------------------------------------------------------------------

# Unidades que escalan con el área del mueble (lineales/superficiales).
# Las demás (UN, CAJA, PAR, TIRA...) son cantidades fijas por pieza.
_UNIDADES_ESCALABLES_POR_AREA = frozenset({"ML", "M2", "M", "LAMINA", "LAM", "METROS", "LITROS"})

_ESTIMADOR_CACHE: dict[str, dict] = {}


def _clave_estimacion(material_norm: str, seccion_base: str, unidad_norm: str) -> str:
    return f"{material_norm}||{seccion_base}||{unidad_norm}"


def _area_producto(prod: Producto) -> Optional[float]:
    """Área real (ancho×largo) de un producto, desde el nombre o la BD.
    Devuelve None si es desconocida (dimensiones ficticias del importador)."""
    medidas = medidas_desde_nombre(prod.nombre)
    if medidas:
        return float(medidas["ancho"]) * float(medidas["largo"])
    ancho = prod.ancho_base
    largo = prod.largo_base
    if ancho and largo and (float(ancho) != 1.60 or float(largo) != 1.90):
        return float(ancho) * float(largo)
    return None


def _cargar_estimaciones_por_tipo(db: Session, tipo_mueble: str) -> dict:
    """Mediana estadística de cantidades por (material, sección, unidad)
    sobre TODAS las recetas históricas del mismo tipo de mueble.

    La IA propone → el histórico refina → y si no hay línea histórica en el
    producto base, la mediana de todos los hermanos del tipo da la mejor
    estimación posible sin entrenar un modelo.
    """
    import statistics

    tipo = (tipo_mueble or "otro").lower().strip()
    cache_key = f"tipo:{tipo}"
    if cache_key in _ESTIMADOR_CACHE:
        return _ESTIMADOR_CACHE[cache_key]

    from app.modules.productos.model import MuebleAtributos

    # Productos reales del tipo (misma lógica que la referencia por tipo)
    base_ids: set = set()
    if tipo and tipo != "otro":
        atribs = db.query(MuebleAtributos).filter(MuebleAtributos.tipo_mueble == tipo).all()
        base_ids = {a.producto_id for a in atribs}
    if tipo and tipo != "otro":
        base_ids |= {
            p.id for p in db.query(Producto).filter(Producto.nombre.ilike(f"%{tipo}%")).all()
        }
    if not base_ids:
        _ESTIMADOR_CACHE[cache_key] = {}
        return {}

    grupos: dict[str, list[float]] = {}
    areas: dict[str, list[float]] = {}

    def acumular(clave: str, cantidad: float, area: Optional[float]) -> None:
        if cantidad <= 0:
            return
        grupos.setdefault(clave, []).append(cantidad)
        if area:
            areas.setdefault(clave, []).append(area)

    # Líneas jerárquicas (elemento_seccion — la receta del Excel)
    filas = (
        db.query(ElementoSeccion, SeccionProducto, Producto)
        .join(SeccionProducto, SeccionProducto.id == ElementoSeccion.seccion_id)
        .join(Producto, Producto.id == SeccionProducto.producto_id)
        .filter(SeccionProducto.producto_id.in_(base_ids))
        .all()
    )
    for el, sec, prod in filas:
        if not el.material_id_normalizado or not el.cantidad:
            continue
        mat = el.material_normalizado
        if not mat or _es_placeholder_matcheo(mat):
            continue
        if _es_linea_labor(mat.nombre, el.unidad_medida or ""):
            continue
        clave = _clave_estimacion(
            _normalizar_texto_material(mat.nombre),
            _base_seccion(_seccion_canonica(sec.nombre)),
            _normalizar_unidad(el.unidad_medida or ""),
        )
        acumular(clave, float(el.cantidad), _area_producto(prod))

    # Líneas planas (producto_material)
    filas_planas = (
        db.query(ProductoMaterial, Producto)
        .join(Producto, Producto.id == ProductoMaterial.producto_id)
        .filter(ProductoMaterial.producto_id.in_(base_ids))
        .all()
    )
    for pm, prod in filas_planas:
        if not pm.material or not pm.cantidad_base:
            continue
        if _es_placeholder_matcheo(pm.material):
            continue
        if _es_linea_labor(pm.material.nombre, ""):
            continue
        clave = _clave_estimacion(
            _normalizar_texto_material(pm.material.nombre),
            _base_seccion(_seccion_canonica(pm.seccion or "")),
            _normalizar_unidad(pm.material.unidad_medida.abreviatura if pm.material.unidad_medida else ""),
        )
        acumular(clave, float(pm.cantidad_base), _area_producto(prod))

    resultado: dict[str, dict] = {}
    for clave, valores in grupos.items():
        if len(valores) < 3:
            continue  # con menos de 3 recetas la mediana no es confiable
        resultado[clave] = {
            "n": len(valores),
            "mediana": float(statistics.median(valores)),
            "min": min(valores),
            "max": max(valores),
            "area_mediana": float(statistics.median(areas[clave])) if areas.get(clave) else None,
        }

    _ESTIMADOR_CACHE[cache_key] = resultado
    return resultado


def _estimar_cantidad_estadistica(
    db: Session,
    tipo_mueble: str,
    nombre_material: str,
    seccion: str,
    unidad: str,
    ancho_nuevo: float,
    largo_nuevo: float,
) -> Optional[dict]:
    """Cantidad estimada por mediana estadística para un material SIN match
    en la receta del producto base. Escala por área cuando la unidad lo
    permite y el área objetivo difiere de la mediana de las recetas fuente."""
    estimaciones = _cargar_estimaciones_por_tipo(db, tipo_mueble)
    if not estimaciones:
        return None

    material_norm = _normalizar_texto_material(nombre_material)
    seccion_base = _base_seccion(_seccion_canonica(seccion))
    unidad_norm = _normalizar_unidad(unidad)

    # 1. Clave exacta (material, sección, unidad)
    est = estimaciones.get(_clave_estimacion(material_norm, seccion_base, unidad_norm))
    if not est:
        # 2. Material similar en la MISMA sección
        candidatos = [
            (k, v) for k, v in estimaciones.items()
            if k.split("||")[1] == seccion_base and v.get("n", 0) >= 3
        ]
        mejor_score = 0.60
        for clave, valor in candidatos:
            score = _similitud_nombre(material_norm, clave.split("||")[0])
            if score > mejor_score:
                mejor_score = score
                est = valor
    if not est:
        # 3. Material similar en CUALQUIER sección (la IA puede poner el
        # material en la sección equivocada; el material manda)
        candidatos = [
            (k, v) for k, v in estimaciones.items()
            if v.get("n", 0) >= 3
        ]
        mejor_score = 0.65
        for clave, valor in candidatos:
            score = _similitud_nombre(material_norm, clave.split("||")[0])
            if score > mejor_score:
                mejor_score = score
                est = valor
    if not est:
        return None

    cantidad = est["mediana"]
    escalada = False
    if (
        est.get("area_mediana")
        and ancho_nuevo > 0 and largo_nuevo > 0
        and unidad_norm in _UNIDADES_ESCALABLES_POR_AREA
    ):
        area_objetivo = ancho_nuevo * largo_nuevo
        factor = area_objetivo / est["area_mediana"]
        if factor < 0.8 or factor > 1.25:
            cantidad = est["mediana"] * factor
            escalada = True

    if est["n"] >= 5:
        confianza = "alta"
    elif est["n"] >= 3:
        confianza = "media"
    else:
        confianza = "baja"

    return {
        "cantidad": round(cantidad, 4),
        "n": est["n"],
        "min": est["min"],
        "max": est["max"],
        "confianza": confianza,
        "escalada": escalada,
    }


def _buscar_material_inventario(
    db: Session,
    nombre_buscado: str,
    umbral: float = 0.60,
    solo_exacto: bool = False,
) -> Optional[Material]:
    """
    Busca el material más parecido al nombre dado en la tabla material
    y en la tabla material_sinonimo.

    Estrategia:
      1. Coincidencia exacta (normalizada)
      2. Coincidencia en sinónimos
      3. Similitud de cadena ≥ umbral (solo si solo_exacto=False)

    Retorna el Material con mayor similitud, o None si no hay match.
    Excluye placeholders (test_*, filas-total) que nunca deben matchear.
    """
    nombre_norm = nombre_buscado.lower().strip()

    # 1. Buscar todos los materiales
    todos: list[Material] = db.query(Material).filter(Material.activo == True).all()  # noqa: E712

    mejor_match: Optional[Material] = None
    mejor_score = 0.0

    for mat in todos:
        if _es_placeholder_matcheo(mat):
            continue
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

    if solo_exacto:
        # Para líneas de mano de obra: solo coincidencia exacta normalizada
        # o por sinónimo; sin fuzzy (evita "HECHURA" → "ENCHUFE").
        if mejor_match and (_similitud_nombre(nombre_norm, mejor_match.nombre) >= 0.98
                            or any(_similitud_nombre(nombre_norm, s.sinonimo) >= 0.98
                                   for s in db.query(MaterialSinonimo)
                                   .filter(MaterialSinonimo.material_id == mejor_match.id).all())):
            return mejor_match
        return None

    if mejor_score >= umbral:
        return mejor_match
    return None


# Variantes de unidades que la IA puede escribir → unidad canónica del ERP.
_UNIDADES_NORM: dict[str, str] = {
    "m2": "M2", "m²": "M2", "mt2": "M2", "metro2": "M2", "metros2": "M2",
    "metros cuadrados": "M2", "metro cuadrado": "M2",
    "m": "ML", "mt": "ML", "metro": "ML", "metros": "ML", "metro lineal": "ML",
    "metros lineales": "ML", "ml": "ML", "mlin": "ML",
    "m3": "M3", "m³": "M3", "mt3": "M3", "metros cubicos": "M3", "metro cubico": "M3",
    "un": "UN", "unds": "UN", "und": "UN", "unidad": "UN", "unidades": "UN", "pieza": "UN", "piezas": "UN", "pza": "UN", "pzs": "UN",
    "l": "L", "lt": "L", "litro": "L", "litros": "L",
    "kg": "KG", "kilo": "KG", "kilos": "KG", "kilogramo": "KG", "kilogramos": "KG",
    "hr": "HR", "hora": "HR", "horas": "HR", "h": "HR",
}


def _normalizar_unidad(unidad: str) -> str:
    """Normaliza variantes de unidad (M2/m2/metros cuadrados → M2, etc.)."""
    if not unidad:
        return "UN"
    clave = unidad.strip().lower()
    if clave in _UNIDADES_NORM:
        return _UNIDADES_NORM[clave]
    return unidad.strip().upper()


def _sugerir_materiales(db: Session, nombre_buscado: str, top: int = 3) -> list[dict]:
    """
    Devuelve los top-N materiales del inventario más parecidos al nombre dado,
    para que el vendedor los mapee con un clic (materiales "precio pendiente").
    """
    nombre_norm = nombre_buscado.lower().strip()
    materiales = (
        db.query(Material)
        .filter(Material.activo == True)  # noqa: E712
        .all()
    )
    puntuados = []
    for mat in materiales:
        if _es_placeholder_matcheo(mat):
            continue
        score = _similitud_nombre(nombre_norm, mat.nombre)
        for sin in db.query(MaterialSinonimo).filter(MaterialSinonimo.material_id == mat.id).all():
            score = max(score, _similitud_nombre(nombre_norm, sin.sinonimo))
        if score >= 0.30:
            puntuados.append((score, mat))

    puntuados.sort(key=lambda x: x[0], reverse=True)
    resultado = []
    for _, mat in puntuados[:top]:
        resultado.append({
            "id": mat.id,
            "nombre": mat.nombre,
            "costo_base": float(mat.costo_base),
            "unidad": mat.unidad_medida.nombre if mat.unidad_medida else None,
            "abreviatura": mat.unidad_medida.abreviatura if mat.unidad_medida else None,
        })
    return resultado


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
    impuesto_porcentaje: float = 7.0,
    pct_mano_obra: float = 15.0,
    pct_gastos: float = 10.0,
    top_n_similar: int = 3,
    producto_base_id: Optional[int] = None,
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
    producto_base_id : Si se indica, se usa ESE producto como receta base
                     (flujo manual sin visión IA) en lugar de la búsqueda de similares.

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

    # 1. Producto base: forzado por el usuario (modo manual) o el más similar
    receta_historica: list[ProductoMaterial] = []
    producto_base: Optional[Producto] = None
    ancho_base_hist = Decimal("1.60")
    largo_base_hist = Decimal("1.90")
    alto_base_hist: Optional[Decimal] = None
    score_base = 0.0
    escala_habilitada = False

    if producto_base_id is not None:
        producto_base = db.query(Producto).options(*_RECETA_EAGER).filter(Producto.id == producto_base_id).first()
        if not producto_base:
            raise ValueError(f"El producto base {producto_base_id} no existe.")
        score_base = 1.0
    else:
        # Auto-referencia por tipo de mueble (cama → camas reales). Solo se
        # usan productos que coinciden con el tipo; si no hay ninguno, NO se
        # fusiona un producto equivocado. Para tipo "otro" (sin tipo
        # conocido) se conserva la búsqueda de similares por atributos.
        por_tipo = _encontrar_referencia_por_tipo(db, attrs.tipo_mueble, max_n=1)
        if por_tipo:
            producto_base = por_tipo[0]
            score_base = 0.9
        elif not attrs.tipo_mueble or attrs.tipo_mueble == "otro":
            similares: list[SimilarityResult] = buscar_similares(db=db, attrs=attrs, top_n=top_n_similar)
            mejor_similar = similares[0] if similares else None
            if mejor_similar:
                producto_base = db.query(Producto).options(*_RECETA_EAGER).filter(
                    Producto.id == mejor_similar.producto_id
                ).first()
                score_base = float(mejor_similar.score) if mejor_similar else 0.0

    if producto_base:
        receta_historica = _receta_historica_completa(producto_base)
        alto_base_hist = producto_base.alto_base
        # Medidas REALES: primero del nombre (2X2 → 2.0x2.0, 1.60 → 1.60x1.90),
        # luego de la BD si NO son las ficticias del importador (1.60x1.90).
        # Si la base es desconocida, NO se escala: las cantidades del Excel
        # son la verdad absoluta.
        medidas_nombre = medidas_desde_nombre(producto_base.nombre)
        if medidas_nombre:
            ancho_base_hist = Decimal(str(medidas_nombre["ancho"]))
            largo_base_hist = Decimal(str(medidas_nombre["largo"]))
            escala_habilitada = True
        elif (
            producto_base.ancho_base is not None
            and (float(producto_base.ancho_base) != 1.60 or float(producto_base.largo_base or 0) != 1.90)
        ):
            ancho_base_hist = producto_base.ancho_base
            largo_base_hist = producto_base.largo_base or Decimal("1.90")
            escala_habilitada = True
        else:
            escala_habilitada = False

    ancho_nuevo = Decimal(str(nuevo_ancho))
    largo_nuevo = Decimal(str(nuevo_largo))
    alto_nuevo = Decimal(str(nuevo_alto)) if nuevo_alto else None

    # 2. Procesar ítems de la IA y fusionar con histórico
    secciones_dict: dict[str, SeccionCosto] = {}
    indices_historico_usados: set[int] = set()
    incluye_nocheros = _estructura_incluye_nocheros(attrs, estructura_ia or [])

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

        es_labor = _es_linea_labor(nombre_mat, item_ia.get("unidad", ""))

        # Detectar sección real.
        # Si la IA ya asignó una sección válida (con o sin pieza, ej.
        # "PINTURA (NOCHEROS)"), respetarla completa.
        # "MANO DE OBRA" nunca se reclasifica por keyword porque sus
        # líneas contienen palabras como "ebanisteria", "tapiceria", etc.
        if _es_seccion_valida(seccion_nombre):
            seccion_final = seccion_nombre
        else:
            seccion_detectada = _detectar_seccion(nombre_mat)
            seccion_final = seccion_detectada

        # Buscar en inventario. Las líneas de labor (HECHURA, PREPARADO...)
        # solo matchean por coincidencia EXACTA: su costo lo cubren los %
        # de mano de obra y no deben engancharse con insumos físicos.
        mat_inv = _buscar_material_inventario(db, nombre_mat, solo_exacto=es_labor)

        # Buscar la línea histórica disponible más compatible por nombre y sección.
        indice_hist, pm_hist = _buscar_linea_historica(
            receta_historica,
            nombre_mat,
            seccion_final,
            indices_historico_usados,
        )
        if indice_hist is not None:
            indices_historico_usados.add(indice_hist)

        # Calcular cantidad
        cantidad_ia = float(item_ia.get("cantidad_sugerida") or 1.0)
        cantidad_estadistica = None

        if pm_hist:
            # Escalar la cantidad histórica según nuevas dimensiones.
            # Si la base es desconocida (escala_habilitada=False) la cantidad
            # del Excel se usa tal cual: es la verdad absoluta.
            cantidad_escalada = _escalar_cantidad(
                pm_hist, ancho_base_hist, largo_base_hist, ancho_nuevo, largo_nuevo,
                alto_base_hist, alto_nuevo, escala_habilitada=escala_habilitada,
            )
            cantidad_final = float(cantidad_escalada)
            fuente = "ia+historico"
            razon = _razon_con_referencia(
                item_ia.get("razon", ""), cantidad_ia, cantidad_final
            )
            if "(" in pm_hist.seccion and "(" not in seccion_final:
                seccion_final = pm_hist.seccion
        else:
            # Sin receta histórica en el producto base: usar la mediana
            # estadística del tipo de mueble como referencia de cantidad.
            estimacion = _estimar_cantidad_estadistica(
                db,
                attrs.tipo_mueble,
                nombre_mat,
                seccion_final,
                item_ia.get("unidad", "UN"),
                nuevo_ancho,
                nuevo_largo,
            )
            if estimacion:
                cantidad_est = estimacion["cantidad"]
                # La cantidad de la IA es la propuesta; la estadística refina
                cantidad_final = cantidad_est
                fuente = "ia+estadistico"
                razon = _razon_con_referencia(
                    item_ia.get("razon", "Estimado por mediana del tipo de mueble"),
                    cantidad_ia, cantidad_est,
                )
                linea_referencia = {
                    "cantidad": cantidad_est,
                    "confianza": estimacion["confianza"],
                    "n": estimacion["n"],
                }
                cantidad_estadistica = estimacion
            else:
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
                linea_referencia = None
                cantidad_estadistica = None

        # Precio del inventario
        costo_unit = 0.0
        # Las líneas de labor no bloquean el finalizado (su costo está en los %)
        precio_pendiente = False if es_labor else True
        material_id = None
        unidad = _normalizar_unidad(item_ia.get("unidad", "UN"))
        sugerencias: list[dict] = []

        material_precio = pm_hist.material if pm_hist else mat_inv
        if material_precio:
            precio_historico = getattr(pm_hist, "costo_unitario_historico", None) if pm_hist else None
            costo_unit = float(precio_historico or material_precio.costo_base)
            precio_pendiente = False
            material_id = material_precio.id
            unidad_receta = getattr(pm_hist, "unidad_receta", None) if pm_hist else None
            unidad = unidad_receta or (
                material_precio.unidad_medida.nombre
                if material_precio.unidad_medida else unidad
            )
        else:
            # Sin match: sugerir candidatos del inventario para mapear con 1 clic
            # (las líneas de labor no necesitan sugerencias: no son insumos físicos)
            if not es_labor:
                sugerencias = _sugerir_materiales(db, nombre_mat, top=3)

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
            sugerencias=sugerencias,
        )
        linea.cantidad_ia_sugerida = cantidad_ia
        if pm_hist:
            linea.cantidad_referencia = cantidad_final
            linea.confianza_cantidad = "alta"
        elif cantidad_estadistica:
            linea.cantidad_referencia = cantidad_estadistica["cantidad"]
            linea.confianza_cantidad = cantidad_estadistica["confianza"]
        else:
            linea.cantidad_referencia = None
            linea.confianza_cantidad = "baja"

        if seccion_final not in secciones_dict:
            secciones_dict[seccion_final] = SeccionCosto(seccion_final)
        secciones_dict[seccion_final].items.append(linea)
    # 3. Agregar materiales del histórico que la IA no mencionó
    for indice_hist, pm in enumerate(receta_historica):
        if indice_hist in indices_historico_usados:
            continue
        if not pm.material:
            continue
        nombre_mat = pm.material.nombre

        # Nocheros: poner en su sección, marcar como opcional.
        # Los materiales históricos conservan la sección de SU receta
        # (como en el Excel, los herrajes/luces viven en TERMINACIÓN).
        seccion_final = _seccion_canonica(pm.seccion)
        es_nochero = _es_linea_de_nocheros(seccion_final, pm.observaciones)
        if es_nochero and "NOCHERO" not in seccion_final.upper():
            seccion_final = "NOCHEROS"

        cantidad_escalada = float(_escalar_cantidad(
            pm, ancho_base_hist, largo_base_hist, ancho_nuevo, largo_nuevo,
            alto_base_hist, alto_nuevo, escala_habilitada=escala_habilitada,
        ))

        precio_historico = getattr(pm, "costo_unitario_historico", None)
        costo_unit = float(precio_historico or (pm.material.costo_base if pm.material else 0.0))
        material_id = pm.material_id

        linea = LineaCosto(
            nombre=nombre_mat.upper(),
            cantidad=cantidad_escalada,
            unidad=getattr(pm, "unidad_receta", None) or (
                pm.material.unidad_medida.nombre
                if pm.material and pm.material.unidad_medida else "UN"
            ),
            costo_unitario=costo_unit,
            material_id=material_id,
            precio_pendiente=False,
            razon="Incluido en estructura histórica similar",
            fuente="historico",
            es_opcional=es_nochero,
            activo=incluye_nocheros or not es_nochero,
            seccion=seccion_final,
            observaciones_historico=pm.observaciones,
        )
        linea.cantidad_referencia = cantidad_escalada
        linea.confianza_cantidad = "alta"

        if seccion_final not in secciones_dict:
            secciones_dict[seccion_final] = SeccionCosto(seccion_final)
        secciones_dict[seccion_final].items.append(linea)

    # 4. Aplicar las respuestas del vendedor a las preguntas de la IA.
    #    Ajusta secciones/líneas/multipladores según lo que el vendedor confirmó.
    if respuestas:
        _aplicar_respuestas(db, secciones_dict, respuestas, attrs)

    # 5. Ordenar secciones según SECCIONES_ORDEN (base) + pieza y serializar
    def _clave_orden(nombre_seccion: str) -> tuple:
        base = _base_seccion(nombre_seccion)
        try:
            idx = SECCIONES_ORDEN.index(base)
        except ValueError:
            idx = len(SECCIONES_ORDEN)  # desconocidas → al final (OTROS)
        pieza = ""
        m = re.search(r"\((.*?)\)", nombre_seccion)
        if m:
            pieza = m.group(1).strip()
        return (idx, pieza)

    secciones_ordenadas: list[SeccionCosto] = []
    para_otros: list[SeccionCosto] = []
    for nombre, sec in secciones_dict.items():
        if _base_seccion(nombre) in SECCIONES_ORDEN:
            secciones_ordenadas.append(sec)
        else:
            para_otros.append(sec)
    secciones_ordenadas.sort(key=lambda s: _clave_orden(s.nombre))
    # Secciones que la IA propuso pero no están en el orden estándar → OTROS
    otros = SeccionCosto("OTROS")
    for sec in para_otros:
        for item in sec.items:
            item.seccion = "OTROS"
            otros.items.append(item)
    if otros.items:
        secciones_ordenadas.append(otros)

    # 6. Agregar MO flat desde políticas de sección antes de serializar
    from decimal import Decimal as D

    # 6a. Fusionar secciones genéricas (sin pieza, ej. "EBANISTERÍA") con la
    # pieza principal de la misma base (ej. "EBANISTERÍA (CAMA)") para no
    # duplicar la política de mano de obra cuando la IA no distingue piezas.
    bases_con_pieza = {
        _base_seccion(s.nombre) for s in secciones_ordenadas if "(" in s.nombre
    }
    if bases_con_pieza:
        para_fusionar = [
            s for s in secciones_ordenadas
            if "(" not in s.nombre and _base_seccion(s.nombre) in bases_con_pieza
        ]
        for sec_gen in para_fusionar:
            principal = next(
                s for s in secciones_ordenadas
                if _base_seccion(s.nombre) == _base_seccion(sec_gen.nombre) and "(" in s.nombre
            )
            for item in sec_gen.items:
                item.seccion = principal.nombre
                principal.items.append(item)
            secciones_ordenadas.remove(sec_gen)

    cps_by_nombre: dict[str, list[CostoProduccionSeccion]] = {}
    cps_by_base: dict[str, list[tuple[int, list[CostoProduccionSeccion]]]] = {}
    costo_flat_mo = D("0")
    if producto_base:
        sps = db.query(SeccionProducto).filter(
            SeccionProducto.producto_id == producto_base.id
        ).options(selectinload(SeccionProducto.costos_produccion)).all()
        for sp in sps:
            cps_by_nombre.setdefault(sp.nombre, []).extend(list(sp.costos_produccion))
            cps_by_base.setdefault(_base_seccion(sp.nombre), []).append(
                (sp.orden or 0, list(sp.costos_produccion))
            )

    if cps_by_nombre:
        seccion_mo_creada = False
        for sec_obj in secciones_ordenadas:
            cps_list = cps_by_nombre.get(sec_obj.nombre)
            if cps_list is None:
                # Fallback: sección genérica sin pieza (ej. "EBANISTERÍA") →
                # tomar SOLO la política de la pieza principal (orden menor),
                # no todas las piezas con la misma base (evita duplicar MO).
                grupos = sorted(cps_by_base.get(_base_seccion(sec_obj.nombre), []), key=lambda g: g[0])
                cps_list = grupos[0][1] if grupos else []
            for cps in cps_list:
                if not cps.costo_base or cps.costo_base <= 0:
                    continue
                cps_amount = D(str(cps.costo_base))
                if cps_amount <= 0:
                    continue
                costo_flat_mo += cps_amount
                labor_line = LineaCosto(
                    nombre=f"[MO] {cps.nombre}".upper(),
                    cantidad=1.0,
                    unidad="Global",
                    costo_unitario=float(cps_amount),
                    material_id=None,
                    precio_pendiente=False,
                    razon="Mano de obra flat por política de sección",
                    fuente="politica",
                    es_opcional=False,
                    activo=True,
                    seccion=sec_obj.nombre,
                )
                labor_line.cantidad_referencia = 1.0
                labor_line.confianza_cantidad = "alta"
                sec_obj.items.append(labor_line)
                seccion_mo_creada = True
        if seccion_mo_creada:
            secciones_ordenadas.sort(key=lambda s: _clave_orden(s.nombre))

    secciones_out = [s.to_dict() for s in secciones_ordenadas]

    # 7. Resumen de totales
    materiales_sin_precio = sum(
        1 for s in secciones_ordenadas
        for item in s.items
        if item.precio_pendiente and item.activo
    )
    costo_materiales = sum(
        item.costo_total
        for s in secciones_ordenadas
        for item in s.items
        if item.activo and item.fuente != "politica"
    )

    # Desglose ERP: ancla a precio_costo_base (ya incluye MO y gastos) con
    # escala proporcional por área; solo si no hay ancla se calcula desde
    # materiales + MO flat + %.
    costo_mat_dec = D(str(costo_materiales))
    area_base = ancho_base_hist * largo_base_hist
    area_nueva = ancho_nuevo * largo_nuevo
    dims_iguales = abs(area_nueva - area_base) < D("0.001")

    pct_mo_dec = D(str(pct_mano_obra)) / D("100")
    pct_g_dec = D(str(pct_gastos)) / D("100")

    if producto_base and producto_base.precio_costo_base:
        # El ancla puede estar en la moneda del producto (reventa en USD): se
        # normaliza a COP (moneda base del ERP) antes de escalarla por área.
        ref_cop = service_productos.convertir_a_moneda_base(
            db, producto_base.moneda_id, float(producto_base.precio_costo_base)
        )
        ref_base = D(str(ref_cop or 0))
        if dims_iguales:
            costo_prod = ref_base
        elif area_base > 0 and ref_base > 0:
            costo_prod = ref_base * (area_nueva / area_base)
        else:
            costo_prod = costo_mat_dec
        costo_mo = costo_flat_mo
        costo_g = costo_mat_dec * pct_g_dec
    else:
        base_mo = costo_mat_dec + costo_flat_mo
        costo_mo = base_mo * pct_mo_dec
        costo_g = costo_mat_dec * pct_g_dec
        costo_prod = costo_mat_dec + costo_flat_mo + costo_mo + costo_g
    # a = costo_producción × (1 + impuesto%); b = a × (1 + ganancia%)
    monto_imp = round(costo_prod * (D(str(impuesto_porcentaje)) / D("100")), 2)
    base_imp = round(costo_prod + monto_imp, 2)
    precio_sin_iva = round(base_imp * (D("1") + D(str(ganancia_porcentaje)) / D("100")), 2)
    precio_con_iva = round(precio_sin_iva * (D("1") + D(str(iva_porcentaje)) / D("100")), 2)

    resumen = {
        "costo_materiales": float(round(costo_mat_dec, 2)),
        "costo_mano_obra": float(round(costo_mo, 2)),
        "costo_gastos": float(round(costo_g, 2)),
        "costo_produccion": float(round(costo_prod, 2)),
        "impuesto_porcentaje": float(impuesto_porcentaje),
        "impuestos": float(monto_imp),
        "base_con_impuestos": float(base_imp),
        "ganancia_porcentaje": float(ganancia_porcentaje),
        "precio_sin_iva": float(precio_sin_iva),
        "iva_porcentaje": float(iva_porcentaje),
        "precio_con_iva": float(precio_con_iva),
        "total_items": sum(len(s.items) for s in secciones_ordenadas),
        "total_activos": sum(
            1 for s in secciones_ordenadas
            for item in s.items
            if item.activo
        ),
    }

    # 7. Validación post-import: secciones faltantes según anatomía + desviación
    secciones_faltantes: list[str] = []
    anatomia = ANATOMIA_POR_TIPO.get(attrs.tipo_mueble or "otro")
    if anatomia:
        # Validación a nivel de sección BASE (la pieza no importa aquí)
        presentes = {_base_seccion(s.nombre) for s in secciones_ordenadas}
        secciones_faltantes = [
            sec for sec in anatomia["secciones"]
            if sec not in presentes
        ]

    desviacion_vs_referencia: Optional[float] = None
    advertencias: list[str] = []
    if producto_base and producto_base.precio_costo_base:
        ref = float(service_productos.convertir_a_moneda_base(
            db, producto_base.moneda_id, float(producto_base.precio_costo_base)
        ) or 0.0)
        if ref > 0:
            desviacion_vs_referencia = round((float(costo_prod) - ref) / ref * 100, 1)
            if abs(desviacion_vs_referencia) >= 30:
                advertencias.append(
                    f"El costo propuesto difiere {desviacion_vs_referencia:+.0f}% del costo real de "
                    f"'{producto_base.nombre}'. Revisa cantidades y materiales faltantes."
                )
    if secciones_faltantes:
        advertencias.append(
            "Faltan secciones típicas de este tipo de mueble: " + ", ".join(secciones_faltantes) + "."
        )

    return {
        "producto_base_id": producto_base.id if producto_base else None,
        "producto_base_nombre": producto_base.nombre if producto_base else None,
        "score_similitud": score_base,
        "secciones": secciones_out,
        "materiales_sin_precio": materiales_sin_precio,
        "resumen": resumen,
        "secciones_faltantes": secciones_faltantes,
        "desviacion_vs_referencia": desviacion_vs_referencia,
        "advertencia": " ".join(advertencias) if advertencias else None,
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
    escala_habilitada: bool = True,
) -> Decimal:
    """Escala la cantidad base del material según el tipo de escala.

    Con escala_habilitada=False (medidas base desconocidas) devuelve la
    cantidad del Excel sin tocar: las recetas reales ya incluyen la medida
    real de cada mueble.
    """
    tipo = (pm.tipo_escala or "FIJO").upper()
    cantidad = pm.cantidad_base or Decimal("0")

    if not escala_habilitada:
        return cantidad

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
    impuesto_porcentaje: float = 7.0,
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

            # Las líneas de labor (HECHURA, PREPARADO...) nunca bloquean
            if precio_pendiente and item.get("activo", True) and not _es_linea_labor(
                item.get("nombre", ""), item.get("unidad", "")
            ):
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
    # a = costo_producción × (1 + impuesto%); b = a × (1 + ganancia%)
    monto_imp = round(costo_prod * (D(str(impuesto_porcentaje)) / D("100")), 2)
    base_imp = round(costo_prod + monto_imp, 2)
    precio_sin_iva = round(base_imp * (D("1") + D(str(ganancia_porcentaje)) / D("100")), 2)
    precio_con_iva = round(precio_sin_iva * (D("1") + D(str(iva_porcentaje)) / D("100")), 2)

    resumen = {
        "costo_materiales": float(round(costo_mat_dec, 2)),
        "costo_mano_obra": float(round(costo_mo, 2)),
        "costo_gastos": float(round(costo_g, 2)),
        "costo_produccion": float(round(costo_prod, 2)),
        "impuesto_porcentaje": float(impuesto_porcentaje),
        "impuestos": float(monto_imp),
        "base_con_impuestos": float(base_imp),
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
        "secciones_faltantes": [],
        "desviacion_vs_referencia": None,
        "advertencia": None,
    }
