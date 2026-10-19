# -*- coding: utf-8 -*-
"""
test_rentabilidad_moneda.py — El margen del pedido se muestra en la moneda
ORIGINAL de la cotización, no solo en COP.

Caso real (pedido #205): cotización en USD a tasa 2 COP/USD.
  - Precio: 405 USD → total cobrado 405 USD (810 COP)
  - Costo estimado: 405 COP → 202,50 USD
  - Costo real: 0 (aún sin producción) → margen real 405 USD (810 COP)

Antes la UI mostraba el precio del renglón como "$405 COP" y el margen solo en
COP, así que parecía que se cobraba 810 y costaba 405 (doble ingreso).

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_rentabilidad_moneda.py -v
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conftest import ADMIN_HEADERS, crear_cliente
from helpers_e2e import crear_cotizacion_multidetalle, convertir_cotizacion


def test_rentabilidad_en_moneda_original_cotizacion(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    detalle = {
        "tipo_item": "REPARACION",
        "cantidad": 1,
        "precio": 405.0,
        "descripcion_especifica": "SOMIER DE 2X2",
        "costo_total": 405.0,
    }
    cot = crear_cotizacion_multidetalle(
        client, cleaner, cliente["id"], [detalle],
        moneda_id=2, tasa_cambio=2.0,
    )
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [{
        "tipo_item": "REPARACION",
        "cantidad": 1,
        "precio": 405.0,
        "descripcion_especifica": "SOMIER DE 2X2",
    }])
    assert r.status_code in (200, 201), f"convertir → {r.status_code}: {r.text}"
    assert pedido is not None

    r = client.get(f"/api/v1/pedido/{pedido['id']}/rentabilidad", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    rent = r.json()

    # La moneda original manda en la vista principal.
    assert rent["moneda_codigo"] == "USD"
    assert rent["tasa_cambio"] == 2.0
    assert rent["total_cobrado"] == 405.0, "el precio del renglón es 405 USD, no 810"
    assert rent["total_cobrado_base"] == 810.0

    # Costo estimado y margen convertidos a USD con la tasa congelada.
    assert rent["costo_estimado_produccion"] == 405.0, "el costo se guarda en COP"
    assert rent["costo_estimado_moneda"] == 202.5
    assert rent["margen_estimado"] == 405.0, "margen en COP: 810 - 405"
    assert rent["margen_estimado_moneda"] == 202.5, "margen en USD: 405 - 202,5"

    # Sin producción todavía: costo real 0 y margen real = total cobrado.
    assert rent["costo_real_produccion"] == 0.0
    assert rent["costo_real_moneda"] == 0.0
    assert rent["margen_real"] == 810.0
    assert rent["margen_real_moneda"] == 405.0
    assert rent["diferencia_costo_moneda"] == -202.5

    # Los campos nuevos son coherentes entre sí.
    assert rent["margen_real_moneda"] == round(
        rent["total_cobrado"] - rent["costo_real_moneda"] - rent["flete_real_moneda"], 2
    )
