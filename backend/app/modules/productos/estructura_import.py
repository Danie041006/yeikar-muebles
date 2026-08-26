"""Importación de estructuras de costos pegadas desde Excel (copy-paste).

El flujo de negocio: la estructura de costos se arma en Excel (una hoja por
producto, columnas MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL, con
filas SECCION X, líneas de mano de obra tipo "HECHURA/PREPARADO/FABRICACION
300.000 *8% ..." y líneas "gastos de X e N%"). El usuario copia las filas de
la hoja y las pega en el ERP; este módulo las clasifica con las MISMAS reglas
del importador masivo (scripts/importar_estructuras_v2.py) y crea el Producto
con su estructura jerárquica completa, calculando el costo con la misma
fórmula del motor (cost_service) para que los precios den iguales.

Filosofía de tasas: no se consultan tasas guardadas; los precios vienen del
propio Excel (columna PRECIO TOTAL).
"""
import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.productos import model
from app.modules.auditoria.service import record_event

MONEDA_BASE_ID = 1

# ---------------------------------------------------------------------------
# Reglas de clasificación (port de scripts/importar_estructuras_v2.py)
# ---------------------------------------------------------------------------
SECCIONES_BASE = ("EBANISTERÍA", "PINTURA", "TAPICERÍA", "TENDIDO",
                  "COLA DE PATO", "TERMINACIÓN", "NOCHEROS")

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

UNIDAD_ALIAS = {
    "CMS": "cm", "CM": "cm", "METROS": "m", "METRO": "m", "MTS": "m", "MT": "m", "M": "m",
    "LITROS": "L", "LITRO": "L", "PISTOLADAS": "pist", "PISTOLADA": "pist", "PISTOLA": "pist",
    "GALONES": "gal", "GALON": "gal", "LAMINAS": "lam", "LAMINA": "lam",
    "CAJAS": "cj", "CAJA": "cj", "UNIDADES": "und", "UNIDAD": "und", "UND": "und", "UN": "und",
    "PIEZAS": "pza", "PIEZA": "pza", "PARES": "par", "PAR": "par", "TIRAS": "tira", "TIRA": "tira",
    "KILOS": "kg", "KILO": "kg", "KG": "kg", "ROLLO": "rollo", "ROLLOS": "rollo",
    "JALADORES": "jal", "JALADOR": "jal", "GOMAS": "goma", "GOMA": "goma",
    "COSTALES": "costal", "COSTAL": "costal", "BOTELLA": "bot", "BOTELLAS": "bot",
    "LATA": "lata", "LATAS": "lata", "TUBO": "tubo", "TUBOS": "tubo", "APAMATE": "apamate",
}

ALIAS_MATERIAL = {
    "GOLBON": "COLBON", "COLBÓN": "COLBON", "PEGANTE COLBON": "COLBON",
    "LAM MFF 9": "LAM MDF 9", "LAMINA DE 9": "LAM MDF 9", "LAMINA DE 9 MDF": "LAM MDF 9",
    "LAMINA DE 15": "LAM MDF 15", "MDF 15": "LAM MDF 15",
    "LAMINA DE 2.5": "LAM MDF 2.5", "LAMINA DE 2,5": "LAM MDF 2.5",
    "LAMINA DE 2.5 MDF": "LAM MDF 2.5", "LAM MDF 2,5": "LAM MDF 2.5",
    "LAMINA DE 2.7": "LAM MDF 2.7", "LAM MDF 2,7": "LAM MDF 2.7",
    "GRAPA": "GRAPAS", "PEOPE": "PEOPLE", "POP": "PEOPLE", "PEO": "PEOPLE",
    "COLAPATOS": "COLA DE PATO", "COLAPATO": "COLA DE PATO",
    "CABUYA": "CABULLA", "EMBALADA": "EMBALAJE",
}


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
    return " ".join(str(texto).split()) if texto is not None else ""


