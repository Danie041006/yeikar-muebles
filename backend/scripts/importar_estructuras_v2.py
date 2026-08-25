#!/usr/bin/env python3
"""
importar_estructuras_v2.py
==========================
Importador batch de estructuras de costos del Excel YEIKAR hacia el esquema
jerárquico por secciones (igual al producto de referencia del ERP):

    Producto
      └─ SeccionProducto            (EBANISTERÍA (CAMA), PINTURA (NOCHEROS), TENDIDO, …)
           ├─ ElementoSeccion        (insumos físicos: cantidad, unidad, precio_unitario)
           ├─ PoliticaSeccion        (pct_gastos_seccion, costo_fabricacion, pct_trabajadores, mano_obra_base)
           └─ CostoProduccionSeccion (FABRICACIÓN, PREPARADO, PINTURA, HECHURA …)

Flujo SEGURO (anti-mamera):
  1) `--dry-run` (por defecto): NO toca la base de datos. Audita las 67 hojas,
     clasifica, calcula el total que produciría el ERP y compara contra el total
     que declara cada hoja. Genera reporte por hoja.
  2) Revisar el reporte.
  3) `--write --sheet "<Nombre>" [--approve aprobadas.txt]`: escribe SOLO las
     hojas aprobadas que superen el umbral (por defecto Δ ≤ 15 %).

Reglas anti-inflación (corrigen los intentos anteriores):
  - Filas con TOTAL=$0 y cantidad 0/en blanco → SOLO REFERENCIA (no son insumos,
    eran la causa #1 de precios inflados: se importaban con cantidad 1).
  - Costos de producción (FABRICACIÓN/PREPARADO/PINTURA/HECHURA...) y políticas
    de gastos se detectan ANTES que los insumos; los %% de gastos se infieren de
    los subtotales declarados por la propia hoja cuando el texto no trae el %.
  - NUNCA se sobrescribe el precio (costo_base) de un Material existente.
  - El script NO recalcula ni reescala precios: transcribe lo que dice la hoja.

El total que aparece en el ERP lo calcula el MISMO motor que usa el producto de
referencia (cost_service), no este script.
"""

import argparse
import re
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import openpyxl

# ---------------------------------------------------------------------------
# Rutas por defecto
# ---------------------------------------------------------------------------
REPO = Path(__file__).parent.parent.parent
EXCEL_DEFAULT = REPO / "docs/info_para_usar/estructuras/CAMAS CON SUS MESAS DE NOCHE.xlsx"
CATALOGO_MATERIAL_CSV = REPO / "docs/documentos_de_negocio/yeikar_costos_csv_v1/material.csv"
UNIDADES_CSV = REPO / "docs/documentos_de_negocio/yeikar_costos_csv_v1/unidad_medida.csv"

# ---------------------------------------------------------------------------
# Normalización de secciones
# ---------------------------------------------------------------------------
SECCIONES_BASE = ("EBANISTERÍA", "PINTURA", "TAPICERÍA", "TERMINACIÓN", "TENDIDO", "COLA DE PATO", "NOCHEROS")

SECCION_HEADER_PAT = re.compile(
    r"^\s*SECCION\s+(TAPICERIA|TAPICERÍA|TERMINACION|TERMINACIÓN|PINTURA|TENDIDO|"
    r"EBANISTERIA|EBANISTERÍA|NOCHEROS|COLA\s*DE\s*PATO)\b(.*)$",
    re.IGNORECASE,
)
SECCION_LONELY = re.compile(
    r"^\s*(TENDIDO(?:S)?(\s+DE\s+\w+)?|COLA\s*DE\s*PATO|NOCHEROS)\s*$", re.IGNORECASE
)

TEXTO_BASE_OCCUP_ROWS = ("MATERIA PRIMA", "CANTIDAD", "UNIDAD DE MEDIDA", "V/UNIT", "PRECIO TOTAL")
IGNORAR_FILA_STARTS = (
    "COSTO DE", "COMISION", "OBSERVACION", "ELABORADO", "RIF-", "COMERCIALIZADORA",
    "ESTRUCTURA", "FECHA ", "EBANISTA", "FABRICO", "FABRICÓ", "MODELO", "VENTA ",
    "FACTURA", "ORDEN", "CELULAR", "DIRECCION", "DIRECCIÓN",
)

COSTO_PROD_STARTS = (
    "FABRICACION", "FABRICACIÓN", "FABRICAC.", "HECHURA",
    "MANO DE OBRA", "M.O", "PAGO AL", "PAGO DE", "PAGO A",
    "COSTO DE PRODUC", "COSTO PRODUC", "LIMPIEZA",
    "MONTAJE", "ARMADO", "ARMADURA", "TAPIZADO", "FORRO ", "COSTURA",
    "LIJADO", "LIJADA", "ACABADO",
)

# ---------------------------------------------------------------------------
# Normalización de unidades de medida
# ---------------------------------------------------------------------------
UNIDAD_ALIAS = {
    "CMS": ("Centímetros", "cm"), "CM": ("Centímetros", "cm"),
    "METROS": ("Metros", "m"), "METRO": ("Metros", "m"), "MTS": ("Metros", "m"),
    "MT": ("Metros", "m"), "M": ("Metros", "m"),
    "LITROS": ("Litros", "L"), "LITRO": ("Litros", "L"),
    "PISTOLADAS": ("Pistoladas", "pist"), "PISTOLADA": ("Pistoladas", "pist"), "PISTOLA": ("Pistoladas", "pist"),
    "GALONES": ("Galones", "gal"), "GALON": ("Galones", "gal"),
    "LAMINAS": ("Láminas", "lam"), "LAMINA": ("Láminas", "lam"),
    "CAJAS": ("Cajas", "cj"), "CAJA": ("Cajas", "cj"),
    "UNIDADES": ("Unidades", "und"), "UNIDAD": ("Unidades", "und"), "UND": ("Unidades", "und"),
    "UN": ("Unidades", "und"), "UNIIDAD": ("Unidades", "und"),
    "PIEZAS": ("Piezas", "pza"), "PIEZA": ("Piezas", "pza"),
    "PARES": ("Pares", "par"), "PAR": ("Pares", "par"),
    "TIRAS": ("Tiras", "tira"), "TIRA": ("Tiras", "tira"),
    "KILOS": ("Kilogramos", "kg"), "KILO": ("Kilogramos", "kg"), "KG": ("Kilogramos", "kg"),
    "ROLLO": ("Rollos", "rollo"), "ROLLOS": ("Rollos", "rollo"),
    "JALADORES": ("Jaladores", "jal"), "JALADOR": ("Jaladores", "jal"),
    "GOMAS": ("Gomas", "goma"), "GOMA": ("Gomas", "goma"),
    "COSTALES": ("Costales", "costal"), "COSTAL": ("Costales", "costal"),
    "BOTELLA": ("Botellas", "bot"), "BOTELLAS": ("Botellas", "bot"),
    "LATA": ("Latas", "lata"), "LATAS": ("Latas", "lata"),
    "TUBO": ("Tubos", "tubo"), "TUBOS": ("Tubos", "tubo"),
}

def normalizar_unidad(raw) -> str:
    if raw is None:
        return "und"
    t = str(raw).strip().upper()
    if not t:
        return "und"
    if "PEDA" in t or "PEDAZ" in t:
        return "pza"
    for key in ("PISTOLA", "GALON", "LITRO", "LAMINA", "CAJA", "UNIDAD", "METRO",
                "CMS", "CM", "TIRA", "PAR", "KILO", "PIEZA", "JALADOR", "ROLLO"):
        if key in t:
            return UNIDAD_ALIAS[key][1]
    return "und"

