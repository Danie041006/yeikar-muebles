"""
texto_excel_parser.py
=====================
Convierte la respuesta de la IA en FORMATO EXCEL (tabla por secciones:
MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL) al JSON interno
`estructura_propuesta` que consume structure_builder.py.

El usuario NUNCA ve JSON: pega la tabla que devolvió la IA y el sistema
la interpreta. Se reutiliza la lógica de detección de secciones del motor.
"""
import re
from typing import Optional

SECCIONES_CANONICAS = [
    "EBANISTERÍA", "TENDIDO", "PINTURA", "TAPICERÍA",
    "HERRAJES", "TERMINACIÓN", "NOCHEROS", "ILUMINACIÓN", "MANO DE OBRA",
]

_FILAS_NO_MATERIAL = (
    "total", "subtotal", "gastos", "materia prima", "ganancia", "iva",
    "precio de venta", "precio del producto", "total a pagar",
    "nombre del producto", "coste de", "costo de", "nocheros en crudo",
)

_SECCIONES_NO = ("SECCION", "SECCIÓN", "SECCIONES", "MATERIA PRIMA")


def _norm(s: str) -> str:
    """Normaliza para comparar: minúsculas, sin acentos, espacios colapsados."""
    s = (s or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n")):
        s = s.replace(a, b)
    s = re.sub(r"[\"'*]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _canonicalizar_seccion(nombre: str) -> str:
    """Convierte un nombre de sección a canónico, CONSERVANDO la pieza.

    Ej: "EBANISTERIA (CAMA)" → "EBANISTERÍA (CAMA)" · "PINTURA Y PREPARADA"
    → "PINTURA" · "COLA DE PATO" / "COLAPATO" → "TERMINACIÓN".
    """
    n = nombre.strip()
    base, pieza = n, None
    m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", n)
    if m:
        base, pieza = m.group(1).strip(), m.group(2).strip()
    nn = _norm(base)
    nn_compact = nn.replace(" ", "")

    if "colapato" in nn_compact or "coladepato" in nn_compact:
        base_can = "TERMINACIÓN"
    else:
        base_can = None
        for can in SECCIONES_CANONICAS:
            cn = _norm(can)
            if cn == nn or (len(cn) >= 5 and cn in nn):
                base_can = can
                break
        if base_can is None:
            # coincidencia parcial (ej. "SECCION PINTURA Y PREPARADA" → PINTURA)
            for can in SECCIONES_CANONICAS:
                cn = _norm(can)
                if cn in nn or nn in cn:
                    base_can = can
                    break
        if base_can is None:
            base_can = "EBANISTERÍA"

    if pieza:
        return f"{base_can} ({pieza.upper()})"
    return base_can


def _es_seccion_linea(linea: str) -> Optional[str]:
    """Devuelve la sección canónica (con pieza si la trae) si la línea es un encabezado."""
    s = linea.strip()
    if not s:
        return None
    upper = s.upper()
    nombre = None
    for prefijo in ("SECCION", "SECCIÓN"):
        if upper.startswith(prefijo):
            resto = s[len(prefijo):].strip(" :\t-–")
            nombre = resto or None
            break
    if nombre is None:
        # Línea que es solo el nombre de una sección válida
        # (acepta base o base con pieza: "EBANISTERÍA (CAMA)")
        if _norm(s) in {_norm(c) for c in SECCIONES_CANONICAS}:
            nombre = s
        else:
            m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", s)
            if not m or _norm(m.group(1)) not in {_norm(c) for c in SECCIONES_CANONICAS}:
                return None
            nombre = s
    return _canonicalizar_seccion(nombre)


def _es_numero(valor: str) -> bool:
    v = (valor or "").strip().replace(",", ".")
    if not v:
        return False
    try:
        float(v)
        return True
    except ValueError:
        return False


def _es_fila_encabezado(linea: str) -> bool:
    n = _norm(linea)
    return ("material" in n and ("cantidad" in n or "unidad" in n)) or n.startswith("material")


def _es_fila_no_material(linea: str) -> bool:
    n = _norm(linea)
    if not n:
        return True
    if any(n.startswith(prefix) for prefix in _FILAS_NO_MATERIAL):
        return True
    # filas de total estilo "MÁS GANANCIA", "Gastos de Ebanisteria e 10%"
    if "ganancia" in n or "gastos de" in n or "total gastos" in n:
        return True
    return False


def _parsear_fila(linea: str) -> Optional[dict]:
    """Convierte una línea de datos a un ítem de la estructura."""
    linea = linea.strip().lstrip("*").strip()
    if not linea:
        return None
    if _es_fila_encabezado(linea) or _es_fila_no_material(linea):
        return None

    tokens = [t.strip() for t in linea.split("|") if t.strip()]
    separador_pipe = len(tokens) > 1
    if not separador_pipe:
        tokens = [t for t in re.split(r"\s{2,}|\t", linea) if t.strip()]

    # sin separador claro → intento por espacios (mejor esfuerzo)
    if len(tokens) == 1:
        tokens = [t for t in linea.split() if t.strip()]

    if not tokens:
        return None

    # Filas sin "|" y sin ningún número NO son materiales (son prosa)
    if not separador_pipe and not any(_es_numero(t) for t in tokens[1:]):
        return None

    material = tokens[0].strip(" *").upper()
    if not material or material in {"MATERIAL", "SECCION", "SECCIÓN"}:
        return None

    numeros = []
    unidad_partes = []
    for t in tokens[1:]:
        if _es_numero(t):
            numeros.append(float(t.replace(",", ".")))
        else:
            unidad_partes.append(t)

    cantidad = numeros[0] if numeros else 1.0
    unidad = " ".join(unidad_partes).upper().strip() if unidad_partes else "UN"
    if not any(ch.isalpha() for ch in unidad):
        unidad = "UN"

    es_opcional = bool(re.search(r"\b(OPC|OPCIONAL)\b", linea, re.IGNORECASE))

    return {
        "nombre_material": material,
        "cantidad_sugerida": round(cantidad, 4),
        "unidad": unidad,
        "razon": "",
        "es_opcional": es_opcional,
    }


def _extraer_lineas_utiles(texto: str) -> list[str]:
    """Extrae las líneas a procesar: si hay cercos ```, usa el primer bloque con datos."""
    lineas_raw = texto.splitlines()
    hubo_fences = any(l.strip().startswith("```") for l in lineas_raw)
    if not hubo_fences:
        return [l.strip() for l in lineas_raw if l.strip()]

    bloques: list[list[str]] = []
    dentro = False
    buffer: list[str] = []
    for l in lineas_raw:
        if l.strip().startswith("```"):
            if dentro and buffer:
                bloques.append(buffer)
                buffer = []
            dentro = not dentro
            continue
        if dentro:
            buffer.append(l)
    if buffer:
        bloques.append(buffer)

    for b in bloques:
        if any(_es_seccion_linea(x) or _es_fila_encabezado(x) for x in b):
            return [x.strip() for x in b if x.strip()]
    return [x.strip() for b in bloques for x in b if x.strip()]


def parsear_texto_excel(texto: str) -> list[dict]:
    """Convierte la respuesta en formato Excel a estructura_propuesta.

    Devuelve: [{"seccion": "EBANISTERÍA", "items": [{nombre_material,
    cantidad_sugerida, unidad, razon, es_opcional}, ...]}, ...]
    """
    if not texto or not texto.strip():
        return []

    lineas = _extraer_lineas_utiles(texto)

    secciones: list[dict] = []
    seccion_actual = None
    empezado = False

    def seccion_obj(nombre: str) -> dict:
        for sec in secciones:
            if sec["seccion"] == nombre:
                return sec
        nueva = {"seccion": nombre, "items": []}
        secciones.append(nueva)
        return nueva

    for linea in lineas:
        if not linea:
            continue
        seccion_linea = _es_seccion_linea(linea)
        if seccion_linea:
            empezado = True
            seccion_actual = seccion_linea
            seccion_obj(seccion_linea)
            continue
        if not empezado:
            continue
        # Al llegar a una fila de totales dejamos de recolectar materiales
        if _es_fila_no_material(linea):
            break
        item = _parsear_fila(linea)
        if not item:
            continue
        sec = seccion_actual or "EBANISTERÍA"
        seccion_obj(sec)["items"].append(item)

    # quitar secciones sin ítems
    return [sec for sec in secciones if sec["items"]]