def normalizar_unidad(raw) -> str:
    t = str(raw or "").strip().upper()
    if not t:
        return "und"
    for key in sorted(UNIDAD_ALIAS, key=len, reverse=True):
        if key in t:
            return UNIDAD_ALIAS[key]
    return t.lower()[:30] or "und"


def normalizar_material(raw) -> str:
    s = str(raw or "").upper().strip().rstrip("* ,.:")
    s = " ".join(s.split()).replace('"', "")
    if not s:
        return ""
    if s in ALIAS_MATERIAL:
        return ALIAS_MATERIAL[s]
    s_clean = s.replace('"', "")
    return ALIAS_MATERIAL.get(s_clean, s_clean)


def _precios(vals):
    """(v_unit, total): el TOTAL autoritativo es la última columna (F del Excel)."""
    v_unit = dec(vals[4]) if len(vals) > 4 else None
    total = dec(vals[5]) if len(vals) > 5 else None
    if total is not None and total <= 0:
        total = None
    if (v_unit is None or v_unit <= 0) and total is not None and len(vals) <= 5:
        # Fila pegada sin la columna de nota: el último número era el total.
        nums = [dec(v) for v in vals if dec(v) is not None and dec(v) > 0]
        if len(nums) >= 2:
            v_unit = nums[-2]
    return v_unit, total


def _cantidad(vals):
    if len(vals) <= 1:
        return None
    d = dec(vals[1])
    return d if (d is not None and d > 0) else None


def _porcentaje_en_texto(texto):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(texto))
    return dec(m.group(1)) if m else None


def _detectar_seccion(c1_up):
    m = SECCION_HEADER_PAT.search(c1_up)
    if m:
        return _normalizar_seccion(m.group(1)), (m.group(2) or "").strip().upper()
    m = SECCION_LONELY.search(c1_up)
    if m:
        return _normalizar_seccion(m.group(1)), ""
    return None


def _normalizar_seccion(txt):
    t = txt.upper()
    t = (t.replace("TAPICERIA", "TAPICERÍA").replace("TERMINACION", "TERMINACIÓN")
          .replace("EBANISTERIA", "EBANISTERÍA"))
    t = re.sub(r"\s+", " ", t).strip()
    for canon in SECCIONES_BASE:
        if canon.upper() in t:
            return canon
    return t


def _sufijo_de_resto(resto):
    if not resto:
        return None
    r = resto.upper()
    if "NOCHERO" in r:
        return "NOCHEROS"
    if "PATAS" in r or "PATA " in r:
        return "PATAS"
    if "CAMA" in r:
        return "CAMA"
    return None


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