# ---------------------------------------------------------------------------
# Normalización de materiales
# ---------------------------------------------------------------------------
ALIAS_MATERIAL = {
    "GOLBON": "COLBON", "COLBÓN": "COLBON", "PEGANTE COLBON": "COLBON",
    "LAM MFF 9": "LAM MDF 9", "LAMINA DE 9": "LAM MDF 9", "LAMINA DE 9 MDF": "LAM MDF 9",
    "LAMINA DE 15": "LAM MDF 15", "MDF 15": "LAM MDF 15", "LAMINA DE 15\"": "LAM MDF 15",
    "LAMINA DE 2.5": "LAM MDF 2.5", "LAMINA DE 2,5": "LAM MDF 2.5",
    "LAMINA DE 2.5 MDF": "LAM MDF 2.5", "LAM MDF 2,5": "LAM MDF 2.5",
    "LAMINA DE 2.7": "LAM MDF 2.7", "LAM MDF 2,7": "LAM MDF 2.7",
    "LAMINA DE 5.5": "LAMINA DE 5.5", "LAMINA DE 5,5": "LAMINA DE 5.5", "LAM MDF 5,5": "LAMINA DE 5.5",
    "TORNILLOS DE 2": "TORNILLOS DE 2\"", "TORNILLO DE 2": "TORNILLOS DE 2\"",
    "GRAPA": "GRAPAS",
    "PEOPE": "PEOPLE", "POP": "PEOPLE", "PEO": "PEOPLE",
    "COLAPATOS": "COLA DE PATO", "COLAPATO": "COLA DE PATO",
    "CABUYA": "CABULLA",
    "EMBALADA": "EMBALAJE",
}

def normalizar_material(raw) -> str:
    s = str(raw or "").upper().strip().rstrip("* ,.:")
    s = " ".join(s.split())
    if not s:
        return ""
    s_clean = s.replace("\"", "")
    if s_clean in ALIAS_MATERIAL:
        return ALIAS_MATERIAL[s_clean]
    if s in ALIAS_MATERIAL:
        return ALIAS_MATERIAL[s]
    return s_clean

# ---------------------------------------------------------------------------
# Helpers numéricos y de fila
# ---------------------------------------------------------------------------
def dec(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    t = str(v).replace(",", ".").strip()
    m = re.search(r"\d+(?:\.\d+)?", t)
    if not m:
        return None
    try:
        return Decimal(m.group(0))
    except InvalidOperation:
        return None


def limpiar(texto):
    if texto is None:
        return ""
    return " ".join(str(texto).split())


def es_fila_vacia(vals):
    return not any(v is not None for v in vals)


def _precios(vals):
    """Devuelve (v_unit, total). El TOTAL autoritativo es la columna F (índice 5),
    la misma que suma el subtotal de la hoja; NUNCA se cae a la columna E, o filas
    sin cantidad (solo precio de referencia) se convertirían en insumos fantasma."""
    v_unit = dec(vals[4]) if len(vals) > 4 else None
    if v_unit is None or v_unit <= 0:
        v_unit = dec(vals[5]) if len(vals) > 5 else None
    total = dec(vals[5]) if len(vals) > 5 else None
    if total is not None and total <= 0:
        total = None
    return v_unit, total


def _total_col(vals):
    """Valor autoritativo de una fila de TOTALES (columna F)."""
    if len(vals) > 5:
        d = dec(vals[5])
        if d is not None and d > 0:
            return d
    return None


def _precio_fila(vals):
    nums = [dec(v) for v in vals if dec(v) is not None and dec(v) > 0]
    return nums[-1] if nums else None


def _cantidad(vals):
    if len(vals) <= 1:
        return None
    d = dec(vals[1])
    return d if (d is not None and d > 0) else None


def _primero_numero(texto):
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(texto))
    if not m:
        return None
    return dec(m.group(1))


def _porcentaje_en_texto(texto):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(texto))
    if not m:
        return None
    return dec(m.group(1))


# ---------------------------------------------------------------------------
# Definición de tipos de fila
# ---------------------------------------------------------------------------
TIPO_IGNORAR = "ignorar"
TIPO_SECCION = "seccion"
TIPO_GASTOS = "gastos"
TIPO_COSTO_PROD = "costo_prod"
TIPO_INSUMO = "insumo"
TIPO_TOTAL = "total"
TIPO_NOMBRE_PRODUCTO = "nombre_producto"


def _detectar_seccion(c1_up):
    m = SECCION_HEADER_PAT.search(c1_up)
    if m:
        base = _normalizar_seccion(m.group(1))
        resto = (m.group(2) or "").strip().upper()
        return base, resto
    m = SECCION_LONELY.search(c1_up)
    if m:
        return _normalizar_seccion(m.group(1)), ""
    return None


def _normalizar_seccion(txt):
    t = txt.upper().replace("TAPICERIA", "TAPICERÍA").replace("TERMINACION", "TERMINACIÓN") \
        .replace("EBANISTERIA", "EBANISTERÍA")
    t = re.sub(r"\s+", " ", t).strip()
    for canon in SECCIONES_BASE:
        if canon.upper() in t:
            return canon
    return t


def _sufijo_de_resto(resto, componente):
    if not resto:
        return None
    r = resto.upper()
    if "NOCHERO" in r:
        return "NOCHEROS"
    if "PATAS" in r or "PATA " in r:
        return "PATAS"
    if "CAMA " in r or "CAMA" in r:
        return "CAMA"
    if "PINTURA Y PREP" in r or "PREP" in r:
        return None
    return None


def clasificar_fila(vals):
    """(tipo, datos). Orden crítico: totales/basura → nombre producto → gastos → sección → costo → insumo."""
    if es_fila_vacia(vals):
        return (TIPO_IGNORAR, {})

    c1 = limpiar(vals[0]) if vals else ""
    if len(c1) < 2:
        return (TIPO_IGNORAR, {})
    c1_up = c1.upper()

    # Headers de sección a veces parten la palabra en dos celdas:
    # "SECCION PINTURA Y PREPAR" + "DE 2 NOCHEROS". Reensamblar texto.
    c1_sec = c1_up
    if "SECCION" in c1_up:
        c1_sec = " ".join(limpiar(v).upper() for v in vals[:4] if v)

    # Los encabezados "a secas" (TENDIDO, NOCHEROS, COLA DE PATO) solo son
    # sección cuando la fila NO trae números; una fila "NOCHEROS 2.0 ... 500000"
    # es un material comprado (mesas de noche), no una sección.
    tiene_nums = any(
        (dec(v) is not None and dec(v) > 0) for v in vals[1:]
    )

    # NOMBRE DEL PRODUCTO (puede aparecer varias veces: cama y luego nocheros)
    if "NOMBRE DEL PRODUCTO" in c1_up or "NOMBRE DEL PRODUCTO" in " | ".join(limpiar(v) for v in vals if v):
        valor = None
        for v in vals:
            t = limpiar(v)
            if "NOMBRE DEL PRODUCTO" in t.upper():
                continue
            if t:
                valor = t
                break
        return (TIPO_NOMBRE_PRODUCTO, {"valor": valor})

    # Texto de encabezado de tabla
    if any(tok in c1_up for tok in TEXTO_BASE_OCCUP_ROWS):
        return (TIPO_IGNORAR, {})

    # Filas calculadas a ignorar
    for p in IGNORAR_FILA_STARTS:
        if c1_up.startswith(p):
            return (TIPO_IGNORAR, {})

    # Totales (bloque final + subtotales por sección)
    if c1_up.startswith("TOTAL GASTOS") or c1_up.startswith("TOTAL DE GASTOS") or \
       c1_up.startswith("TOTAL PRODUCCION") or c1_up.startswith("TOTAL PRODUCCIÓN"):
        return (TIPO_TOTAL, {"label": "TOTAL_GASTOS", "valor": _total_col(vals) or _precio_fila(vals)})
    if c1_up.startswith("TOTAL COSTO DE PRODUC"):
        return (TIPO_TOTAL, {"label": "COSTO_PRODUCCION", "valor": _total_col(vals) or _precio_fila(vals)})
    if c1_up.startswith("TOTAL A PAGAR"):
        return (TIPO_TOTAL, {"label": "TOTAL_PAGAR", "valor": _total_col(vals) or _precio_fila(vals)})
    if c1_up.startswith("TOTAL COSTO"):
        return (TIPO_TOTAL, {"label": "TOTAL_COSTO", "valor": _total_col(vals) or _precio_fila(vals)})
    if re.match(r"^IVA\b", c1_up):
        return (TIPO_TOTAL, {"label": "IVA", "valor": _total_col(vals) or _precio_fila(vals)})
    if c1_up.startswith("PRECIO DE VENTA") or "PRECIO DE VENTA" in c1_up:
        return (TIPO_TOTAL, {"label": "PRECIO_VENTA", "valor": _total_col(vals) or _precio_fila(vals)})
    if "MÁS GANANCIA" in c1_up or "MAS GANANCIA" in c1_up or c1_up == "GANANCIA":
        return (TIPO_TOTAL, {"label": "GANANCIA", "valor": _total_col(vals) or _precio_fila(vals)})
    if "GANANCIA" in c1_up and c1_up.startswith("TOTAL"):
        return (TIPO_TOTAL, {"label": "GANANCIA", "valor": _total_col(vals) or _precio_fila(vals)})

    # Subtotal intermedio por sección (eliminar, no es un material)
    if re.match(r"^SUB\s*TOTAL\b", c1_up) or c1_up.replace(" ", "").replace("-", "") == "SUBTOTAL":
        return (TIPO_IGNORAR, {})

    # Subtotal intermedio mal etiquetado ("TOTAL DE VIDRIOS", "TOTAL DE...")
    if c1_up.startswith("TOTAL DE "):
        return (TIPO_IGNORAR, {})

    # Políticas de gastos ("gastos de Ebanisteria e 10", "Gastos de Pintura 10%")
    if "GASTOS" in c1_up:
        pct = _primero_numero(c1)
        return (TIPO_GASTOS, {"porcentaje": pct})

    # Encabezado de sección (solo si la fila no lleva precios/cantidades,
    # o si trae la palabra SECCION explícita)
    if not tiene_nums and not c1_up.startswith("SECCION"):
        pass  # candidato a sección "a secas"
    det = None
    if c1_up.startswith("SECCION") or not tiene_nums:
        det = _detectar_seccion(c1_sec)
    if det:
        return (TIPO_SECCION, {"base": det[0], "resto": det[1]})

    # Costos de producción / mano de obra.
    #  - por palabra clave fuerte (FABRICACION, HECHURA, MANO DE OBRA…) o
    #  - por señal de "%" en las primeras columnas ("X CON EL 5%") como en pintura.
    pct = None
    for v in vals[:4]:
        p = _porcentaje_en_texto(v)
        if p:
            pct = p
            break
    if any(c1_up.startswith(k) for k in COSTO_PROD_STARTS) or pct is not None:
        v_unit, total = _precios(vals)
        if total is None:
            return (TIPO_IGNORAR, {})  # sin monto (referencia), no es un material
        if pct:
            base = (total / (Decimal("1") + pct / Decimal("100"))).quantize(Decimal("0.01"))
        else:
            base = total
        return (TIPO_COSTO_PROD, {"texto": c1_up, "porcentaje": pct, "base": base, "total": total,
                                  "es_fabricacion": c1_up.startswith("FABRICAC")})

    # Insumo físico
    qty = _cantidad(vals)
    v_unit, total = _precios(vals)
    unidad = limpiar(vals[2]) if len(vals) > 2 else ""
    return (TIPO_INSUMO, {"nombre": c1_up, "qty": qty, "unidad": unidad, "base": v_unit, "total": total})


