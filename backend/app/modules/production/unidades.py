"""
Conversión de capturas de consumo de material a la unidad base del inventario.

La unidad base SIEMPRE es la de compra del material (`material.unidad_medida`).
El operario digita la cantidad como le quede cómodo y este módulo la lleva a
la unidad base ANTES de descontar inventario o costear:

  - Materiales LINEALES (m): en metros o centímetros (1520 cm = 15.20 m).
  - Materiales VOLUMÉTRICOS (m³): en m³ o "por pieza" con la FÓRMULA DE LA
    CASA de la mueblería (21 años de práctica empírica):

        (largo × ancho × espesor) × piezas ÷ 10000 = m³ a descontar

    Los números se toman TAL CUAL los escribe el taller; la fórmula es ley.

Este es el ÚNICO punto de conversión del sistema: si mañana cambia una regla
o se agrega una unidad, se toca aquí y no en cada endpoint.

Uso típico en service:
    cantidad_base = resolver_cantidad_consumo(
        material, esquema.cantidad, esquema.unidad_captura,
        esquema.pieza_largo, esquema.pieza_ancho, esquema.pieza_espesor,
    )
"""
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------------------
# Constantes de negocio (ajustables en un solo lugar)
# ---------------------------------------------------------------------------
CM_POR_METRO = Decimal("100")

# Fórmula de la casa: el producto de las 3 medidas de la pieza (números tal
# cual los anotan en el taller) dividido entre 10000 da los m³ a descontar.
# (El taller divide entre 10000, no 1000 — regla confirmada por el dueño.)
DIVISOR_PIEZA = Decimal("10000")

# Las columnas de cantidad son Numeric(12,4) (4 decimales: la fórmula de la
# casa ÷10000 da volúmenes pequeños como 0.016 m³ y con 2 decimales se
# perdía stock al redondear). Se redondea UNA sola vez aquí para que consumo,
# kardex y costo queden EXACTAMENTE iguales (la reversa al eliminar un
# consumo depende de esa igualdad).
DECIMALES_CANTIDAD = Decimal("0.0001")

# Dimensionalidades reconocidas (extensible: agregar más en `dimensionalidad`)
LONGITUD = "LONGITUD"
AREA = "AREA"
VOLUMEN = "VOLUMEN"
OTRA = "OTRA"


def _norm(abreviatura: str | None) -> str:
    """Normaliza una abreviatura: 'M³', ' m3 ', 'Mt3' → 'm3'."""
    return (
        (abreviatura or "")
        .strip()
        .lower()
        .replace("³", "3")
        .replace("²", "2")
        .replace("^", "")
        .replace(" ", "")
    )


def dimensionalidad(abreviatura: str | None) -> str:
    """Clasifica una unidad: LONGITUD (m, cm, mts), VOLUMEN (m3), AREA (m2)
    u OTRA (und, kg, lt...)."""
    a = _norm(abreviatura)
    if a in ("m3", "mt3", "mc"):
        return VOLUMEN
    if a in ("m2", "mt2"):
        return AREA
    if a in ("m", "mt", "mts", "cm"):
        return LONGITUD
    return OTRA


def _base_en_metros(abreviatura: str | None) -> bool:
    """True si la unidad base de longitud del material es el metro (no cm)."""
    return _norm(abreviatura) != "cm"


def resolver_cantidad_consumo(
    material,
    cantidad,
    unidad_captura: str | None = None,
    pieza_largo=None,
    pieza_ancho=None,
    pieza_espesor=None,
) -> Decimal:
    """Convierte la captura del operario a la unidad base del material.

    Args:
        material: modelo Material (con .unidad_medida.abreviatura).
        cantidad: número digitado. En modo pieza ES EL NÚMERO DE PIEZAS.
        unidad_captura: 'M' | 'CM' — unidad en que se digitó `cantidad`
            (solo materiales lineales; None = tal cual, comportamiento legacy).
        pieza_largo / pieza_ancho / pieza_espesor: medidas de UNA pieza tal
            cual las escribe el taller. Si ALGUNO viene, se activa el modo
            pieza (fórmula de la casa) y se exige material volumétrico (m³).

    Returns:
        Decimal redondeado a 2 decimales: cantidad canónica en la unidad base
        del material, lista para descontar del inventario y costear.

    Raises:
        ValueError: si la captura no es coherente con la unidad del material
            (p. ej. pieza sobre un material lineal, o cm sobre m²).
    """
    abrev = material.unidad_medida.abreviatura if material.unidad_medida else None
    dim = dimensionalidad(abrev)
    cant = Decimal(str(cantidad))

    es_pieza = any(v is not None for v in (pieza_largo, pieza_ancho, pieza_espesor))
    if es_pieza:
        if dim != VOLUMEN:
            raise ValueError(
                "El consumo por pieza (largo×ancho×espesor) solo aplica a materiales en m³."
            )
        faltan = [
            nombre
            for nombre, valor in (
                ("largo", pieza_largo),
                ("ancho", pieza_ancho),
                ("espesor", pieza_espesor),
            )
            if not valor
        ]
        if faltan:
            raise ValueError(f"Faltan medidas de la pieza: {', '.join(faltan)}.")
        # FÓRMULA DE LA CASA (21 años de práctica): producto de las 3 medidas
        # tal cual, por número de piezas, dividido entre 10000 = m³.
        volumen = (
            Decimal(str(pieza_largo))
            * Decimal(str(pieza_ancho))
            * Decimal(str(pieza_espesor))
            * cant
        ) / DIVISOR_PIEZA
        return volumen.quantize(DECIMALES_CANTIDAD, rounding=ROUND_HALF_UP)

    if unidad_captura:
        if dim != LONGITUD:
            raise ValueError(
                "El toggle cm/mts solo aplica a materiales medidos en longitud (m)."
            )
        captura = unidad_captura.upper()
        if captura == "CM":
            cant = cant / CM_POR_METRO if _base_en_metros(abrev) else cant
        elif captura == "M":
            cant = cant * CM_POR_METRO if not _base_en_metros(abrev) else cant
        else:
            raise ValueError(f"Unidad de captura no soportada: {unidad_captura}.")

    return cant.quantize(DECIMALES_CANTIDAD, rounding=ROUND_HALF_UP)


def nota_captura(
    cantidad,
    unidad_captura: str | None = None,
    pieza_largo=None,
    pieza_ancho=None,
    pieza_espesor=None,
) -> str | None:
    """Texto corto de trazabilidad sobre CÓMO se digitó la cantidad.

    Ej.: 'pieza 20×4×2 × 2' · 'digitado en cm'. None = captura directa."""
    if pieza_largo or pieza_ancho or pieza_espesor:
        return (
            f"pieza {_fmt(pieza_largo)}×{_fmt(pieza_ancho)}×{_fmt(pieza_espesor)}"
            f" × {_fmt(cantidad)}"
        )
    if unidad_captura:
        return f"digitado en {unidad_captura.upper()}"
    return None


def _fmt(valor) -> str:
    """Formatea un número sin ceros de más: 20.0 → '20', 2.5 → '2.5'."""
    return f"{Decimal(str(valor)):g}"