def clasificar_fila(vals):
    """(tipo, datos). Orden crítico: basura → nombre → totales → gastos → sección → costo → insumo."""
    c1 = limpiar(vals[0]) if vals else ""
    if len(c1) < 2:
        return ("ignorar", {})
    c1_up = c1.upper()

    c1_sec = c1_up
    if "SECCION" in c1_up:
        c1_sec = " ".join(limpiar(v).upper() for v in vals[:4] if v)

    tiene_nums = any((dec(v) is not None and dec(v) > 0) for v in vals[1:])

    if any(tok in c1_up for tok in TEXTO_BASE_OCCUP_ROWS):
        return ("ignorar", {})
    for p in IGNORAR_FILA_STARTS:
        if c1_up.startswith(p):
            return ("ignorar", {})

    if c1_up.startswith(("TOTAL GASTOS", "TOTAL DE GASTOS")):
        return ("total", {"label": "TOTAL_GASTOS_SECCION", "valor": _ultimo_numero(vals)})
    if c1_up.startswith(("TOTAL PRODUCCION", "TOTAL PRODUCCIÓN", "TOTAL COSTO DE PRODUC")):
        return ("total", {"label": "TOTAL_PRODUCCION", "valor": _ultimo_numero(vals)})
    if c1_up.startswith("TOTAL A PAGAR"):
        return ("total", {"label": "TOTAL_PAGAR", "valor": _ultimo_numero(vals)})
    if re.match(r"^IVA\b", c1_up):
        return ("total", {"label": "IVA", "valor": _ultimo_numero(vals)})
    if "PRECIO DE VENTA" in c1_up:
        return ("total", {"label": "PRECIO_VENTA", "valor": _ultimo_numero(vals)})
    if "GANANCIA" in c1_up and (c1_up.startswith("TOTAL") or "MÁS GANANCIA" in c1_up or "MAS GANANCIA" in c1_up):
        return ("total", {"label": "GANANCIA", "valor": _ultimo_numero(vals)})
    if re.match(r"^SUB\s*TOTAL\b", c1_up) or c1_up.replace(" ", "") == "SUBTOTAL":
        return ("ignorar", {})
    if c1_up.startswith("TOTAL"):
        return ("total", {"label": "OTRO_TOTAL", "valor": _ultimo_numero(vals)})

    if "NOMBRE DEL PRODUCTO" in c1_sec:
        valor = None
        for v in vals:
            t = limpiar(v)
            if t and "NOMBRE DEL PRODUCTO" not in t.upper():
                valor = t
                break
        return ("nombre_producto", {"valor": valor})

    if "GASTOS" in c1_up and not tiene_nums:
        return ("gastos", {"porcentaje": _primero_numero(c1)})

    det = None
    if c1_up.startswith("SECCION") or not tiene_nums:
        det = _detectar_seccion(c1_sec)
    if det:
        return ("seccion", {"base": det[0], "resto": det[1]})

    pct = None
    for v in vals[:4]:
        p = _porcentaje_en_texto(v)
        if p:
            pct = p
            break
    if any(c1_up.startswith(k) for k in COSTO_PROD_STARTS) or pct is not None:
        v_unit, total = _precios(vals)
        if total is None:
            return ("ignorar", {})
        base = (total / (Decimal("1") + pct / Decimal("100"))).quantize(Decimal("0.01")) if pct else total
        return ("costo_prod", {"texto": c1_up, "porcentaje": pct, "base": base, "total": total,
                               "es_fabricacion": c1_up.startswith("FABRICAC")})

    qty = _cantidad(vals)
    v_unit, total = _precios(vals)
    unidad = limpiar(vals[2]) if len(vals) > 2 else ""
    return ("insumo", {"nombre": c1_up, "qty": qty, "unidad": unidad,
                       "v_unit": v_unit, "total": total})


def _ultimo_numero(vals):
    nums = [dec(v) for v in vals if dec(v) is not None and dec(v) > 0]
    return nums[-1] if nums else None


def _primero_numero(texto):
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(texto))
    return dec(m.group(1)) if m else None


def partir_lineas(texto: str):
    """Divide el texto pegado en filas de celdas (tab de Excel; tolera | y 2+ espacios)."""
    filas = []
    for linea in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not linea.strip():
            continue
        if "\t" in linea:
            celdas = [limpiar(c) for c in linea.split("\t")]
        elif "|" in linea:
            celdas = [limpiar(c) for c in linea.split("|")]
        else:
            celdas = [limpiar(c) for c in re.split(r"\s{2,}", linea)]
            if len(celdas) == 1:
                celdas = [linea.strip()]
        filas.append(celdas)
    return filas