def _redondear(d, digitos):
    return d.quantize(Decimal("1." + "0" * digitos)) if d is not None else None


# ---------------------------------------------------------------------------
# Parseo de una hoja completa
# ---------------------------------------------------------------------------
def parsear_hoja(ws):
    rd = {
        "nombre_hoja": ws.title,
        "nombre_producto": None,
        "totales": {"TOTAL_GASTOS": [], "GANANCIA": None, "TOTAL_PAGAR": None, "IVA": None,
                    "TOTAL_COSTO": None, "COSTO_PRODUCCION": None, "PRECIO_VENTA": None},
        "precio_costo": None, "precio_venta": None, "precio_con_iva": None,
        "secciones": {},          # clave → {base, sufijo, insumos, costos, politica, total_declarado, componente}
        "orden": [],
        "referencia": [],
        "has_nocheros": False,
        "total_filas": 0,
    }

    componente = "CAMA"
    seccion_base = "EBANISTERÍA"
    seccion_sufijo = None

    def nueva_seccion(base, sufijo, comp):
        sufi = sufijo
        if sufi is None and base in ("EBANISTERÍA", "PINTURA") and rd["has_nocheros"]:
            sufi = comp
        clave = (base, sufi)
        if clave not in rd["secciones"]:
            rd["secciones"][clave] = {
                "base": base, "sufijo": sufijo, "componente": comp,
                "insumos": [], "costos": [],
                "politica": {"pct_gastos_seccion": None, "costo_fabricacion": None,
                             "pct_trabajadores": None, "mano_obra_base": None,
                             "pct_liquidacion_mo": Decimal("5.00"), "pct_negocio": None},
                "total_declarado": None,
            }
            rd["orden"].append(clave)
        return clave

    clave_actual = nueva_seccion(seccion_base, None, componente)

    for vals in ws.iter_rows(values_only=True):
        vals = list(vals)
        rd["total_filas"] += 1
        tipo, datos = clasificar_fila(vals)

        if tipo == TIPO_IGNORAR:
            continue

        if tipo == TIPO_NOMBRE_PRODUCTO:
            valor = (datos.get("valor") or "").strip()
            if valor:
                if not rd["nombre_producto"]:
                    rd["nombre_producto"] = valor[:200]
            if "NOCHERO" in (valor or "").upper() and "NOCHE" in (valor or "").upper().replace("NOCHERO", ""):
                pass
            if "NOCHERO" in (valor or "").upper():
                rd["has_nocheros"] = True
                componente = "NOCHEROS"
                clave_actual = nueva_seccion("EBANISTERÍA", None, componente)
            else:
                componente = "CAMA"
            continue

        if tipo == TIPO_TOTAL:
            et = datos.get("label")
            val = datos.get("valor")
            if et == "TOTAL_GASTOS" and val is not None:
                rd["secciones"][clave_actual].setdefault("totales_gastos", []).append(val)
                rd["totales"]["TOTAL_GASTOS"].append(val)
            elif et in rd["totales"] and val is not None:
                rd["totales"][et] = val
            continue

        if tipo == TIPO_SECCION:
            base = datos["base"]
            resto = datos["resto"]
            suf = _sufijo_de_resto(resto, componente)
            if suf == "NOCHEROS":
                rd["has_nocheros"] = True
                componente = "NOCHEROS"
            elif suf == "PATAS":
                componente = "CAMA"
            seccion_base = base
            seccion_sufijo = suf
            clave_actual = nueva_seccion(base, suf, componente if base != "NOCHEROS" else "NOCHEROS")
            continue

        if tipo == TIPO_GASTOS:
            rd["secciones"][clave_actual]["politica"]["pct_gastos_seccion"] = datos["porcentaje"]
            continue

        if tipo == TIPO_COSTO_PROD:
            base = datos["base"] or datos["total"] or Decimal("0")
            nombre = _nombre_costo(datos["texto"], rd["secciones"][clave_actual]["base"])
            rd["secciones"][clave_actual]["costos"].append(
                {"nombre": nombre, "base": base, "porcentaje": datos["porcentaje"],
                 "total_declarado": datos["total"]})
            if datos["es_fabricacion"]:
                pol = rd["secciones"][clave_actual]["politica"]
                pol["costo_fabricacion"] = base
                if datos["porcentaje"] is not None:
                    pol["pct_trabajadores"] = datos["porcentaje"]
            continue

        if tipo == TIPO_INSUMO:
            qty = datos["qty"]
            total = datos["total"]
            v_unit = datos["base"]

            # El monto SIEMPRE proviene de la columna PRECIO TOTAL (F).
            # Sin fallback qty×V/UNIT: cuando F=0 la hoja NO calculó el ítem
            # (filas de referencia / copiadas) y multiplicar inventa fantasmas
            # (ej. 900 × 140.000 = 126M en "MADERA 60X1X4").
            # Además: filas QUE SOLO tienen total (sin cantidad ni precio unitario)
            # son subtotales traspuestos ("PINTUTRA DE CAMA" 587.608,8) →
            # se descartan, no son un material.
            if total is None or total <= 0:
                rd["referencia"].append({"nombre": datos["nombre"], "unidad": datos["unidad"],
                                         "base": v_unit, "motivo": "sin_cantidad"})
                continue
            if (qty is None or qty <= 0) and (v_unit is None or v_unit <= 0):
                rd["referencia"].append({"nombre": datos["nombre"], "unidad": datos["unidad"],
                                         "base": total, "motivo": "subtotal_traspuesto"})
                continue

            qty2 = qty if (qty is not None and qty > 0) else Decimal("1")
            pu = (total / qty2).quantize(Decimal("0.01"))

            rd["secciones"][clave_actual]["insumos"].append({
                "nombre": datos["nombre"],
                "qty": qty2,
                "unidad": datos["unidad"],
                "precio_unitario": pu,
                "_total": total,
            })
            continue

    _finalizar(rd)
    return rd


