# -*- coding: utf-8 -*-
"""
test_abono_inicial_mixto.py — El abono inicial de un pedido pagado de varias maneras.

Al convertir una cotización el abono inicial puede venir pago José: la mitad
en efectivo y el resto por Zelle (dólares), cada uno con su tasa y su fecha
(opcional: sin fecha → HOY VE). Se crean N pagos de factura, uno por cuenta.

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_abono_inicial_mixto.py -v
"""
from conftest import ADMIN_HEADERS, crear_cliente, crear_cotizacion, crear_producto, registrar_venta_de_pedido


def _convertir_y_resolver(client, cleaner, precio=200000.0, adelantos=None):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(
        client, cleaner, cliente["id"], prod["id"], precio=precio, moneda_id=1
    )
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": precio}],
        "adelantos": adelantos or [],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    venta = registrar_venta_de_pedido(client, cleaner, pedido["id"])
    return cliente, prod, pedido, venta


def _traer_venta(client, pedido_id):
    r = client.get("/api/v1/venta/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return next(v for v in r.json() if v.get("pedido_id") == pedido_id)


def _detalle_venta(client, pedido_id):
    venta = _traer_venta(client, pedido_id)
    return venta, client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()


def test_abono_inicial_en_dos_cuentas(client, cleaner):

    cliente, prod, pedido, venta = _convertir_y_resolver(client, cleaner, 200000.0, adelantos=[
        {"metodo_pago": "EFECTIVO_COP", "moneda_id": 1, "monto": 150000, "fecha": "2026-11-01"},
        {"metodo_pago": "EFECTIVO_USD", "moneda_id": 2, "monto": 12.5, "tasa_cambio": 4000},
    ])
    venta2, det = _detalle_venta(client, pedido["id"])
    cleaner.registrar("venta", venta2["id"] if 'venta' not in venta2 else venta['id'] or venta2['id'])
    assert float(det["total_pagado"]) == 200000.0, "150.000 + 12,5 USD × 4.000"
    assert det["estado"] == "PAGADA"
    pagos = det["pagos"]
    assert len(pagos) == 2, f"deben ser dos pagos: {[p['metodo_pago'] for p in pagos]}"
    metodos = {p["metodo_pago"] for p in pagos}
    assert metodos == {"EFECTIVO_COP", "EFECTIVO_USD"}
    por_metodo = {p["metodo_pago"]: p for p in pagos}
    # 150.000 COP y 50.000 COP (12,5 USD × 4.000)
    assert float(por_metodo["EFECTIVO_COP"]["monto"]) == 150000.0
    assert str(por_metodo["EFECTIVO_COP"]["fecha"])[:10] == "2026-11-01", "fecha opcional del abono"
    assert float(por_metodo["EFECTIVO_USD"]["monto"]) == 12.5
    assert float(por_metodo["EFECTIVO_USD"]["monto_en_moneda_base"]) == 50000.0


def test_abono_mixto_parcial_queda_abonado(client, cleaner):
    """La suma no cubre la factura: el pedido nace ABONADA con los dos pagos."""
    cliente, prod, pedido, venta = _convertir_y_resolver(client, cleaner, 300000.0, adelantos=[
        {"metodo_pago": "EFECTIVO_COP", "moneda_id": 1, "monto": 200000},
        {"metodo_pago": "EFECTIVO_USD", "moneda_id": 2, "monto": 12.5, "tasa_cambio": 4000},
    ])
    venta2, det = _detalle_venta(client, pedido["id"])
    assert float(det["total_pagado"]) == 250000.0
    assert det["estado"] == "ABONADA"
    assert float(det["saldo_pendiente"]) == 50000.0


def test_abono_mixto_sin_tasa_rechaza(client, cleaner):
    import pytest
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], prod["id"], precio=200000)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 200000}],
        "adelantos": [
            {"metodo_pago": "EFECTIVO_COP", "moneda_id": 1, "monto": 100000},
            {"metodo_pago": "EFECTIVO_USD", "moneda_id": 2, "monto": 10},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "tasa" in r.text.lower()


def test_abono_mixto_mas_de_la_factura_rechaza(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], prod["id"], precio=200000)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 200000}],
        "adelantos": [
            {"metodo_pago": "EFECTIVO_COP", "moneda_id": 1, "monto": 150000},
            {"metodo_pago": "EFECTIVO_USD", "moneda_id": 2, "monto": 25, "tasa_cambio": 4000},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "saldo" in r.text.lower()
