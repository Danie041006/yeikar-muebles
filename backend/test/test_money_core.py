# -*- coding: utf-8 -*-
"""
test_money_core.py
==================
Pruebas unitarias de la lógica financiera PURA de YEIKAR:

  * `_derivar_tasa_pago`  (app.modules.orders.service) — tasa '1 {pago} = X {venta}'
    derivada de la TRM congelada en la cotización, o exigencia de TRM manual.
  * `_evaluar_condicion`   (app.modules.productos.cost_service) — operadores de
    condición de activación de materiales en la receta paramétrica.
  * `_calcular_por_rango`  (app.modules.productos.cost_service) — saltos discretos
    de cantidad según rangos de dimensiones (POR_RANGO).

Las monedas COP(id=1), USD(id=2) y VES(id=3) ya existen en la BD; los tests de
tasa NO crean filas y por tanto no registran nada en el cleaner.

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_money_core.py -v
"""
from decimal import Decimal

import pytest

from app.modules.orders.service import _derivar_tasa_pago
from app.modules.productos.cost_service import _evaluar_condicion, _calcular_por_rango


# --- test_derivar_tasa_pago_misma_moneda ---
def test_derivar_tasa_pago_misma_moneda(db):
    """Pago en la misma moneda de la venta → tasa 1.0, derivada=True."""
    tasa, derivada = _derivar_tasa_pago(db, moneda_venta_id=2, moneda_pago_id=2, tasa_cotizacion=3900)
    assert tasa == 1.0, f"esperado 1.0, se obtuvo {tasa}"
    assert derivada is True, f"esperado True, se obtuvo {derivada}"


# --- test_derivar_tasa_pago_cop_a_usd ---
def test_derivar_tasa_pago_cop_a_usd(db):
    """Venta en COP, pago en USD → NO deducible: una cotización COP fija tasa 1.0
    (1 COP = 1 COP), no una TRM real; deducirla convertiría 200 USD en 200 COP.
    Debe exigir la TRM del abono (fallback con tasa_cambio_adelanto)."""
    tasa, derivada = _derivar_tasa_pago(db, moneda_venta_id=1, moneda_pago_id=2, tasa_cotizacion=3900)
    assert tasa is None, f"esperado None (no deducible), se obtuvo {tasa}"
    assert derivada is False, f"esperado False, se obtuvo {derivada}"


# --- test_derivar_tasa_pago_usd_a_cop ---
def test_derivar_tasa_pago_usd_a_cop(db):
    """Venta en USD, pago en COP → 1 COP = 1/tasa_cotizacion USD."""
    tasa, derivada = _derivar_tasa_pago(db, moneda_venta_id=2, moneda_pago_id=1, tasa_cotizacion=3900)
    assert derivada is True, f"esperado True, se obtuvo {derivada}"
    assert tasa == pytest.approx(1 / 3900), (
        f"esperado 1/3900 ≈ {1 / 3900}, se obtuvo {tasa}"
    )
    assert tasa == pytest.approx(0.000256410, abs=1e-9), (
        f"esperado ≈ 0.000256410, se obtuvo {tasa}"
    )


# --- test_derivar_tasa_pago_ves_no_deducible ---
def test_derivar_tasa_pago_ves_no_deducible(db):
    """Pago en VES con venta en USD → par no deducible: exige TRM manual."""
    tasa, derivada = _derivar_tasa_pago(db, moneda_venta_id=2, moneda_pago_id=3, tasa_cotizacion=3900)
    assert tasa is None, f"esperado None, se obtuvo {tasa}"
    assert derivada is False, f"esperado False, se obtuvo {derivada}"


# --- test_derivar_tasa_pago_sin_tasa ---
def test_derivar_tasa_pago_sin_tasa(db):
    """Sin tasa_cotizacion el par COP/USD no es deducible: exige TRM manual."""
    tasa, derivada = _derivar_tasa_pago(db, moneda_venta_id=2, moneda_pago_id=1, tasa_cotizacion=None)
    assert tasa is None, f"esperado None, se obtuvo {tasa}"
    assert derivada is False, f"esperado False, se obtuvo {derivada}"


