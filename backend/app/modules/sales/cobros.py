"""Lectura única de lo aplicado a ventas, separada del dinero recibido."""
from decimal import Decimal

from sqlalchemy import func

from app.modules.sales.model import Pago


def monto_aplicado(pago: Pago) -> Decimal:
    valor = pago.monto_aplicado
    return Decimal(str(pago.monto_en_moneda_base if valor is None else valor))


def expresion_aplicado():
    return func.coalesce(Pago.monto_aplicado, Pago.monto_en_moneda_base)


def resumen_cobro(venta) -> tuple[float, float, float]:
    """Pagado, descontado y pendiente, todos en la moneda de la venta."""
    pagado = sum((monto_aplicado(p) for p in venta.pagos), Decimal("0"))
    descontado = sum((Decimal(str(d.monto_en_moneda_base)) for d in venta.descuentos), Decimal("0"))
    pendiente = max(Decimal("0"), Decimal(str(venta.total)) - pagado - descontado)
    return float(pagado), float(descontado), float(pendiente)