# ---------------------------------------------------------------------------
# Parseo de la estructura completa
# ---------------------------------------------------------------------------
def parsear_texto_estructura(texto: str) -> dict:
    rd = {
        "nombre_sugerido": None,
        "has_nocheros": False,
        "totales": {},
        "secciones": [],
        "referencias_descartadas": [],
    }
    if not texto or not texto.strip():
        return rd

    secciones: dict = {}   # clave (base, sufijo) → dict

    def nueva_seccion(base, sufijo, comp):
        suf = sufijo
        if suf is None and base in ("EBANISTERÍA", "PINTURA") and rd["has_nocheros"]:
            suf = comp
        clave = (base, suf)
        if clave not in secciones:
            secciones[clave] = {
                "base": base, "sufijo": suf, "componente": comp,
                "insumos": [], "costos": [],
                "pct_gastos": None, "total_declarado_seccion": None,
            }
            rd["secciones"].append(secciones[clave])
        return clave

    componente = "CAMA"
    seccion_base = "EBANISTERÍA"
    clave_actual = nueva_seccion(seccion_base, None, componente)

    for vals in partir_lineas(texto):
        tipo, datos = clasificar_fila(vals)

        if tipo == "nombre_producto":
            valor = (datos.get("valor") or "").strip()
            if valor and not rd["nombre_sugerido"]:
                rd["nombre_sugerido"] = valor[:200]
            if "NOCHERO" in valor.upper():
                rd["has_nocheros"] = True
                componente = "NOCHEROS"
                clave_actual = nueva_seccion("EBANISTERÍA", None, componente)
            else:
                componente = "CAMA"
            continue

        if tipo == "total":
            label, val = datos["label"], datos["valor"]
            if label == "TOTAL_GASTOS_SECCION" and val is not None:
                sec = secciones[clave_actual]
                sec["total_declarado_seccion"] = val
            elif val is not None:
                previo = rd["totales"].get(label)
                if previo is None or label in ("TOTAL_PRODUCCION", "PRECIO_VENTA", "TOTAL_PAGAR"):
                    rd["totales"][label] = val
            continue

        if tipo == "seccion":
            base, resto = datos["base"], datos["resto"]
            suf = _sufijo_de_resto(resto)
            if suf == "NOCHEROS":
                rd["has_nocheros"] = True
                componente = "NOCHEROS"
            elif suf == "PATAS":
                componente = "CAMA"
            clave_actual = nueva_seccion(base, suf, componente if base != "NOCHEROS" else "NOCHEROS")
            continue

        if tipo == "gastos":
            secciones[clave_actual]["pct_gastos"] = datos["porcentaje"]
            continue

        if tipo == "costo_prod":
            sec = secciones[clave_actual]
            sec["costos"].append({
                "nombre": _nombre_costo(datos["texto"], sec["base"]),
                "porcentaje": datos["porcentaje"],
                "base": datos["base"],
            })
            continue

        if tipo == "insumo":
            qty, total, v_unit = datos["qty"], datos["total"], datos["v_unit"]
            # El monto SIEMPRE proviene de PRECIO TOTAL; sin él la hoja no calculó
            # el ítem (referencia) y multiplicar inventaría fantasmas.
            if total is None or total <= 0:
                rd["referencias_descartadas"].append({"nombre": datos["nombre"], "motivo": "sin_total"})
                continue
            if (qty is None or qty <= 0) and (v_unit is None or v_unit <= 0):
                rd["referencias_descartadas"].append({"nombre": datos["nombre"], "motivo": "subtotal_traspuesto"})
                continue
            qty2 = qty if (qty is not None and qty > 0) else Decimal("1")
            pu = v_unit if (v_unit is not None and v_unit > 0) else (total / qty2).quantize(Decimal("0.01"))
            secciones[clave_actual]["insumos"].append({
                "nombre": datos["nombre"],
                "cantidad": qty2,
                "unidad": normalizar_unidad(datos["unidad"]),
                "precio_unitario": pu.quantize(Decimal("0.01")),
                "total": total.quantize(Decimal("0.01")),
            })
            continue

    # Nombres finales: solo EBANISTERÍA/PINTURA distinguen (CAMA)/(NOCHEROS)
    for clave, sec in secciones.items():
        base, suf = clave
        if suf is None and base in ("EBANISTERÍA", "PINTURA") and rd["has_nocheros"]:
            suf = sec["componente"] or "CAMA"
        sec["nombre"] = f"{base} ({suf})" if suf else base

    rd["secciones"] = [s for s in rd["secciones"] if s["insumos"] or s["costos"]]
    return rd


# ---------------------------------------------------------------------------
# Cálculo (misma fórmula que cost_service Rama B)
# ---------------------------------------------------------------------------
def subtotal_insumos(sec) -> Decimal:
    return sum((i["total"] for i in sec["insumos"]), Decimal("0"))


