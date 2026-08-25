"""Registro de movimientos de caja (contabilidad).

Unifica la creación de movimientos de caja (entradas/salidas) para que cada
peso que entra o sale del negocio quede en su cuenta. Los módulos de ventas,
compras, gastos y devoluciones lo usan.
"""
from datetime import date

from sqlalchemy.orm import Session


def obtener_cuenta_por_codigo(db: Session, codigo: str):
    from app.modules.reports.model import MetodoCaja
    return db.query(MetodoCaja).filter(MetodoCaja.codigo == codigo).first()


def obtener_cuenta_por_id(db: Session, metodo_caja_id: int):
    from app.modules.reports.model import MetodoCaja
    return db.query(MetodoCaja).filter(MetodoCaja.id == metodo_caja_id).first()


def crear_cuenta_si_no_existe(db: Session, codigo: str) -> "MetodoCaja":
    """Crea la cuenta en el catálogo si no existe (para no perder movimientos)."""
    from sqlalchemy import func
    from app.modules.reports.model import MetodoCaja
    cuenta = obtener_cuenta_por_codigo(db, codigo)
    if cuenta:
        return cuenta
    ultimo_orden = db.query(func.coalesce(func.max(MetodoCaja.orden), 0)).scalar()
    cuenta = MetodoCaja(
        nombre=codigo.replace("_", " ").title(),
        codigo=codigo,
        activo=True,
        orden=int(ultimo_orden) + 1,
    )
    db.add(cuenta)
    db.flush()
    return cuenta


def registrar_movimiento_caja(
    db: Session,
    *,
    metodo_caja_id: int | None = None,
    codigo: str | None = None,
    tipo: str,
    monto: float,
    moneda_id: int = 1,
    tasa_cambio: float = 1.0,
    fecha: date | None = None,
    referencia: str | None = None,
    observaciones: str | None = None,
    usuario_id: int | None = None,
    pago_id: int | None = None,
):
    """Crea un movimiento de caja. Exige monto > 0 (un monto negativo no tiene
    sentido: el tipo ENTRADA/SALIDA ya expresa la dirección del flujo)."""
    if monto <= 0:
        raise ValueError("El monto del movimiento de caja debe ser mayor que cero.")

    from app.modules.reports.model import MovimientoCaja

    cuenta = None
    if metodo_caja_id is not None:
        cuenta = obtener_cuenta_por_id(db, metodo_caja_id)
    elif codigo:
        cuenta = crear_cuenta_si_no_existe(db, codigo)
    if cuenta is None:
        raise ValueError("Debes indicar el método de caja del movimiento.")

    monto_base = round(float(monto) * float(tasa_cambio or 1.0), 2)
    db.add(MovimientoCaja(
        metodo_caja_id=cuenta.id,
        usuario_id=usuario_id,
        pago_id=pago_id,
        fecha=fecha or date.today(),
        tipo=tipo,
        monto=round(float(monto), 2),
        moneda_id=moneda_id,
        tasa_cambio=round(float(tasa_cambio or 1.0), 6),
        monto_en_moneda_base=monto_base,
        referencia=referencia,
        observaciones=observaciones,
    ))
    db.flush()
