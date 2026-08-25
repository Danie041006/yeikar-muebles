"""
contexto_exporter.py
====================
Genera el "paquete de contexto" para el Modo Manual del Cotizador IA:
el ERP le entrega al usuario (y este a una IA de navegador: ChatGPT,
Gemini, Claude) el conocimiento del negocio: inventario con costos,
receta de un producto similar, reglas de costeo, anatomía por tipo de
mueble y una LIBRERÍA de prompts conversacionales en lenguaje llano.

La IA responde en el MISMO FORMATO DEL EXCEL de la empresa (tabla por
secciones: MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL). El
ERP convierte esa respuesta al JSON interno (ver texto_excel_parser.py)
sin que el usuario tenga que ver ni entender "JSON".

Ninguna llamada externa: es 100% local y gratuito.
"""
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.productos.model import Material, Producto, MaterialSinonimo, ProductoMaterial
from app.modules.quotes.structure_builder import (
    _detectar_seccion,
    _encontrar_referencia_por_tipo,
    _seccion_canonica,
    _base_seccion,
    _RECETA_EAGER,
    _cargar_estimaciones_por_tipo,
)
from app.modules.quotes.atributos import ANATOMIA_POR_TIPO, LABOR_POR_SECCION, SUB_PARTES_POR_TIPO

# Secciones del negocio ALINEADAS AL EXCEL: herrajes, iluminación y cola de
# pato viven dentro de TERMINACIÓN (no hay secciones separadas). Cuando el
# mueble tiene varias piezas, la sección lleva la pieza entre paréntesis
# (EBANISTERÍA (CAMA), PINTURA (NOCHEROS)...) — ver regla 1 y SUB_PARTES_POR_TIPO.
SECCIONES_VALIDAS = [
    "EBANISTERÍA", "TENDIDO", "PINTURA", "TAPICERÍA",
    "TERMINACIÓN", "NOCHEROS", "MANO DE OBRA",
]

# Formato de respuesta que pedimos a la IA (visible para Carolina, estilo Excel)
FORMATO_EXCEL = """SECCION EBANISTERIA (CAMA)
MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL
LAMINA DE 9 | 1 | LAMINA | 140000 | 140000
COLBON | 0.7 | LITRO | 14000 | 9800
HECHURA (CAMA) | 1 | PAR |  | 
SECCION PINTURA (NOCHEROS)
PREPARADO | 1 | PISTOLADA |  | 
PINTURA | 1 | PISTOLADA |  | 
"""

# Esquema JSON interno del motor (NO se muestra al usuario; es el contrato
# que produce texto_excel_parser.py y que consume structure_builder.py).
ESQUEMA_JSON_INTERNO = {
    "seccion": "EBANISTERÍA",
    "items": [
        {"nombre_material": "LAMINA DE 9", "cantidad_sugerida": 1, "unidad": "LAMINA", "razon": "", "es_opcional": False},
    ],
}

# --- Limpieza del catálogo para presentación (no toca la BD) ----------------

_ACENTOS = str.maketrans(
    "áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN"
)

_UNIDADES_BASURA = (
    "%", "PEDAZO", "PEDASO", "POQUITO", "PAGO AL CO", "CIERREL", "CENTIMET",
    "* LITRO", "* UNIDAD", "DE 2X2", "M.O", "UNIIDAD", "1 X 1", "PATAS PINT",
    "30X30", "3*20", "2,10X", "187", "LAMINA (", "55*56", "PUNTO DE",
)