def _nombre_costo(texto, seccion_base):
    t = re.sub(r"\bX\s*\d+(?:[.,]\d+)?\s*%$", "", texto).strip()
    t = re.sub(r"\s+", " ", t)
    if t == "HECHURA":
        t = f"HECHURA {seccion_base}"
    elif t == "PINTURA":
        t = f"PINTURA {seccion_base}"
    elif t == "PREPARADO":
        t = f"PREPARADO {seccion_base}"
    return t[:100]


def _finalizar(rd):
    # 1. Nombres finales de sección.
    #    Solo EBANISTERÍA y PINTURA distinguen "(CAMA)"/"(NOCHEROS)" cuando la
    #    hoja trae mesas de noche; el resto (TENDIDO, TERMINACIÓN, TAPICERÍA…)
    #    conserva nombre plano (igual que el producto de referencia).
    def display(clave):
        base, suf = clave
        if suf is None and base in ("EBANISTERÍA", "PINTURA") and rd["has_nocheros"]:
            suf = rd["secciones"][clave]["componente"] or "CAMA"
        return f"{base} ({suf})" if suf else base

    nuevas_claves = {}
    for clave in list(rd["orden"]):
        nuevo = display(clave)
        rd["secciones"][clave]["nombre"] = nuevo

    # 2. Inferir % de gastos por sección desde los TOTAL GASTOS de la hoja
    #    cuando el texto no traía el % (ej. "gastos de Ebanisteria" sin número).
    for clave in rd["orden"]:
        sec = rd["secciones"][clave]
        pol = sec["politica"]
        if pol["pct_gastos_seccion"] is None:
            subt = _subtotal_seccion(sec)
            if sec["total_declarado"] and sec["total_declarado"] > 0:
                t = sec["total_declarado"]
                if subt > 0 and t >= subt and t <= subt * Decimal("2.2"):
                    pct = ((t - subt) / subt) * 100
                    pct = _redondear(pct, 1)
                    if pct is not None and 0 <= pct <= 60:
                        pol["pct_gastos_seccion"] = pct
            elif "totales_gastos" in sec:
                val = max(sec["totales_gastos"]) if sec["totales_gastos"] else None
                if val and subt > 0 and val >= subt and val <= subt * Decimal("2.2"):
                    pct = ((val - subt) / subt) * 100
                    pct = _redondear(pct, 1)
                    if pct is not None and 0 <= pct <= 60:
                        pol["pct_gastos_seccion"] = pct

    # 3. Precio costo del producto: prioridad COSTO_PRODUCCION > max TOTAL_GASTOS de producto
    tots = rd["totales"]
    costo = tots["COSTO_PRODUCCION"]
    if costo is None:
        candidatos = [v for v in tots["TOTAL_GASTOS"] if v]
        if candidatos:
            costo = max(candidatos)
    rd["precio_costo"] = costo

    gan = tots["GANANCIA"]
    pagar = tots["TOTAL_PAGAR"]
    venta = tots["PRECIO_VENTA"]
    if pagar is not None:
        rd["precio_con_iva"] = pagar
        rd["precio_venta"] = pagar / Decimal("1.16")
    elif venta is not None:
        rd["precio_venta"] = venta
        rd["precio_con_iva"] = venta * Decimal("1.16")
    elif gan is not None and costo is not None:
        rd["precio_venta"] = costo + gan
        rd["precio_con_iva"] = rd["precio_venta"] * Decimal("1.16")
    elif costo is not None:
        rd["precio_venta"] = costo * Decimal("1.30")
        rd["precio_con_iva"] = rd["precio_venta"] * Decimal("1.16")


def _subtotal_seccion(sec):
    ins = sum((i.get("_total") or i["qty"] * i["precio_unitario"]) for i in sec["insumos"])
    cost0 = sum((c["base"]) for c in sec["costos"])
    return ins + cost0


def _merge_repetidos(rd):
    for clave in rd["orden"]:
        sec = rd["secciones"][clave]
        vistos = {}
        nuevos = []
        for ins in sec["insumos"]:
            k = ins["nombre"]
            if k in vistos:
                total_suma = vistos[k].get("_total", vistos[k]["qty"] * vistos[k]["precio_unitario"]) \
                    + ins.get("_total", ins["qty"] * ins["precio_unitario"])
                vistos[k]["qty"] += ins["qty"]
                vistos[k]["_total"] = total_suma
                if vistos[k]["qty"] > 0:
                    vistos[k]["precio_unitario"] = (total_suma / vistos[k]["qty"]).quantize(Decimal("0.01"))
            else:
                vistos[k] = dict(ins)
                nuevos.append(vistos[k])
        sec["insumos"] = nuevos


def _aplicar_totales_gastos_seccion(rd):
    """Convierte TOTAL GASTOS <sección> de la hoja en total_declarado por sección."""
    # los TOTALES llegan en orden; el último TOTAL GASTOS antes de otra sección o
    # del fin pertenece a la sección actual (si su magnitud es coherente).
    umbrales = []
    for clave in rd["orden"]:
        sec = rd["secciones"][clave]
        subt = _subtotal_seccion(sec)
        umbrales.append((clave, subt))
    # recorrido sencillo: el primer TOTAL_GASTOS tras la sección A pertenece a A
    #  → por eso se usó 'totales_gastos' por clave (ya asignados en el parse)
    for clave in rd["orden"]:
        sec = rd["secciones"][clave]
        tgs = sec.get("totales_gastos") or []
        if tgs:
            subt = _subtotal_seccion(sec)
            candidatos = [v for v in tgs if v <= subt * Decimal("2.2")]
            if candidatos:
                sec["total_declarado"] = max(candidatos)


# ---------------------------------------------------------------------------
# Cálculo del costo que produciría el ERP (misma fórmula que cost_service)
# ---------------------------------------------------------------------------
def total_erp_por_secciones(rd):
    total = Decimal("0")
    detalle = {}
    for clave in rd["orden"]:
        sec = rd["secciones"][clave]
        ins = sum((i.get("_total") or i["qty"] * i["precio_unitario"]) for i in sec["insumos"])
        cp = Decimal("0")
        for c in sec["costos"]:
            a = c["base"]
            if c["porcentaje"] is not None and c["porcentaje"] > 0:
                a += c["base"] * c["porcentaje"] / Decimal("100")
            cp += a
        subtotal = ins + cp
        pg = sec["politica"].get("pct_gastos_seccion") or Decimal("0")
        pn = sec["politica"].get("pct_negocio") or Decimal("0")
        tsec = subtotal + subtotal * pg / Decimal("100") + subtotal * pn / Decimal("100")
        total += tsec
        detalle.setdefault(sec["nombre"], {"insumos": 0.0, "costos": 0.0, "subtotal": 0.0,
                                           "gastos": 0.0, "total": 0.0})
        detalle[sec["nombre"]] = {
            "insumos": float(ins), "costos": float(cp), "subtotal": float(subtotal),
            "gastos": float(subtotal * pg / Decimal("100")), "total": float(tsec),
        }
    return total, detalle


# ---------------------------------------------------------------------------
# Evaluación (gate anti-inflación)
# ---------------------------------------------------------------------------
def evaluar_hoja(rd, umbral):
    _merge_repetidos(rd)
    _aplicar_totales_gastos_seccion(rd)
    _finalizar(rd)

    total_calc, detalle = total_erp_por_secciones(rd)
    declarado = rd["precio_costo"]
    delta = None
    if declarado and declarado > 0:
        delta = ((total_calc - declarado) / declarado) * 100

    insumos_sin_precio = sum(1 for c in rd["orden"] for i in rd["secciones"][c]["insumos"]
                             if i["precio_unitario"] <= 0)

    advertencias = []
    for ref in rd["referencia"][:8]:
        advertencias.append(f"referencia: {ref['nombre']}")
    if len(rd["referencia"]) > 8:
        advertencias.append(f"... y {len(rd['referencia']) - 8} más")

    estado = "OK"
    if not declarado:
        estado = "REVISAR_SIN_TOTAL"
    elif delta is not None and abs(delta) > umbral:
        estado = "BLOQUEADA"
    elif insumos_sin_precio:
        estado = "REVISAR_SIN_PRECIOS"
    elif not rd["secciones"]:
        estado = "BLOQUEADA"

    return {
        "total_calculado_erp": float(total_calc),
        "total_declarado_hoja": float(declarado) if declarado else None,
        "delta_pct": (float(delta) if delta is not None else None),
        "estado": estado,
        "advertencias": advertencias,
        "detalle_secciones": detalle,
        "insumos_sin_precio": insumos_sin_precio,
        "insumos_ref": len(rd["referencia"]),
        "costos_produccion": sum(len(rd["secciones"][c]["costos"]) for c in rd["orden"]),
        "total_insumos": sum(len(rd["secciones"][c]["insumos"]) for c in rd["orden"]),
    }


