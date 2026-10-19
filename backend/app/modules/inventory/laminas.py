"""
laminas.py
==========
Motor de cortes para materiales laminares (MDF, melamina, espuma, formica...).

Conceptos:
  - Un material es LAMINAR cuando tiene largo_cm y ancho_cm definidos
    (medidas de la lámina completa de compra, en cm).
  - Un CONTEO de cortes por lámina asume corte de guillotina y prueba las
    dos orientaciones del corte (80×130 cabe igual que 130×80).
  - Al abrir LÁMINAS NUEVAS para cortes, se descuentan láminas enteras del
    inventario; el costo del consumo es proporcional al área del corte.

NOTA: el inventario de retazos ("sobrantes de lámina") fue RETIRADO del
sistema por decisión del dueño: ya no se crean, ni se consumen, ni se
reponen. Las tablas viejas quedan congeladas en la BD (sin uso).

Todas las medidas son centímetros. El área es la fuente de verdad para el
costo.
"""
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP


def dec(valor) -> Decimal:
    return Decimal(str(valor))


def es_laminar(material) -> bool:
    """True si el material tiene las dos dimensiones de lámina definidas."""
    return getattr(material, "largo_cm", None) is not None and getattr(material, "ancho_cm", None) is not None


def area_cm2(largo, ancho) -> Decimal:
    return dec(largo) * dec(ancho)


def _encajan(L: Decimal, A: Decimal, lc: Decimal, ac: Decimal) -> int:
    """Cuántos cortes lc×ac caben en L×A (guillotina, una sola orientación)."""
    if lc <= 0 or ac <= 0 or lc > L or ac > A:
        return 0
    return int((L / lc).to_integral_value(rounding=ROUND_DOWN)) * int(
        (A / ac).to_integral_value(rounding=ROUND_DOWN)
    )


def cortes_que_caban(largo_lamina, ancho_lamina, largo_corte, ancho_corte) -> int:
    """Cortes lc×ac que caben en una lámina L×A probando ambas orientaciones."""
    L, A, lc, ac = dec(largo_lamina), dec(ancho_lamina), dec(largo_corte), dec(ancho_corte)
    return max(_encajan(L, A, lc, ac), _encajan(L, A, ac, lc))


def laminas_necesarias(cantidad_cortes, cortes_por_lamina: int) -> int:
    """Láminas enteras a abrir para sacar `cantidad_cortes` cortes."""
    if cortes_por_lamina <= 0:
        raise ValueError("El corte no cabe en la lámina del material.")
    n = dec(cantidad_cortes)
    return int((n / Decimal(cortes_por_lamina)).to_integral_value(rounding=ROUND_CEILING))


def costo_por_corte(costo_base_lamina, area_corte_cm2, area_lamina_cm2) -> Decimal:
    """Costo proporcional: área del corte × costo por cm² de lámina."""
    if area_lamina_cm2 <= 0:
        raise ValueError("El material laminar no tiene área de lámina válida.")
    return (dec(costo_base_lamina) * dec(area_corte_cm2) / dec(area_lamina_cm2)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def validar_corte(material, largo_corte, ancho_corte):
    """Valida que el material sea laminar y las medidas del corte positivas."""
    if not es_laminar(material):
        raise ValueError(
            f"El material '{material.nombre}' no tiene dimensiones de lámina "
            "(largo_cm/ancho_cm). Configúralas para usar cortes."
        )
    lc, ac = dec(largo_corte), dec(ancho_corte)
    if lc <= 0 or ac <= 0:
        raise ValueError("Las medidas del corte deben ser positivas.")
    return lc, ac
