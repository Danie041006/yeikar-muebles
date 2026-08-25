"""Política de redondeo de precios YEIKAR.

Regla de negocio:
- Los precios de venta de productos se expresan en múltiplos de 1.000 COP
  (terminan en `000`) para que ningún descuento porcentual o cantidad fraccionada
  genere decimales o cifras inviables (la moneda mínima física en Colombia es de
  50 COP, pero YEIKAR trabaja con el millar como paso estándar).
- Los precios NUEVOS o recalculados se redondean hacia ARRIBA (ceil) para nunca
  vender por debajo del precio calculado (protege el margen de ganancia).
- Las migraciones de datos existentes usan el millar más cercano (half_up).
- En pagos en moneda extranjera, el equivalente en COP se redondea al millar
  más cercano (half_up) para que el libro COP quede limpio.
"""
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

PASO_PRECIO_COP = Decimal("1000")


def redondear_a_multiplo(valor, paso=PASO_PRECIO_COP, modo="half_up") -> Decimal:
    """Redondea `valor` al múltiplo más cercano de `paso`.

    modos: "half_up" (más cercano, .5 hacia arriba) | "ceil" | "floor".
    """
    v = Decimal(str(valor))
    p = Decimal(str(paso))
    if p <= 0:
        raise ValueError("El paso de redondeo debe ser mayor a cero.")
    if modo == "ceil":
        redondeo = ROUND_CEILING
    elif modo == "floor":
        redondeo = ROUND_FLOOR
    else:
        redondeo = ROUND_HALF_UP
    return (v / p).to_integral_value(rounding=redondeo) * p


def redondear_precio_cop(valor, modo="ceil") -> Decimal:
    """Redondea un precio de venta COP al millar (default: hacia arriba)."""
    return redondear_a_multiplo(valor, PASO_PRECIO_COP, modo)


def es_multiplo_de_millar(valor) -> bool:
    """True si `valor` es un múltiplo exacto de 1.000 COP."""
    v = Decimal(str(valor))
    return v.is_zero() or (v % PASO_PRECIO_COP) == 0