def fmon(v):
    return f"${v:,.2f}" if v is not None else "—"


# ---------------------------------------------------------------------------
# Conciliación contra el catálogo/inventario (solo lectura de BD)
# ---------------------------------------------------------------------------
def cargar_precios_catalog(db):
    """Mapea nombre normalizado → LISTA de precios material.costo_base.
    Devuelve dict: nombre_normalizado → [precios…] (hay duplicados del catálogo
    con precios distintos: la mamera vieja creó materiales repetidos).
    El precio 'de catálogo' se resuelve con la MEDIANA para no dejarse
    arrastrar por duplicados contaminados."""
    from app.modules.productos.model import Material, MaterialSinonimo

    mats = db.query(Material).all()
    precios = {}
    for m in mats:
        if m.costo_base and m.costo_base > 0:
            precios.setdefault(normalizar_material(m.nombre).upper(), []).append(m.costo_base)
    for s in db.query(MaterialSinonimo).all():
        k = normalizar_material(s.sinonimo).upper()
        if s.material_id:
            for m in mats:
                if m.id == s.material_id and m.costo_base and m.costo_base > 0:
                    precios.setdefault(k, []).append(m.costo_base)
                    break
    return precios


def _mediana(lst):
    ordenada = sorted(lst)
    n = len(ordenada)
    if n % 2 == 1:
        return ordenada[n // 2]
    return (ordenada[n // 2 - 1] + ordenada[n // 2]) / 2


def precio_catalogo(nombre, precios):
    """Precio representativo del catálogo para un insumo (mediana).
    Si el catálogo es dudoso (todos los precios se alejan >4× del precio de la
    hoja, p. ej. CLAVILLOS F40 1.000 vs 28.000), devuelve None → se conserva
    el precio de la hoja y se reporta."""
    cands = precios.get(normalizar_material(nombre).upper())
    if not cands:
        return None, False
    med = _mediana(cands)
    return med, True


def total_catalogo_secciones(rd, precios):
    """Repite el cálculo del ERP usando el PRECIO DEL CATÁLOGO actual (mediana)
    para cada insumo ('el insumo era más barato'). Insumos sin material en
    catálogo o con catálogo dudoso conservan el precio de la hoja.
    Devuelve (total_catalog, cobertura_%, muestras_de_diferencias, dudosos)."""
    total = Decimal("0")
    cubierto, todo = Decimal("0"), Decimal("0")
    diffs, dudosos = [], []
    for clave in rd["orden"]:
        sec = rd["secciones"][clave]
        ins = Decimal("0")
        for i in sec["insumos"]:
            monto = i.get("_total") or i["qty"] * i["precio_unitario"]
            pu_hoja = i["precio_unitario"] or Decimal("0")
            todo += monto
            pc, ok = precio_catalogo(i["nombre"], precios)
            if pc is not None and pc > 0:
                if pu_hoja > 0 and (pc > 4 * pu_hoja or pc < Decimal("0.25") * pu_hoja):
                    dudosos.append((i["nombre"][:34], float(pu_hoja), float(pc)))
                    ins += monto
                    continue
                monto_cat = i["qty"] * pc
                ins += monto_cat
                cubierto += monto
                if abs(monto_cat - monto) > monto * Decimal("0.5"):
                    diffs.append((i["nombre"][:34], float(monto), float(monto_cat)))
            else:
                ins += monto
        cp = Decimal("0")
        for c in sec["costos"]:
            a = c["base"]
            if c["porcentaje"] is not None and c["porcentaje"] > 0:
                a += c["base"] * c["porcentaje"] / Decimal("100")
            cp += a
        subtotal = ins + cp
        pg = sec["politica"].get("pct_gastos_seccion") or Decimal("0")
        total += subtotal + subtotal * pg / Decimal("100")
    cobertura = float(cubierto / todo * 100) if todo > 0 else 0.0
    return total, cobertura, diffs[:8], dudosos[:8]


def diagnostico_gate(rd, total_calc, declarado, umbral):
    """Explica POR QUÉ una hoja quedó BLOQUEADA (para la decisión de aprobación):
      - 'total_declarado_obsoleto': las secciones de la hoja cuadran entre sí
        (su subtotal = suma de sus TOTAL GASTOS), pero el TOTAL COSTO DE
        PRODUCCION del producto está desactualizado/olvida una sección
        (ej. NOCHEROS). Las secciones son la fuente de verdad.
      - 'desglose_incompleto': la hoja declara dinero que sus filas de ítems no
        respaldan (ej. PINTURA 477.895 sin cantidades). No es importable sin
        completar el Excel.
    """
    if declarado and abs((total_calc - declarado) / declarado) * 100 <= umbral:
        return "ok"
    suma_sec_decl = Decimal("0")
    suma_sec_nuestras = Decimal("0")
    sin_declarado = []
    for clave in rd["orden"]:
        sec = rd["secciones"][clave]
        subt = _subtotal_seccion(sec)
        pg = sec["politica"].get("pct_gastos_seccion") or Decimal("0")
        tsec = subt + subt * pg / Decimal("100")
        if sec.get("total_declarado"):
            suma_sec_decl += sec["total_declarado"]
            suma_sec_nuestras += tsec
        else:
            sin_declarado.append(sec["nombre"])
    if suma_sec_decl > 0 and abs(suma_sec_nuestras - suma_sec_decl) <= max(suma_sec_decl * Decimal("0.03"), Decimal("3000")):
        return "total_declarado_obsoleto"
    return "desglose_incompleto"


# ---------------------------------------------------------------------------
# Persistencia (solo --write)
# ---------------------------------------------------------------------------
def persistir_hoja(db, rd, gate, args):
    from app.modules.productos.model import (
        Producto, Material, MaterialSinonimo, SeccionProducto, ElementoSeccion,
        PoliticaSeccion, CostoProduccionSeccion,
    )
    from app.modules.catalogos.model import TipoProducto, UnidadMedida

    producto = None
    if rd["nombre_hoja"]:
        producto = db.query(Producto).filter(Producto.hoja_excel == rd["nombre_hoja"]).first()
    # Fallback SOLO para productos legado sin hoja asignada: nunca mergear entre
    # hojas del Excel, porque hay hojas renombradas con el mismo header interno
    # (p. ej. 'CAMA DE MELAMINA 1.60 ISIDRO' y '2X2 ISIDRO' comparten header).
    if not producto and rd["nombre_producto"]:
        producto = db.query(Producto).filter(Producto.nombre == rd["nombre_producto"],
                                              Producto.hoja_excel.is_(None)).first()
    if not producto and rd["nombre_producto"]:
        limpo = re.sub(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", "", rd["nombre_producto"])
        limpo = re.sub(r"\d+[xX*]\d+", "", limpo)
        limpo = " ".join(limpo.split()).strip()
        if limpo:
            producto = db.query(Producto).filter(Producto.nombre.ilike(f"%{limpo}%"),
                                                 Producto.hoja_excel.is_(None)).first()

    tipo_cama = db.query(TipoProducto).filter(TipoProducto.nombre.ilike("%cama%")).first()
    if not producto:
        producto = Producto(
            nombre=(rd["nombre_producto"] or f"CAMA MODELO {rd['nombre_hoja']}")[:150],
            tipo_producto_id=tipo_cama.id if tipo_cama else 1,
            activo=True, hoja_excel=rd["nombre_hoja"],
            ancho_base=Decimal("1.60"), largo_base=Decimal("1.90"),
            precio_costo_base=rd["precio_costo"], precio_venta_base=rd["precio_venta"],
            precio_venta_con_iva=rd["precio_con_iva"],
        )
        db.add(producto)
        db.flush()
    else:
        producto.hoja_excel = rd["nombre_hoja"]
        if rd["precio_costo"] is not None:
            producto.precio_costo_base = rd["precio_costo"]
        if rd["precio_venta"] is not None:
            producto.precio_venta_base = rd["precio_venta"]
        if rd["precio_con_iva"] is not None:
            producto.precio_venta_con_iva = rd["precio_con_iva"]
        db.flush()

    db.query(SeccionProducto).filter(SeccionProducto.producto_id == producto.id).delete()
    db.flush()

    materiales = {}
    for m in db.query(Material).all():
        materiales.setdefault(normalizar_material(m.nombre).upper(), m)
        materiales.setdefault(limpiar(m.nombre).upper(), m)
    sinonimos = {}
    for s in db.query(MaterialSinonimo).all():
        sinonimos.setdefault(limpiar(s.sinonimo).upper(), s.material_id)
    unidades = {}
    for u in db.query(UnidadMedida).all():
        unidades.setdefault(limpiar(u.abreviatura).upper(), u)
        unidades.setdefault(limpiar(u.nombre).upper(), u)

    def get_unidad(abbr):
        key = (abbr or "und").upper()
        if key in unidades:
            return unidades[key]
        nombre, abr = UNIDAD_ALIAS.get(key, ("Unidades", "und"))
        u = UnidadMedida(nombre=nombre, abreviatura=abr[:10])
        db.add(u)
        db.flush()
        unidades[abr.upper()] = u
        return u

    def get_material(nombre_raw, pref_abbr, precio):
        nc = normalizar_material(nombre_raw).upper()
        mat = materiales.get(nc) or materiales.get(nc.replace('"', ''))
        if not mat and nc in sinonimos:
            mat = db.query(Material).filter(Material.id == sinonimos[nc]).first()
        if mat:
            return mat, False
        unm = get_unidad(pref_abbr)
        mat = Material(
            nombre=(nombre_raw or "")[:150],
            unidad_medida_id=unm.id,
            costo_base=precio if (precio is not None and precio > 0) else Decimal("0"),
            activo=True,
        )
        db.add(mat)
        db.flush()
        materiales[nc] = mat
        for alias, canon in ALIAS_MATERIAL.items():
            if normalizar_material(canon).upper() == nc and alias.upper() != (nombre_raw or "").upper():
                if not db.query(MaterialSinonimo).filter(MaterialSinonimo.sinonimo.ilike(alias)).first():
                    db.add(MaterialSinonimo(material_id=mat.id, sinonimo=alias))
        return mat, True

    def precio_catalogo_mediana(nombre_raw):
        """Mediana de costo_base entre TODOS los materiales con el mismo nombre
        normalizado (el catálogo tiene duplicados contaminados por la mamera
        vieja; la mediana es representativa)."""
        nc = normalizar_material(nombre_raw).upper()
        precios = []
        for m in db.query(Material).all():
            if normalizar_material(m.nombre).upper() == nc and m.costo_base and m.costo_base > 0:
                precios.append(m.costo_base)
        if not precios:
            return None
        return _mediana(precios)

    nuevas_claves = []
    for clave in rd["orden"]:
        if clave not in nuevas_claves:
            nuevas_claves.append(clave)

    for idx, clave in enumerate(nuevas_claves):
        sec = rd["secciones"][clave]
        nombre = sec["nombre"]
        db_sec = SeccionProducto(producto_id=producto.id, nombre=nombre[:100], orden=idx + 1)
        db.add(db_sec)
        db.flush()

        pol = sec["politica"]
        db.add(PoliticaSeccion(
            seccion_id=db_sec.id,
            mano_obra_base=pol["mano_obra_base"] or Decimal("0"),
            pct_liquidacion_mo=pol["pct_liquidacion_mo"] or Decimal("5.00"),
            pct_gastos_seccion=pol["pct_gastos_seccion"] or Decimal("0"),
            costo_fabricacion=pol["costo_fabricacion"],
            pct_trabajadores=pol["pct_trabajadores"],
            pct_negocio=pol["pct_negocio"] or Decimal("0"),
        ))

        for c in sec["costos"]:
            db.add(CostoProduccionSeccion(
                seccion_id=db_sec.id, nombre=c["nombre"][:200],
                porcentaje=c["porcentaje"], costo_base=c["base"],
            ))

        for i in sec["insumos"]:
            mat, creado = get_material(i["nombre"], i["unidad"], i["precio_unitario"])
            qty = i["qty"]
            pu = i["precio_unitario"]
            subtotal = i.get("_total") or qty * pu
            if getattr(args, "reprice_from_catalog", False):
                pu_cat = precio_catalogo_mediana(i["nombre"])
                if pu_cat is not None and pu_cat > 0 and pu_cat != pu:
                    pu = pu_cat
                    subtotal = qty * pu_cat
            db.add(ElementoSeccion(
                seccion_id=db_sec.id,
                nombre_insumo_original=i["nombre"][:150],
                material_id_normalizado=mat.id,
                estado_resolucion="MAPEADO" if not creado else "PENDIENTE",
                cantidad=qty,
                unidad_medida=limpiar(i["unidad"])[:50],
                precio_unitario=pu,
                costo_subtotal=subtotal,
                observaciones=f"hoja:{rd['nombre_hoja']}" if creado else None,
            ))

    return producto.id


# ---------------------------------------------------------------------------
# Auditoría de catálogo: duplicados vs precios de las 68 hojas (solo lectura)
# ---------------------------------------------------------------------------
def _ruta(p):
    """Resuelve rutas relativas contra la raíz del repo (docs/…)."""
    path = Path(p)
    if path.is_absolute():
        return path
    repo_rel = REPO / path
    return repo_rel if (repo_rel.parent.exists()) else path


def _grupos_catalog(args):
    """Devuelve (hoja_prices, por_nombre, uso):
    - hoja_prices: nombre normalizado → [precios unitarios vistos en las hojas]
    - por_nombre:   nombre normalizado → [Material…] (ordenados por precio desc)
    - uso:          material_id → nº de ElementoSeccion que lo referencian
    Solo lectura."""
    from app.modules.productos.model import Material, ElementoSeccion
    from app.db.session import session_local

    wb = openpyxl.load_workbook(args.excel, data_only=True)
    hoja_prices = {}
    for sname in wb.sheetnames:
        rd = parsear_hoja(wb[sname])
        if not rd["secciones"]:
            continue
        for clave in rd["orden"]:
            for i in rd["secciones"][clave]["insumos"]:
                pu = i["precio_unitario"]
                if pu and pu > 0:
                    k = normalizar_material(i["nombre"]).upper()
                    hoja_prices.setdefault(k, []).append(float(pu))

    db = session_local()
    mats = db.query(Material).all()
    uso = {}
    for e in db.query(ElementoSeccion).all():
        if e.material_id_normalizado:
            uso[e.material_id_normalizado] = uso.get(e.material_id_normalizado, 0) + 1
    por_nombre = {}
    for m in mats:
        k = normalizar_material(m.nombre).upper()
        por_nombre.setdefault(k, []).append(m)
    db.close()
    for k in por_nombre:
        por_nombre[k].sort(key=lambda x: -(x.costo_base or 0))
    return hoja_prices, por_nombre, uso


def _consenso_hoja(hoja):
    if not hoja:
        return None
    return max(set(hoja), key=hoja.count)


def auditoria_catalog(args):
    """Cruza la tabla material contra los precios de las hojas del Excel.
    Detecta duplicados por nombre normalizado y precios contaminados
    (la mamera vieja creó materiales repetidos a precios fantasma)."""
    hoja_prices, por_nombre, uso = _grupos_catalog(args)
    mats_total = sum(len(g) for g in por_nombre.values())

    print(f"\n AUDITORÍA DE CATÁLOGO — {mats_total} materiales, {len(por_nombre)} nombres normalizados")
    reporte = {"materiales": mats_total, "nombres": len(por_nombre), "grupos": []}
    grupos_fallos = 0
    for k, grupo in sorted(por_nombre.items()):
        precios_db = sorted({float(m.costo_base) for m in grupo if m.costo_base and m.costo_base > 0})
        hoja = hoja_prices.get(k, [])
        modo_hoja = _consenso_hoja(hoja)
        if modo_hoja is None:
            if len(precios_db) <= 1:
                continue
            estado = "INCIERTO"
        elif len(precios_db) <= 1 and precios_db and abs(precios_db[0] - modo_hoja) <= modo_hoja * 0.25:
            continue  # sano
        else:
            malos = [p for p in precios_db if abs(p - modo_hoja) > modo_hoja * 0.25]
            if not malos:
                continue  # duplicados a precios coherentes
            estado = "POLLUCION"

        grupos_fallos += 1
        filas = [{
            "id": m.id, "nombre": m.nombre, "precio": float(m.costo_base or 0),
            "activo": m.activo, "en_uso": uso.get(m.id, 0),
        } for m in grupo]
        reporte["grupos"].append({
            "nombre": k, "estado": estado,
            "precio_hojas": modo_hoja, "n_hojas": len(hoja),
            "precios_db": precios_db, "materiales": filas,
        })
        print(f"\n{estado:>10}  {k[:46]}")
        print(f"           hoja consenso: {fmon(Decimal(str(modo_hoja))) if modo_hoja else '—'}  ({len(hoja)} apariciones) | en BD: " +
              ", ".join(f"{p:,.0f}" for p in precios_db) or "sin precio")
        for f in filas:
            print(f"           · id {f['id']:<5} {f['nombre'][:40]:<42} {f['precio']:>12,.0f}  activo={f['activo']} usos={f['en_uso']}")
    print(f"\nGrupos que requieren acción: {grupos_fallos}")
    import json as _json
    p = _ruta(args.audit_catalog)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(reporte, ensure_ascii=False, indent=1))
    print(f" Auditoría catálogo → {p}")


def aplicar_limpieza_catalog(args):
    """Consolida duplicados contaminados:
    - costo_base de CADA material del grupo = precio consenso (hojas o mediana).
    - se DESACTIVA cada miembro que es redundancia pura: no referenciado y con
      el mismo precio del consenso (queda 1 activo sin uso por grupo).
    Muestra el plan; sin --commit no toca la BD."""
    from app.modules.productos.model import Material, ElementoSeccion
    from app.db.session import session_local

    hoja_prices, por_nombre, uso = _grupos_catalog(args)
    db = session_local()
    cambios_precio = 0
    desactivar = []
    plan = []
    for k, grupo in sorted(por_nombre.items()):
        precios_db = sorted({float(m.costo_base) for m in grupo if m.costo_base and m.costo_base > 0})
        hoja = hoja_prices.get(k, [])
        modo_hoja = _consenso_hoja(hoja)
        tiene_ground_truth = modo_hoja is not None
        if not tiene_ground_truth:
            canon = None
        else:
            canon = Decimal(str(modo_hoja))
        # si algo referenciado sigue activo con precio distinto, el consenso pesa igual
        miembro_canon = [m for m in grupo if canon is not None and m.costo_base and abs(float(m.costo_base) - float(canon)) <= float(canon) * 0.25]
        en_uso = [m for m in grupo if uso.get(m.id, 0) > 0]
        if not miembro_canon and en_uso:
            if canon is None:
                canon = en_uso[0].costo_base or Decimal("0")
                tiene_ground_truth = True
            miembro_canon = [en_uso[0]]
        se_toca = tiene_ground_truth and any(m.costo_base != canon for m in grupo)
        if not se_toca and len(grupo) == 1:
            continue
        plan_k = {"nombre": k, "canon": float(canon) if canon is not None else None,
                  "precios_db": precios_db, "materiales": []}
        for idx, m in enumerate(grupo):
            cambio = tiene_ground_truth and canon is not None and m.costo_base != canon
            plan_k["materiales"].append({
                "id": m.id, "nombre": m.nombre, "precio": float(m.costo_base or 0),
                "nuevo_precio": float(canon) if cambio else None,
                "activo": m.activo, "en_uso": uso.get(m.id, 0), "desactivar": False,
            })
            if cambio:
                cambios_precio += 1
        # redundancia pura: mismo precio, sin uso → desactivar (guarda 1 activo)
        if len(grupo) > 1:
            usados_activos = [m for m in grupo if uso.get(m.id, 0) > 0 and m.activo]
            if canon is not None:
                con_canon = [m for m in grupo if m.activo and m.costo_base and abs(float(m.costo_base) - float(canon)) <= float(canon) * 0.25]
                candidatos = con_canon
            else:
                precios_posibles = sorted({float(m.costo_base) for m in grupo if m.costo_base and m.costo_base > 0})
                canon_dedupe = _mediana([Decimal(str(p)) for p in precios_posibles]) if precios_posibles else None
                candidatos = [m for m in grupo if m.activo and m.costo_base and canon_dedupe is not None and abs(float(m.costo_base) - float(canon_dedupe)) <= float(canon_dedupe) * 0.25]
            if not usados_activos and len(candidatos) >= 1:
                keep = candidatos[0]
                for j, m in enumerate(grupo):
                    if m.id != keep.id and uso.get(m.id, 0) == 0 and m.activo:
                        plan_k["materiales"][j]["desactivar"] = True
                        desactivar.append(m.id)
            elif not usados_activos:
                # sin canon ni referencia: conserva el de mayor precio activo
                keep = max([m for m in grupo if m.activo], key=lambda x: -(x.costo_base or 0), default=None)
                if keep is not None:
                    for j, m in enumerate(grupo):
                        if m.id != keep.id and uso.get(m.id, 0) == 0 and m.activo:
                            plan_k["materiales"][j]["desactivar"] = True
                            desactivar.append(m.id)
        plan.append(plan_k)

    print(f"\n PLAN DE LIMPIEZA — {len(plan)} grupos, {cambios_precio} precios a corregir, {len(desactivar)} duplicados a desactivar")
    import json as _json
    p = _ruta(args.audit_catalog.replace("auditoria_catalog.json", "plan_limpieza_catalog.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(plan, ensure_ascii=False, indent=1))
    for g in plan:
        act = sum(1 for m in g["materiales"] if m["desactivar"])
        canon = g["canon"] if g["canon"] is not None else 0
        print(f"  {g['nombre'][:40]:<42} canon {canon:>12,.0f} | {len(g['materiales'])} mats, {sum(1 for m in g['materiales'] if m['nuevo_precio']) } precios, {act} a desactivar")

    if args.commit:
        n_ids = {m["id"] for g in plan for m in g["materiales"]}
        mats = db.query(Material).filter(Material.id.in_(n_ids)).all() if n_ids else []
        for g in plan:
            canon = Decimal(str(g["canon"])) if g["canon"] is not None else None
            for det in g["materiales"]:
                m = next((x for x in mats if x.id == det["id"]), None)
                if m is None:
                    continue
                if det["nuevo_precio"] is not None and canon is not None:
                    m.costo_base = canon
                if det["desactivar"]:
                    m.activo = False
        db.commit()
        print(f" Aplicado: {cambios_precio} precios corregidos, {len(desactivar)} materiales desactivados")
        print(f" Plan → {p}")
    else:
        print("   (modo plan — verifica y repite con --commit para escribir en la BD)")


def main():
    ap = argparse.ArgumentParser(description="Importador seguro de estructuras de costos del Excel YEIKAR")
    ap.add_argument("--excel", default=str(EXCEL_DEFAULT))
    ap.add_argument("--sheet", action="append", default=None, help="Solo esta hoja (repetible)")
    ap.add_argument("--sheets-file", default=None, help="Archivo con nombres de hojas aprobadas (1 por línea)")
    ap.add_argument("--write", action="store_true", help="Escribir a la BD (por defecto solo audita)")
    ap.add_argument("--reprice-from-catalog", action="store_true",
                    help="Al escribir, usar el precio actual del catálogo (material.costo_base) "
                         "en vez del precio viejo de la hoja para cada insumo que tenga material.")
    ap.add_argument("--reconcile", action=argparse.BooleanOptionalAction, default=True,
                    help="Cruzar cada hoja contra el catálogo de materiales (solo lectura). "
                         "Desactiva con --no-reconcile para auditoría sin BD.")
    ap.add_argument("--threshold", type=float, default=15.0)
    ap.add_argument("--force", action="store_true", help="Escribir aunque esté BLOQUEADA")
    ap.add_argument("--fijar-costo-computado", action="store_true",
                    help="Al escribir, usar el total calculado por el ERP (suma de secciones) "
                         "como precio_costo_base del producto en vez del total declarado de la hoja "
                         "(recomendado para hojas bloqueadas por total obsoleto/desglose incompleto).")
    ap.add_argument("--json", default=None, help="Guardar reporte completo (JSON)")
    ap.add_argument("--audit-catalog", nargs="?", const="docs/auditoria_catalog.json", default=None,
                    help="Auditar duplicados del catálogo vs precios de las hojas (solo lectura). "
                         "Ruta opcional del reporte.")
    ap.add_argument("--cleanup-catalog", action="store_true",
                    help="Generar/plan de consolidación de duplicados contaminados del catálogo "
                         "(por defecto solo muestra el plan; usa --commit para escribir).")
    ap.add_argument("--commit", action="store_true", help="En --cleanup-catalog: escribir los cambios a la BD.")
    args = ap.parse_args()

    if args.audit_catalog is not None and args.cleanup_catalog:
        args.audit_catalog = args.audit_catalog
    if args.cleanup_catalog:
        if args.audit_catalog is None:
            args.audit_catalog = "docs/auditoria_catalog.json"
        aplicar_limpieza_catalog(args)
        return
    if args.audit_catalog is not None:
        auditoria_catalog(args)
        return

    aprobadas_set = set(args.sheet or [])
    if args.sheets_file:
        p = Path(args.sheets_file)
        if p.exists():
            aprobadas_set |= {l.strip() for l in p.read_text().splitlines() if l.strip()}

    wb = openpyxl.load_workbook(args.excel, data_only=True)
    print(f" Excel: {args.excel}")
    print(f"   Hojas: {len(wb.sheetnames)} | {'MODO ESCRITURA' if args.write else 'MODO AUDITORÍA (no toca la BD)'}")

    db = None
    precios_catalog = {}
    if args.write:
        from app.db.session import session_local
        db = session_local()
        precios_catalog = cargar_precios_catalog(db)
    elif args.reconcile:
        try:
            from app.db.session import session_local
            db = session_local()
            precios_catalog = cargar_precios_catalog(db)
            db.close()
            db = None
        except Exception:
            print("   (aviso: no se pudo conectarse a la BD para conciliar catálogo; se omite)")
    repricers = args.reprice_from_catalog

    resumen = []
    total_ok = total_bloqueada = total_revisar = total_escribir = 0
    try:
        for sname in wb.sheetnames:
            if args.sheet or args.sheets_file:
                if sname not in aprobadas_set:
                    continue
            rd = parsear_hoja(wb[sname])

            if not rd["secciones"] and not rd["nombre_producto"]:
                resumen.append({"hoja": sname, "etiquetas_costo": "",
                                "estado": "SIN_DATOS", "secciones": 0, "total_insumos": 0,
                                "costos_prod": 0, "total_calc": 0.0, "total_hoja": None,
                                "delta": None, "producto": None})
                resultados_print = f" {sname.strip()[:60]}  → SIN_DATOS (hoja índice)"
                print(f"\n{resultados_print}")
                continue

            gate = evaluar_hoja(rd, args.threshold)

            print(f"\n {sname.strip()[:60]}")
            print(f"   Producto: {rd['nombre_producto'] or '—'}")
            for clave in rd["orden"]:
                s = rd["secciones"][clave]
                pg = s["politica"].get("pct_gastos_seccion")
                print(f"     ◆ {s['nombre']:<28} {len(s['insumos']):>3} insumos | "
                      f"{len(s['costos']):>1} costo(s) prod | gastos={pg}%" if pg is not None else
                      f"     ◆ {s['nombre']:<28} {len(s['insumos']):>3} insumos | "
                      f"{len(s['costos']):>1} costo(s) prod | gastos=—")

            estado = gate["estado"]
            if estado == "OK":
                total_ok += 1
            elif estado == "BLOQUEADA":
                total_bloqueada += 1
            else:
                total_revisar += 1

            # Conciliación con catálogo + diagnóstico del gate
            diag = None
            tcatalog, cobertura, diffs_cat, dudosos_cat = None, None, [], []
            if precios_catalog:
                declarado_gate = rd["precio_costo"]
                tcatalog, cobertura, diffs_cat, dudosos_cat = total_catalogo_secciones(rd, precios_catalog)
                if estado == "BLOQUEADA":
                    diag = diagnostico_gate(rd, Decimal(str(gate["total_calculado_erp"])),
                                            declarado_gate, args.threshold)
                    print(f"    diagnóstico: {diag if diag != 'desglose_incompleto' else 'desglose incompleto en la hoja (dinero declarado sin ítems)'}")
                if diag == "total_declarado_obsoleto":
                    print(f"    sus secciones cuadran entre sí; el TOTAL del producto olvida una sección. Importable por secciones.")

            dd = f"{gate['delta_pct']:+.1f}%" if gate["delta_pct"] is not None else "??"
            print(f"   → ERP calcula: {fmon(gate['total_calculado_erp'])} | "
                  f"hoja declara: {fmon(gate['total_declarado_hoja'])} | Δ: {dd} | {estado}")
            if tcatalog is not None:
                print(f"   → re-preciado a catálogo: {fmon(tcatalog)} "
                      f"(insumos cubiertos {cobertura:.0f}%)")

            for adv in gate["advertencias"]:
                print(f"      {adv}")
            if diffs_cat:
                print(f"      precios hoja vs catálogo (más de ±50%):")
                for n, a, b in diffs_cat:
                    print(f"       · {n:<34} hoja {a:>12,.0f} vs catálogo {b:>12,.0f}")
            if dudosos_cat:
                print(f"      catálogo dudoso (precio unitario en catálogo >4× o <¼ el de la hoja; se conserva hoja):")
                for n, a, b in dudosos_cat:
                    print(f"       · {n:<34} hoja {a:>12,.0f} vs catálogo {b:>12,.0f} /unidad")

            resumen.append({
                "hoja": sname, "producto": rd["nombre_producto"], "estado": estado,
                "secciones": len(rd["orden"]), "total_insumos": gate["total_insumos"],
                "costos_prod": gate["costos_produccion"], "total_calc": gate["total_calculado_erp"],
                "total_hoja": gate["total_declarado_hoja"], "delta": gate["delta_pct"],
                "diagnostico": diag,
                "total_catalog": float(tcatalog) if tcatalog is not None else None,
                "cobertura_catalog": cobertura,
                "precios_devian_catalog": [{"material": n, "hoja": a, "catalogo": b} for n, a, b in diffs_cat],
                "catalogo_dudoso": [{"material": n, "hoja": a, "catalogo": b} for n, a, b in dudosos_cat],
                "advertencias": gate["advertencias"],
            })

            if args.write:
                if estado == "BLOQUEADA" and not args.force:
                    print("    BLOQUEADA por umbral — no se escribe (usa --force para forzar)")
                    continue
                if args.fijar_costo_computado and gate["total_calculado_erp"] is not None and gate["total_calculado_erp"] > 0:
                    costo_computado = Decimal(str(gate["total_calculado_erp"]))
                    rd["precio_costo"] = costo_computado
                    if rd.get("precio_venta") is None or (rd.get("precio_venta") or Decimal("0")) <= 0:
                        rd["precio_venta"] = (costo_computado * Decimal("1.30")).quantize(Decimal("0.01"))
                    if rd.get("precio_con_iva") is None or (rd.get("precio_con_iva") or Decimal("0")) <= 0:
                        rd["precio_con_iva"] = (rd["precio_venta"] * Decimal("1.16")).quantize(Decimal("0.01"))
                try:
                    pid = persistir_hoja(db, rd, gate, args)
                    db.commit()
                    total_escribir += 1
                    print(f"    ESCRITO -> Producto #{pid}")
                except Exception as e:
                    db.rollback()
                    print(f"    Error: {e}")

        print("\n" + "=" * 100)
        print("RESUMEN DE AUDITORÍA")
        print(f"{'HOJA':<58} {'ESTADO':<18} {'SECC':>4} {'INS':>4} {'CP':>3} {'Δ%':>7} {'TOTAL ERP':>14}")
        for r in sorted(resumen, key=lambda x: (x["estado"], x["hoja"])):
            d = f"{r['delta']:+.1f}" if r["delta"] is not None else "  —"
            print(f"{r['hoja'][:58]:<58} {r['estado']:<18} {r['secciones']:>4} {r['total_insumos']:>4} "
                  f"{r['costos_prod']:>3} {d:>7} {r['total_calc']:>14,.2f}")
        print(f"\nOK: {total_ok} | REVISAR: {total_revisar} | BLOQUEADAS: {total_bloqueada}"
              + (f" | ESCRITOS: {total_escribir}" if args.write else ""))

        if args.json:
            Path(args.json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json).write_text(json.dumps({"resumen": resumen}, ensure_ascii=False, indent=2, default=str))
            print(f" Reporte JSON → {args.json}")

    finally:
        if db:
            db.close()


if __name__ == "__main__":
    main()