def subtotal_costos_prod(sec) -> Decimal:
    total = Decimal("0")
    for c in sec["costos"]:
        aporte = c["base"]
        if c.get("porcentaje"):
            aporte += c["base"] * c["porcentaje"] / Decimal("100")
        total += aporte
    return total


def resumen_calculo(estructura: dict, ganancia_pct: float = 40.0, impuesto_pct: float = 7.0) -> dict:
    por_seccion = []
    costo_produccion = Decimal("0")
    for sec in estructura["secciones"]:
        ins = subtotal_insumos(sec).quantize(Decimal("0.01"))
        cp = subtotal_costos_prod(sec).quantize(Decimal("0.01"))
        sub = (ins + cp).quantize(Decimal("0.01"))
        pct_g = sec.get("pct_gastos")
        gasto = (sub * (pct_g or Decimal("0")) / Decimal("100")).quantize(Decimal("0.01"))
        total_sec = (sub + gasto).quantize(Decimal("0.01"))
        por_seccion.append({
            "nombre": sec["nombre"],
            "insumos_total": float(ins),
            "costos_produccion_total": float(cp),
            "subtotal": float(sub),
            "pct_gastos": float(pct_g) if pct_g is not None else None,
            "gasto": float(gasto),
            "total_seccion": float(total_sec),
            "num_insumos": len(sec["insumos"]),
            "num_costos_produccion": len(sec["costos"]),
        })
        costo_produccion += total_sec

    costo_produccion = costo_produccion.quantize(Decimal("0.01"))
    from app.core.redondeo import redondear_precio_cop
    impuestos = (costo_produccion * Decimal(str(impuesto_pct)) / Decimal("100")).quantize(Decimal("0.01"))
    base_con_impuestos = costo_produccion + impuestos
    precio_sin_iva = redondear_precio_cop(base_con_impuestos * (Decimal("1") + Decimal(str(ganancia_pct)) / Decimal("100")), "ceil")

    declarado = estructura["totales"].get("TOTAL_PRODUCCION")
    desviacion = None
    if declarado and declarado > 0:
        desviacion = round(float(abs(costo_produccion - declarado) / declarado * 100), 2)

    return {
        "por_seccion": por_seccion,
        "costo_produccion": float(costo_produccion),
        "impuesto_porcentaje": impuesto_pct,
        "impuestos": float(impuestos),
        "ganancia_porcentaje": ganancia_pct,
        "precio_sin_iva": float(precio_sin_iva),
        "total_declarado_excel": float(declarado) if declarado else None,
        "desviacion_porcentual": desviacion,
        "excede_gate_15": bool(desviacion is not None and desviacion > 15),
    }


# ---------------------------------------------------------------------------
# Material / tipo / persistencia
# ---------------------------------------------------------------------------
def matchear_material(db: Session, nombre_raw: str):
    """Exacto → sinónimo → contiene → fuzzy ≥0.82. None si nada (queda PENDIENTE)."""
    norm = normalizar_material(nombre_raw)
    if not norm:
        return None
    m = db.query(model.Material).filter(func.upper(func.trim(model.Material.nombre)) == norm).first()
    if m:
        return m
    sin = db.query(model.MaterialSinonimo).filter(
        func.upper(model.MaterialSinonimo.sinonimo) == norm
    ).first()
    if sin:
        return db.query(model.Material).filter(model.Material.id == sin.material_id).first()
    contiene = db.query(model.Material).filter(model.Material.nombre.ilike(f"%{norm}%")).first() \
        or db.query(model.Material).filter(model.Material.nombre.ilike(f"{norm[:12]}%")).first()
    if contiene:
        return contiene
    mejor, mejor_score = None, 0.0
    candidatos = db.query(model.Material).filter(
        func.left(model.Material.nombre, 6) == norm[:6]
    ).all() if len(norm) >= 6 else []
    for cand in candidatos:
        score = SequenceMatcher(None, norm, cand.nombre.upper().strip()).ratio()
        if score > mejor_score:
            mejor, mejor_score = cand, score
    return mejor if mejor_score >= 0.82 else None