# --- test_evaluar_condicion_operadores ---
def test_evaluar_condicion_operadores():
    """Cada operador de `nuevo_largo` y condiciones booleanas por atributos."""
    # >
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": ">", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("3.0"))
    assert r is True, f"'>' con 3.0 > 2.0 debe ser True, se obtuvo {r}"
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": ">", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("1.0"))
    assert r is False, f"'>' con 1.0 > 2.0 debe ser False, se obtuvo {r}"

    # >=
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": ">=", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("2.0"))
    assert r is True, f"'>=' con 2.0 >= 2.0 debe ser True, se obtuvo {r}"
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": ">=", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("1.5"))
    assert r is False, f"'>=' con 1.5 >= 2.0 debe ser False, se obtuvo {r}"

    # <
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": "<", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("1.0"))
    assert r is True, f"'<' con 1.0 < 2.0 debe ser True, se obtuvo {r}"
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": "<", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("2.0"))
    assert r is False, f"'<' con 2.0 < 2.0 debe ser False, se obtuvo {r}"

    # <=
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": "<=", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("2.0"))
    assert r is True, f"'<=' con 2.0 <= 2.0 debe ser True, se obtuvo {r}"

    # ==
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": "==", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("2.0"))
    assert r is True, f"'==' con 2.0 == 2.0 debe ser True, se obtuvo {r}"
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": "==", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("2.1"))
    assert r is False, f"'==' con 2.1 == 2.0 debe ser False, se obtuvo {r}"

    # !=
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": "!=", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("2.1"))
    assert r is True, f"'!=' con 2.1 != 2.0 debe ser True, se obtuvo {r}"

    # Booleano por atributos
    r = _evaluar_condicion({"campo": "tiene_tapiceria", "op": "==", "valor": True},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("2.0"),
                           atributos={"tiene_tapiceria": True})
    assert r is True, f"tiene_tapiceria == True debe ser True, se obtuvo {r}"
    r = _evaluar_condicion({"campo": "tiene_tapiceria", "op": "==", "valor": True},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("2.0"),
                           atributos={"tiene_tapiceria": False})
    assert r is False, f"tiene_tapiceria == True con False debe ser False, se obtuvo {r}"


# --- test_evaluar_condicion_operador_desconocido ---
def test_evaluar_condicion_operador_desconocido():
    """Operador desconocido → ops.get(operador, True) devuelve True (default)."""
    r = _evaluar_condicion({"campo": "nuevo_largo", "op": "gt", "valor": 2.0},
                           nuevo_ancho=Decimal("1.0"), nuevo_largo=Decimal("1.0"))
    assert r is True, f"operador desconocido 'gt' debe caer al default True, se obtuvo {r}"


# --- test_calcular_por_rango ---
def test_calcular_por_rango():
    """POR_RANGO: devuelve la cantidad del primer rango que cubre nuevo_largo."""
    rangos = [{"max": 1.8, "cantidad": 1}, {"max": 2.2, "cantidad": 2}]

    r = _calcular_por_rango(rangos, nuevo_largo=Decimal("2.0"))
    assert r == Decimal("2"), f"nuevo_largo=2.0 debe caer en el rango {1.8, 2.2} → 2, se obtuvo {r}"

    r = _calcular_por_rango(rangos, nuevo_largo=Decimal("1.5"))
    assert r == Decimal("1"), f"nuevo_largo=1.5 debe caer en el rango ≤ 1.8 → 1, se obtuvo {r}"

    r = _calcular_por_rango(rangos, nuevo_largo=Decimal("3.0"))
    assert r == Decimal("2"), f"nuevo_largo=3.0 supera todos los máximos → último rango (2), se obtuvo {r}"

    r = _calcular_por_rango([], nuevo_largo=Decimal("2.0"))
    assert r is None, f"lista vacía debe devolver None, se obtuvo {r}"