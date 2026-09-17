"""Hora operativa del sistema: Venezuela (America/Caracas, UTC-4 fijo).

Convención del proyecto: los timestamps de negocio se guardan como hora local
de Venezuela en columnas naive (sin zona), y el frontend los muestra tal cual.
Por eso NUNCA se usa UTC para horas visibles (ver test C8 en
test_production_risks.py: una etapa completada de noche caía fuera del
período de nómina).

UTC se reserva solo para matemática de autenticación (expiración de JWT,
ventanas de lockout) en `users/service.py`, que no se muestra al usuario.

`zoneinfo` usa el paquete pip `tzdata` (ver requirements.txt) para funcionar
igual en Vercel, Docker y desarrollo.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

ZONA_VE = ZoneInfo("America/Caracas")


def ahora_ve() -> datetime:
    """Ahora en Venezuela, naive (pared VE). Reemplaza `datetime.now()` y
    `datetime.utcnow()` en todo timestamp de negocio que se guarde/muestre."""
    return datetime.now(ZONA_VE).replace(tzinfo=None)


def hoy_ve() -> date:
    """Fecha de negocio en Venezuela. Reemplaza `date.today()` y
    `datetime.utcnow().date()` en fechas de venta, pedido, producción, etc."""
    return ahora_ve().date()