def resolver_tipo(db: Session, tipo_producto_id: Optional[int], nuevo_tipo: Optional[str],
                  crear: bool = True) -> model.TipoProducto:
    if tipo_producto_id:
        tipo = db.query(model.TipoProducto).filter(model.TipoProducto.id == tipo_producto_id).first()
        if not tipo:
            raise ValueError(f"El tipo de mueble #{tipo_producto_id} no existe.")
        return tipo
    if nuevo_tipo and nuevo_tipo.strip():
        nombre = limpiar(nuevo_tipo)[:100]
        tipo = db.query(model.TipoProducto).filter(
            func.upper(func.trim(model.TipoProducto.nombre)) == nombre.upper()
        ).first()
        if not tipo:
            if not crear:
                raise ValueError(f"El tipo de mueble '{nombre}' no existe.")
            tipo = model.TipoProducto(nombre=nombre)
            db.add(tipo)
            db.flush()
        return tipo
    raise ValueError("Indica el tipo de mueble (obligatorio).")


def crear_producto_desde_estructura(
    db: Session,
    *,
    nombre: str,
    tipo: model.TipoProducto,
    estructura: dict,
    ancho: float,
    largo: float,
    resumen: dict,
    usuario=None,
) -> model.Producto:
    producto = model.Producto(
        nombre=limpiar(nombre)[:150],
        tipo_producto_id=tipo.id,
        ancho_base=Decimal(str(ancho)),
        largo_base=Decimal(str(largo)),
        activo=True,
        es_reventa=False,
        moneda_id=MONEDA_BASE_ID,
        hoja_excel="importacion-manual",
        precio_costo_base=Decimal(str(resumen["costo_produccion"])),
        precio_venta_base=(Decimal(str(estructura["totales"]["PRECIO_VENTA"]))
                           if estructura["totales"].get("PRECIO_VENTA") else None),
    )
    db.add(producto)
    db.flush()

    for orden, sec in enumerate(estructura["secciones"], start=1):
        seccion = model.SeccionProducto(producto_id=producto.id, nombre=sec["nombre"], orden=orden)
        db.add(seccion)
        db.flush()

        pct_g = sec.get("pct_gastos")
        politica = model.PoliticaSeccion(
            seccion_id=seccion.id,
            mano_obra_base=Decimal("0"),
            pct_liquidacion_mo=Decimal("5.00"),
            # 0% por defecto: la hoja pegada YA incluye sus gastos (como filas o
            # dentro de los totales); sumar otro % duplicaría el costo al
            # recalcular con el motor. Si la hoja trajo "gastos de X e N%",
            # ese % explícito sí se respeta.
            pct_gastos_seccion=Decimal(str(pct_g)) if pct_g is not None else Decimal("0.00"),
        )
        db.add(politica)

        for c in sec["costos"]:
            db.add(model.CostoProduccionSeccion(
                seccion_id=seccion.id,
                nombre=c["nombre"],
                porcentaje=c.get("porcentaje"),
                costo_base=c["base"],
            ))

        for i in sec["insumos"]:
            material = matchear_material(db, i["nombre"])
            db.add(model.ElementoSeccion(
                seccion_id=seccion.id,
                nombre_insumo_original=i["nombre"],
                material_id_normalizado=material.id if material else None,
                estado_resolucion="MAPEADO" if material else "PENDIENTE",
                cantidad=i["cantidad"],
                unidad_medida=i["unidad"],
                precio_unitario=i["precio_unitario"],
                costo_subtotal=i["total"],
            ))

    record_event(
        db, actor=usuario, action="CREATE", entity_type="producto",
        entity_id=producto.id,
        after={"nombre": producto.nombre, "origen": "importacion-excel",
               "costo_produccion": float(producto.precio_costo_base or 0)},
    )
    db.commit()
    db.refresh(producto)
    return producto