def _norm_texto(valor: str) -> str:
    """Normaliza un texto para comparación (minúsculas, sin acentos, espacios)."""
    s = (valor or "").lower().translate(_ACENTOS)
    s = re.sub(r'["\'"]', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _unidad_es_basura(unidad: Optional[str]) -> bool:
    if not unidad:
        return False
    u = unidad.upper()
    if not any(ch.isalpha() for ch in u):
        return True
    return any(marker in u for marker in _UNIDADES_BASURA)


def _es_material_util(mat) -> bool:
    nombre = (mat.nombre or "").strip()
    n = _norm_texto(nombre)
    if n.startswith("test"):
        return False
    if any(n.startswith(prefix) for prefix in ("total", "subtotal", "gastos", "materia prima", "costo de", "gasos", "tabulaci", "nombre del producto")):
        return False
    if _unidad_es_basura(mat.unidad_medida.nombre if mat.unidad_medida else None):
        return False
    if any(p in n for p in (" m.o", " 5% de m.o", " 10% de m.o")):
        return False
    return True


def _inventario_para_contexto(db: Session, solo_secciones: Optional[set] = None) -> list[dict]:
    """Catálogo de materiales activos con costo y unidad.

    Se presentan DEDUPLICADOS por nombre normalizado y LIMPIOS (se excluyen
    materiales de prueba, líneas-total y unidades basura) para que la IA
    trabaje con un catálogo enfocado. No modifica la base de datos.

    Si solo_secciones se indica, solo incluye materiales cuya sección
    detectada esté en el conjunto.
    """
    materiales = (
        db.query(Material)
        .filter(Material.activo == True)  # noqa: E712
        .order_by(Material.nombre)
        .all()
    )

    mejores: dict[str, dict] = {}
    for mat in materiales:
        if not _es_material_util(mat):
            continue
        if solo_secciones is not None:
            seccion = _detectar_seccion(mat.nombre)
            if seccion not in solo_secciones:
                continue
        sinonimos = [
            s.sinonimo
            for s in db.query(MaterialSinonimo)
            .filter(MaterialSinonimo.material_id == mat.id)
            .all()
        ]
        candidato = {
            "id": mat.id,
            "nombre": mat.nombre,
            "costo_base": float(mat.costo_base),
            "unidad": mat.unidad_medida.nombre if mat.unidad_medida else None,
            "abreviatura": mat.unidad_medida.abreviatura if mat.unidad_medida else None,
            "sinonimos": sinonimos,
        }
        clave = _norm_texto(mat.nombre)
        previo = mejores.get(clave)
        if previo is None or _mejor_candidato(candidato, previo) == candidato:
            mejores[clave] = candidato

    return sorted(mejores.values(), key=lambda m: _norm_texto(m["nombre"]))


def _mejor_candidato(candidato: dict, previo: dict) -> dict:
    """Entre duplicados, prefiere unidad limpia corta y costo razonable."""
    def calidad(unidad: Optional[str]) -> int:
        if not unidad:
            return 0
        u = unidad.upper()
        if any(ch.isdigit() for ch in u):
            return 1  # unidad con medidas extrañas → baja
        if len(u) <= 12:
            return 3  # unidad corta y limpia
        return 2
    c1, c2 = calidad(candidato["unidad"]), calidad(previo["unidad"])
    if c1 != c2:
        return candidato if c1 > c2 else previo
    return candidato


def _receta_desde_producto(producto: Producto) -> dict:
    """Receta de un producto agrupada por sección (para imitar proporciones).

    Prefiere la estructura JERÁRQUICA importada del Excel
    (SeccionProducto → ElementoSeccion); si no existe, usa la receta plana.
    """
    secciones: dict[str, list[dict]] = {}

    if producto.secciones:
        for sec in producto.secciones:
            sec_nombre = _seccion_canonica(sec.nombre)
            for el in sec.elementos:
                mat = el.material_normalizado
                nombre = mat.nombre if mat else (el.nombre_insumo_original or "SIN NOMBRE")
                unidad = (
                    el.unidad_medida
                    or (mat.unidad_medida.abreviatura if mat and mat.unidad_medida else None)
                )
                secciones.setdefault(sec_nombre, []).append({
                    "nombre": nombre,
                    "cantidad": float(el.cantidad or 1.0),
                    "unidad": unidad,
                    "tipo_escala": "FIJO",
                    "observaciones": el.observaciones or None,
                })
    else:
        for pm in producto.materiales:
            if not pm.material:
                continue
            sec = (pm.seccion or "EBANISTERIA").upper()
            secciones.setdefault(sec, []).append({
                "nombre": pm.material.nombre,
                "cantidad": float(pm.cantidad_base),
                "unidad": pm.material.unidad_medida.abreviatura if pm.material.unidad_medida else None,
                "tipo_escala": pm.tipo_escala,
                "observaciones": pm.observaciones or None,
            })

    return {
        "producto_id": producto.id,
        "nombre": producto.nombre,
        "ancho_base": float(producto.ancho_base or 1.60),
        "largo_base": float(producto.largo_base or 1.90),
        "alto_base": float(producto.alto_base) if producto.alto_base else None,
        "secciones": [
            {"seccion": sec, "items": items}
            for sec, items in secciones.items()
        ],
    }


def _receta_para_contexto(db: Session, producto_base_id: Optional[int]) -> Optional[dict]:
    """Receta plana del producto base agrupada por sección (para imitar proporciones)."""
    if not producto_base_id:
        return None
    producto = db.query(Producto).options(*_RECETA_EAGER).filter(Producto.id == producto_base_id).first()
    if not producto:
        return None
    return _receta_desde_producto(producto)


def _formatear_inventario(inventario: list[dict]) -> str:
    lineas = []
    for m in inventario:
        unidad = f"{m['unidad']} ({m['abreviatura']})" if m["abreviatura"] else "—"
        lineas.append(f"- {m['nombre']} — {m['costo_base']:.2f} por {unidad}")
    return "\n".join(lineas)


def _formatear_receta_excel(receta: dict) -> str:
    """Renderiza una receta REAL completa en el formato Excel de la empresa.

    Incluye TODOS los ítems (materiales Y líneas de mano de obra como
    HECHURA/PREPARADO o contratistas, p. ej. 'NOCHEROS | LUIS ALFONSO'):
    la IA debe ver cómo se expresan realmente las estructuras.
    """
    partes = [
        f"PRODUCTO REAL: {receta['nombre']} (base {receta['ancho_base']} m × {receta['largo_base']} m)",
    ]
    for sec in receta["secciones"]:
        partes.append(f"SECCION {sec['seccion']}")
        partes.append("MATERIAL | CANTIDAD | UNIDAD")
        for item in sec["items"]:
            partes.append(
                f"  {item['nombre']} | {item['cantidad']:g} | {item['unidad'] or 'UN'}"
            )
    return "\n".join(partes)


def _medianas_para_contexto(db: Session, tipo_mueble: str, max_lineas: int = 40) -> str:
    """Tabla de MEDIANAS de cantidad por (material, sección, unidad) calculada
    sobre todas las recetas históricas del tipo de mueble.

    Le dice a la IA del navegador cuánto se usa REALMENTE cada material en la
    fábrica, para que proponga cantidades realistas desde el inicio y no
    invente números. Se ordena por frecuencia (n) para mostrar lo más sólido.
    """
    estimaciones = _cargar_estimaciones_por_tipo(db, tipo_mueble)
    if not estimaciones:
        return ""

    filas = []
    for clave, est in estimaciones.items():
        material, seccion, unidad = clave.split("||")
        filas.append((est["n"], material, seccion, unidad, est["mediana"], est["min"], est["max"]))
    filas.sort(reverse=True)

    lineas = [
        "CANTIDADES REALES MÁS COMUNES (MEDIANA de recetas ya fabricadas de este tipo de mueble, por material/sección/unidad). "
        "Úsalas como referencia al proponer cantidades — la fábrica usa aproximadamente estas cantidades por mueble:",
    ]
    for n, material, seccion, unidad, mediana, mn, mx in filas[:max_lineas]:
        lineas.append(
            f"  {material.upper()} | {seccion.upper()} | {unidad} → mediana {mediana:g} (rango {mn:g}-{mx:g}, {n} recetas)"
        )
    return "\n".join(lineas)


def _recetas_referencia(
    db: Session,
    tipo_mueble: str,
    producto_base_id: Optional[int] = None,
    max_n: int = 3,
) -> str:
    """Embeber las estructuras REALES de referencia para anclar la respuesta de la IA.

    Prioriza el producto elegido por el usuario y completa con los productos
    reales del mismo tipo (auto-selección). Es el ancla que hace que la IA
    imite nuestras estructuras (madera, secciones, materiales) en vez de inventar.
    """
    elegidos: list[Producto] = []
    vistos: set = set()
    if producto_base_id:
        p = db.query(Producto).options(*_RECETA_EAGER).filter(Producto.id == producto_base_id).first()
        if p:
            elegidos.append(p)
            vistos.add(p.id)
    for p in _encontrar_referencia_por_tipo(db, tipo_mueble, max_n=max_n):
        if p.id not in vistos:
            elegidos.append(p)
            vistos.add(p.id)

    if not elegidos:
        return ""

    bloques = [
        "ESTRUCTURAS REALES QUE YA FABRICAMOS (REFERENCIA — tu respuesta debe salir de estas estructuras: mismos materiales, "
        "mismas secciones y la misma forma de expresar la MADERA, ej. 'MADERA (2) | APAMATE'. Copia de ellas y ajusta cantidades al mueble nuevo):"
    ]
    for p in elegidos[:max_n]:
        bloques.append(_formatear_receta_excel(_receta_desde_producto(p)))
    return "\n\n".join(bloques)


def _dims_texto(ancho: float, largo: float, alto: Optional[float]) -> str:
    dims = f"{ancho} m de ancho × {largo} m de largo"
    if alto:
        dims += f" × {alto} m de alto"
    return dims


def _anatomia_para_tipo(tipo_mueble: str) -> str:
    """Texto de la anatomía del mueble para incluir en el prompt (vacío si no aplica).

    Si el tipo tiene piezas definidas (SUB_PARTES_POR_TIPO), las secciones se
    listan POR PIEZA con su nombre completo (EBANISTERÍA (CAMA)...); si no,
    se listan las secciones base con su mano de obra.
    """
    anatomia = ANATOMIA_POR_TIPO.get(tipo_mueble or "otro")
    if not anatomia:
        return ""
    piezas = SUB_PARTES_POR_TIPO.get(tipo_mueble or "otro")
    partes = [
        f"ANATOMÍA DEL MUEBLE (un/a {anatomia['etiqueta']}; NO omitas ninguna sección que aplique):",
    ]
    if piezas:
        partes.append("- Piezas del mueble: " + ", ".join(piezas.keys()) + ".")
        partes.append("- Secciones POR PIEZA (nómbralas así, con la pieza entre paréntesis):")
        for pieza, secciones_pieza in piezas.items():
            partes.append(f"  · {pieza}: " + ", ".join(secciones_pieza) + ".")
        partes.append("- Mano de obra por pieza (línea dentro de su sección):")
        for pieza, secciones_pieza in piezas.items():
            for sec in secciones_pieza:
                labor = LABOR_POR_SECCION.get(_base_seccion(sec))
                if labor:
                    partes.append(f"  · {sec}: {labor}")
    else:
        partes.append("- Secciones requeridas: " + ", ".join(anatomia["secciones"]) + ".")
        if anatomia["opcionales"]:
            partes.append("- Opcionales según el pedido: " + ", ".join(anatomia["opcionales"]) + ".")
        partes.append("- Mano de obra por sección (inclúyela como línea dentro de la sección):")
        for sec in anatomia["secciones"] + anatomia["opcionales"]:
            labor = LABOR_POR_SECCION.get(sec)
            if labor:
                partes.append(f"  · {sec}: {labor}")
    return "\n".join(partes)


def _bloque_comun(
    anatomia_texto: str,
    receta_texto: str,
    referencias_texto: str,
    inv_texto: str,
) -> str:
    """Reglas de negocio + anatomía + estructuras de referencia + catálogo.

    Es el "conocimiento del negocio" compartido por TODOS los prompts.
    """
    return f"""REGLAS DEL NEGOCIO (obligatorias):
1. Secciones de producción válidas: {", ".join(SECCIONES_VALIDAS)}. Cuando el mueble tenga VARIAS PIEZAS (cama + nocheros, mesa + sillas, sofá + acompañantes), NOMBRA la pieza entre paréntesis, igual que en nuestro Excel: EBANISTERÍA (CAMA), EBANISTERÍA (NOCHEROS), PINTURA (CAMA), PINTURA (NOCHEROS), PINTURA (PATAS), EBANISTERÍA (MESA), EBANISTERÍA (SILLAS), TAPICERÍA (SILLAS), etc. Si es una sola pieza, usa la sección sin paréntesis.
2. Las cantidades son para UN (1) mueble terminado, no para lotes.
3. Unidades: copia SIEMPRE la unidad que aparece entre paréntesis al lado de cada material del catálogo (ej. LAMINA, LITRO, TIRA, PAR, PISTOLADA, CMS, METROS, UN). NO conviertas ni inventes unidades.
4. Nombres: usa los nombres EXACTOS del catálogo (cópialos tal cual, en mayúsculas). Si el catálogo tiene un sinónimo más claro, usa el nombre principal del material.
5. Mano de obra POR SECCIÓN: dentro de cada sección que lo requiera incluye la línea de labor del taller como un ítem más (HECHURA, PREPARADO, PINTURA/ACABADO, TAPIZADO, MONTAJE, EMBALAJE, COLA DE PATO) con cantidad 1 y la unidad que corresponda (PAR, PISTOLADA, CAMA, UN). Si la sección es de una pieza, nombra la labor con la pieza (HECHURA (CAMA), HECHURA (NOCHEROS)). NO crees una sección global de MANO DE OBRA salvo que el catálogo incluya materiales de mano de obra con precio.
6. Marca las mejoras opcionales (nocheros, iluminación, cojines, espejos) como opcionales si son adicionales.
7. Razona paso a paso antes de responder. Usa todo tu modo de razonamiento si lo tienes activado. NUNCA asumas ni inventes datos: si algo no se puede saber con certeza (medidas, tela, patas, alcance), pregúntalo antes de cotizar.
8. Herrajes (correderas, jaladores, patas, bisagras), iluminación (luces, cable, apagadores, LED) y la COLA DE PATO (doblado de tela) van DENTRO de la sección TERMINACIÓN, como en nuestro Excel. NO los pongas en secciones separadas.

{anatomia_texto}
{referencias_texto if referencias_texto else "No hay estructuras de referencia en el sistema: propón desde el catálogo de abajo."}

CATÁLOGO DE INVENTARIO (nombre — costo por unidad — unidad). Usa estos nombres EXACTOS:
{inv_texto}
"""


def _construir_prompts(
    inventario: list[dict],
    referencias_texto: str,
    ancho: float,
    largo: float,
    alto: Optional[float],
    con_foto: bool = True,
    descripcion: Optional[str] = None,
    tipo_mueble: str = "otro",
    medianas_texto: str = "",
) -> list[dict]:
    """Construye la LIBRERÍA conversacional de prompts.

    La IA responde en FORMATO EXCEL (tabla por secciones); el ERP convierte
    la respuesta al JSON interno (texto_excel_parser.py).
    """
    inv_texto = _formatear_inventario(inventario)
    anatomia_texto = _anatomia_para_tipo(tipo_mueble)
    dims = _dims_texto(ancho, largo, alto)
    comun = _bloque_comun(anatomia_texto, "", referencias_texto, inv_texto)
    if medianas_texto:
        comun = comun.rstrip() + "\n\n" + medianas_texto + "\n"

    if con_foto:
        entrada = "Te voy a adjuntar la FOTO del mueble que vamos a cotizar"
        entrada_extra = ""
    else:
        entrada = "Te voy a dar la DESCRIPCIÓN del mueble que vamos a cotizar"
        entrada_extra = (
            "\n\nDESCRIPCIÓN DEL MUEBLE:\n" + (descripcion or "").strip()
            if descripcion and descripcion.strip()
            else "\n\n(Sin descripción adicional: un mueble razonable de la familia indicada)"
        )

    # ── 1) Entender el mueble (briefing con preguntas clave) ───────────────
    prompt_entender = f"""Eres el costeador de fábrica de "Comercializadora Yeikar", una mueblería que fabrica muebles a medida. {entrada}.{entrada_extra}

POR AHORA NO des la estructura de costos todavía. Tu tarea es ENTENDER el mueble como lo haría un costeador experimentado de la fábrica, con su MISMO nivel de detalle: sé tan minucioso como puedas y hazme las preguntas clave que necesites, una a la vez o en grupos cortos (2-3), de lo más importante a lo menos importante.

Antes de cada pregunta di brevemente qué puedes ver de la foto y qué NO puedes saber. No asumas ni inventes: todo lo que no se pueda saber con certeza se pregunta. Repasa punto por punto, sin saltarte ninguno:

- Dimensiones y cortes: ancho, largo y alto del mueble (una foto no da medidas); alto del espaldar y de cada pieza desde el piso; curvas, esquinas redondeadas o paneles que requieran CNC/plantilla/torno.
- Alcance del pedido: ¿solo el mueble principal o también los acompañantes que salen en la foto (nocheros, sillas, mesas)? ¿Los objetos decorativos de la foto (lámparas, alfombras) van incluidos en la cotización o son solo referencia?
- Secciones que lleva (mira la ANATOMÍA de abajo): ebanistería, tendido, pintura, tapicería, terminación, nocheros, iluminación.
- Tapicería: ¿qué piezas van tapizadas (espaldar, laterales, pie, base)? ¿El acabado envuelve toda la pieza o solo el panel frontal? ¿La tela es del catálogo o es una tela nueva? (si es nueva: metros aproximados y precio por metro). ¿El relleno de las canales es espuma o guata? ¿Cuántas canales/pliegues tiene?
- Patas y herrajes: ¿las patas son de un modelo del catálogo o un modelo nuevo que hay que comprar? (si es nuevo: cantidad y precio aproximado por unidad). ¿Lleva herrajes especiales (gato de cama, correderas, jaladores, bisagras) o va con herrajes normales?
- Pintura: ¿qué partes van pintadas y cuáles tapizadas (ej. la parte de atrás del espaldar)? ¿Necesita sellador/color/laca?
- Si hay algún insumo que NO esté en el catálogo de abajo y que necesitaríamos comprar por primera vez (pregúntame su cantidad y su precio aproximado).
- Mano de obra por sección (hechura, preparado, pintura, tapizado).

{comun}

Pregunta en lenguaje claro y simple, como si hablaras con la dueña de la mueblería. Cuando entiendas bien el mueble, dímelo y pide que continuemos con la estructura de costos."""

    # ── 2) Estructura de costos (formato Excel) ─────────────────────────────
    prompt_estructura = f"""Eres el costeador de fábrica de "Comercializadora Yeikar". Ya conocemos el mueble (lo analizamos arriba en esta misma conversación). Ahora dame la ESTRUCTURA DE COSTOS DEFINITIVA para cotizar.

RESPONDE EN EL MISMO FORMATO DE NUESTRO EXCEL, así lo copiamos directo:
1. Tu respuesta debe salir de las ESTRUCTURAS REALES DE REFERENCIA de abajo: mismos materiales, mismas secciones y la MISMA forma de expresar la MADERA (con su especie o medida, ej. "MADERA (2) | APAMATE" o "MADERA | 232 | CMS"). Copia de esas estructuras y ajusta las cantidades al mueble nuevo. NO inventes materiales que ya tengamos en el catálogo.
2. Separa por SECCIONES de producción: EBANISTERÍA, TENDIDO, PINTURA, TAPICERÍA, TERMINACIÓN, NOCHEROS, etc. (los herrajes e iluminación van dentro de TERMINACIÓN, como en nuestro Excel).
3. Debajo de cada sección pon una tabla con estas columnas separadas por " | ":
   MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL
4. La mano de obra va como una fila dentro de su sección (HECHURA, PREPARADO, PINTURA/ACABADO, TAPIZADO, MONTAJE, EMBALAJE) con cantidad 1 y su unidad.
5. Usa SOLO nombres y unidades del catálogo de abajo (cópialos tal cual).
6. En PRECIO TOTAL pon cantidad × v/unit o un valor aproximado; nosotros validamos los precios con el inventario.
7. Marca como opcionales (con (OPC) al final de la línea) las mejoras opcionales: nocheros, iluminación, cojines, espejos.

MEDIDAS DEL MUEBLE: {dims}.

Si al pedir esta estructura hay datos clave que aún NO sabes con certeza (medidas exactas, tela, patas, alcance del pedido), pregúntalos PRIMERO, uno por uno, antes de dar la tabla. Nunca asumas ni inventes datos.

EJEMPLO DEL FORMATO QUE QUIERO:
{FORMATO_EXCEL}
{comun}
RESPUESTA: Devuelve la tabla en texto plano (marcada con ``` arriba y abajo), sin ningún otro texto. NO uses JSON."""

    # ── 3) Dudas específicas (insumo nuevo, precio, cantidad) ───────────────
    prompt_dudas = f"""Eres el costeador de fábrica de "Comercializadora Yeikar". Te voy a mostrar un caso puntual de un mueble: un insumo, una sección o un costo en particular (puede ser un insumo NUEVO que nunca hemos usado o una duda de cantidad o precio).

Tu tarea:
1. Antes de incluir el insumo, pregúntame lo específico que necesites: cantidad, unidad, precio (V/UNIT), proveedor o dónde se usa en el mueble.
2. Si el insumo NO está en el catálogo de abajo, dímelo claramente para que lo podamos agregar al inventario.
3. Cuando tengas lo que necesitas, incorpora el insumo a la sección correcta de la estructura, EN EL FORMATO EXCEL (tabla MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL).

{comun}
Haz preguntas cortas y claras. NO inventes precios ni cantidades."""

    # ── 4) Reparar una respuesta que no quedó bien ──────────────────────────
    prompt_reparar = f"""Eres el costeador de fábrica de "Comercializadora Yeikar". Te voy a pegar texto que contiene una estructura de costos: puede venir desordenado, incompleto, con texto alrededor, con formato raro, o mezclado con explicaciones.

Tu tarea es LIMPIARLO y devolverlo en el FORMATO EXCEL estándar:
1. Sepáralo por SECCIONES (EBANISTERÍA, TENDIDO, PINTURA, TAPICERÍA, TERMINACIÓN, NOCHEROS...).
2. Cada fila con las columnas separadas por " | ": MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL.
3. Corrige nombres y unidades para que coincidan con el catálogo de abajo.
4. Quita filas de totales, encabezados, y cualquier texto que no sea un material.

{comun}
RESPUESTA: Solo la tabla limpia (marcada con ``` arriba y abajo), sin texto adicional. NO uses JSON."""

    return [
        {
            "id": "entender_mueble",
            "titulo": "Entender el mueble",
            "descripcion": "La IA te hace las preguntas clave del costeador antes de cotizar (cortes, materiales, insumos nuevos, secciones).",
            "instrucciones": prompt_entender,
        },
        {
            "id": "estructura_costos",
            "titulo": "Estructura de costos",
            "descripcion": "La IA da la estructura definitiva en el formato del Excel (tabla por secciones) para pegar directo en el ERP.",
            "instrucciones": prompt_estructura,
        },
        {
            "id": "preguntas_especificas",
            "titulo": "Dudas específicas",
            "descripcion": "Para un insumo o costo puntual que necesita aclaración (insumo nuevo, precio o cantidad).",
            "instrucciones": prompt_dudas,
        },
        {
            "id": "reparar_pegar",
            "titulo": "Reparar respuesta",
            "descripcion": "Limpia y ordena una respuesta que no quedó bien y la devuelve en formato Excel.",
            "instrucciones": prompt_reparar,
        },
    ]


def _construir_instrucciones(
    inventario: list[dict],
    ancho: float,
    largo: float,
    alto: Optional[float],
    con_foto: bool = True,
    descripcion: Optional[str] = None,
    referencias_texto: str = "",
    tipo_mueble: str = "otro",
) -> str:
    """Prompt por defecto (entender el mueble), por compatibilidad."""
    prompts = _construir_prompts(
        inventario, referencias_texto, ancho, largo, alto,
        con_foto=con_foto, descripcion=descripcion, tipo_mueble=tipo_mueble,
    )
    return prompts[0]["instrucciones"] if prompts else ""


def generar_contexto(
    db: Session,
    producto_base_id: Optional[int] = None,
    ancho: float = 1.60,
    largo: float = 1.90,
    alto: Optional[float] = None,
    con_foto: bool = True,
    descripcion: Optional[str] = None,
    tipo_mueble: str = "otro",
) -> dict:
    """Arma el paquete de contexto completo (shape de ContextoExportarOut)."""
    anatomia = ANATOMIA_POR_TIPO.get(tipo_mueble or "otro")
    if anatomia:
        # El filtro del catálogo mantiene los materiales de herrajes/iluminación
        # (la IA los necesita aunque se agrupen dentro de TERMINACIÓN).
        solo = set(anatomia["secciones"]) | set(anatomia["opcionales"]) | {"HERRAJES", "ILUMINACIÓN", "MANO DE OBRA"}
        inventario = _inventario_para_contexto(db, solo_secciones=solo)
    else:
        inventario = _inventario_para_contexto(db)

    receta = _receta_para_contexto(db, producto_base_id)
    referencias_texto = _recetas_referencia(
        db, tipo_mueble, producto_base_id=producto_base_id, max_n=3
    )
    medianas_texto = _medianas_para_contexto(db, tipo_mueble)

    prompts = _construir_prompts(
        inventario, referencias_texto, ancho, largo, alto,
        con_foto=con_foto, descripcion=descripcion, tipo_mueble=tipo_mueble,
        medianas_texto=medianas_texto,
    )
    instrucciones = prompts[0]["instrucciones"] if prompts else ""

    modo = "CON FOTO" if con_foto else "SIN FOTO (DESCRIPCIÓN)"
    tipo_label = anatomia["etiqueta"] if anatomia else tipo_mueble

    prompts_texto = "\n\n".join(
        f"### [{i+1}] {p['titulo']} — {p['descripcion']}\n{p['instrucciones']}"
        for i, p in enumerate(prompts)
    )

    texto = f"""MODO MANUAL DEL COTIZADOR IA — PAQUETE DE CONTEXTO ({modo})

TIPO DE MUEBLE: {tipo_label}

CÓMO USARLO (paso a paso):
1. COPIA el prompt [1] "Entender el mueble" y pégalo en ChatGPT, Gemini o Claude.{" Adjunta la FOTO del mueble en el PRIMER mensaje." if con_foto else ""}
2. Responde las preguntas que la IA te haga (cortes, materiales, insumos nuevos, secciones).
3. En la MISMA conversación (no abras otra), COPIA el prompt [2] "Estructura de costos" y pégalo.
4. La IA te devuelve la tabla estilo Excel (basada en nuestras estructuras reales): cópiala y pégala en el campo "Respuesta de la IA" del ERP, luego pulsa "Importar".
5. Si algo no quedó bien, usa [3] "Dudas específicas" o [4] "Reparar respuesta".

CONSEJOS SEGÚN TU IA:
- Las 3 IAs (Claude, ChatGPT y Gemini) deben hacerte las preguntas del costeador ANTES de cotizar: el prompt [1] lo exige. Si alguna salta directo a la tabla, respóndele: "Hazme TODAS las preguntas que necesites antes de cotizar, una por una".
- Claude: activa "extended thinking" para mejores cantidades.
- ChatGPT: usa un modelo con razonamiento y adjunta la foto en el primer mensaje.
- Gemini: activa "Deep Think" (modelo 2.5 Pro) para analizar la foto.
- No cambies de chat entre el paso 1 y el 2: la IA necesita recordar lo que entendió.

{"PRODUCTO DE REFERENCIA: id " + str(receta['producto_id']) + " — " + receta['nombre'] if receta else "PRODUCTO DE REFERENCIA: ninguno (el sistema usa las estructuras reales del mismo tipo)"}

=============== LIBRERÍA DE PROMPTS ===============
{prompts_texto}
====================================================

Datos estructurados descargables: inventario.json y receta.json incluidos en este paquete.
"""
    return {
        "producto_base_id": receta["producto_id"] if receta else None,
        "producto_base_nombre": receta["nombre"] if receta else None,
        "inventario": inventario,
        "receta_similar": receta,
        "instrucciones": instrucciones,
        "prompts": prompts,
        "texto": texto,
    }
