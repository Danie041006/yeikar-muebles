# -*- coding: utf-8 -*-
"""
test_tasas_universales.py
=========================
Pruebas de la estandarización universal de tasas de cambio bajo la regla
de monedas fuertes (EUR > USD > VES > COP) y el egreso multimoneda en inventario.

El saldo de una cuenta de caja se DERIVA de sus movimientos (ENTRADA − SALIDA):
no existe columna `saldo` en metodo_caja.
"""
from decimal import Decimal
import pytest
from app.modules.inventory.service import _gasto_compra_contado
from app.modules.reports.model import MetodoCaja, MovimientoCaja


def _saldo_caja(db, cuenta) -> Decimal:
    movs = db.query(MovimientoCaja).filter(MovimientoCaja.metodo_caja_id == cuenta.id).all()
    saldo = Decimal("0")
    for mv in movs:
        if mv.tipo == "SALIDA":
            saldo -= Decimal(str(mv.monto))
        else:
            saldo += Decimal(str(mv.monto))
    return saldo


def _cuenta_de_moneda(db, moneda_id: int, nombre: str, codigo: str) -> MetodoCaja:
    cuenta = db.query(MetodoCaja).filter(MetodoCaja.moneda_id == moneda_id).first()
    if not cuenta:
        cuenta = MetodoCaja(nombre=nombre, codigo=codigo, moneda_id=moneda_id, activo=True, orden=99)
        db.add(cuenta)
        db.flush()
    return cuenta


def test_egreso_compra_usd_pagado_en_ves(db):
    """
    Caso reportado: producto en USD (id=2), pagado desde cuenta en VES (id=3).
    Tasa humana: 1 USD = 75.00 VES.
    Costo del producto: 10.00 USD.
    Monto debitado de la cuenta en VES: 10 * 75 = 750.00 VES.
    """
    cuenta = _cuenta_de_moneda(db, 3, "Caja Bolívares Test", "CAJA-VES-TEST")
    saldo_inicial = _saldo_caja(db, cuenta)

    _gasto_compra_contado(
        db,
        total_ref=Decimal("10.00"),
        ref_moneda_id=2,  # USD
        descripcion="Producto Test USD pagado en VES",
        tipo_gasto_nombre="Compra inventario reventa",
        metodo_caja_id=cuenta.id,
        moneda_pago_id=3,  # VES
        tasa_pago=Decimal("75.00"),  # 1 USD = 75 VES
    )
    db.flush()

    # Verificar que se debitaron exactamente 750.00 VES
    saldo_esperado = saldo_inicial - Decimal("750.00")
    assert _saldo_caja(db, cuenta) == pytest.approx(float(saldo_esperado), abs=0.01)


def test_egreso_compra_cop_pagado_en_usd(db):
    """
    Producto en COP (id=1), pagado desde cuenta en USD (id=2).
    Tasa humana: 1 USD = 4,200.00 COP.
    Costo: 420,000.00 COP.
    Monto debitado de la cuenta en USD: 420,000 / 4,200 = 100.00 USD.
    """
    cuenta = _cuenta_de_moneda(db, 2, "Zelle USD Test", "ZELLE-USD-TEST")
    saldo_inicial = _saldo_caja(db, cuenta)

    _gasto_compra_contado(
        db,
        total_ref=Decimal("420000.00"),
        ref_moneda_id=1,  # COP
        descripcion="Material Test COP pagado en USD",
        tipo_gasto_nombre="Compra insumo",
        metodo_caja_id=cuenta.id,
        moneda_pago_id=2,  # USD
        tasa_pago=Decimal("4200.00"),  # 1 USD = 4200 COP
    )
    db.flush()

    saldo_esperado = saldo_inicial - Decimal("100.00")
    assert _saldo_caja(db, cuenta) == pytest.approx(float(saldo_esperado), abs=0.01)


def test_egreso_compra_ves_pagado_en_cop(db):
    """
    Producto en VES (id=3), pagado desde cuenta en COP (id=1).
    Tasa humana: 1 VES = 55.00 COP.
    Costo: 100.00 VES.
    Monto debitado de la cuenta en COP: 100 * 55 = 5,500.00 COP.
    """
    cuenta = _cuenta_de_moneda(db, 1, "Bancolombia COP Test", "BANCO-COP-TEST")
    saldo_inicial = _saldo_caja(db, cuenta)

    _gasto_compra_contado(
        db,
        total_ref=Decimal("100.00"),
        ref_moneda_id=3,  # VES
        descripcion="Insumo VES pagado en COP",
        tipo_gasto_nombre="Compra insumo",
        metodo_caja_id=cuenta.id,
        moneda_pago_id=1,  # COP
        tasa_pago=Decimal("55.00"),  # 1 VES = 55 COP
    )
    db.flush()

    saldo_esperado = saldo_inicial - Decimal("5500.00")
    assert _saldo_caja(db, cuenta) == pytest.approx(float(saldo_esperado), abs=0.01)


def test_egreso_compra_falta_tasa_error_claro(db):
    """
    Si difiere la moneda y no se proporciona tasa, debe arrojar un error
    humano claro especificando la tasa que falta (ej: 1 USD = ? VES).
    """
    cuenta = db.query(MetodoCaja).first()
    with pytest.raises(ValueError) as excinfo:
        _gasto_compra_contado(
            db,
            total_ref=Decimal("50.00"),
            ref_moneda_id=2,  # USD
            descripcion="Item sin tasa",
            tipo_gasto_nombre="Compra insumo",
            metodo_caja_id=cuenta.id,
            moneda_pago_id=3,  # VES
            tasa_pago=None,
        )
    assert "1 USD = ? VES" in str(excinfo.value)
