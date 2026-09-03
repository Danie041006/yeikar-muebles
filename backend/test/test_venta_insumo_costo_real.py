"""
test_venta_insumo_costo_real.py — Costo real del insumo (compra + pasada).

"La pasada" (llevada/flete) se registra como monto TOTAL en la ENTRADA de
inventario; el costo real por unidad = costo_unitario + llevada/cantidad.

Cadena probada:
  - Endpoint /inventario/material/{id}/costo-unitario-real (con y sin llevada).
  - Cotización INSUMO con costo_total (costo real × cantidad) → pedido → venta:
    el costo unitario real se propaga y la utilidad se calcula contra
    compra + pasada (no contra el precio de compra pelado).
  - Cotización vieja SIN costo guardado: fallback al costo_base (compatibilidad).

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_venta_insumo_costo_real.py -v
"""
import pytest
from datetime import date

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_cliente,
    crear_material,
    registrar_inventario_de_material,
)


def _costo_real(client, material_id) -> dict:
    r = client.get(f"/api/v1/inventario/material/{material_id}/costo-unitario-real", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"costo-unitario-real → {r.status_code}: {r.text}"
    return r.json()


def _cotizacion_insumo(client, cleaner, cliente_id, material_id, precio, cantidad=1, costo_total=None):
    detalle = {
        "producto_id": None,
        "material_id": material_id,
        "tipo_item": "INSUMO",
        "cantidad": cantidad,
        "precio": precio,
    }
    if costo_total is not None:
        detalle["costo_total"] = costo_total
    payload = {
        "cliente_id": cliente_id,
        "fecha": str(date.today()),
        "estado": "BORRADOR",
        "total_estimado": round(precio * cantidad, 2),
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": _uniq("cot_insumo_costo"),
        "detalles": [detalle],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear cotización INSUMO → {r.status_code}: {r.text}"
    cot = r.json()
    cleaner.registrar("cotizacion", cot["id"])
    return cot


def _convertir(client, cleaner, cot_id, material_id, precio, cantidad):
    r = client.post(f"/api/v1/pedido/convertir/{cot_id}", json={
        "detalles": [
            {
                "producto_id": None,
                "material_id": material_id,
                "tipo_item": "INSUMO",
                "cantidad": cantidad,
                "precio": precio,
            }
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"conversión INSUMO → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    from conftest import registrar_venta_de_pedido
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    return pedido


def _detalle_venta(client, pedido_id):
    from sqlalchemy import text
    r = client.get("/api/v1/venta/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    venta = next((v for v in r.json() if v.get("pedido_id") == pedido_id), None)
    assert venta is not None, "La conversión debe crear la venta automáticamente"
    rv = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS)
    assert rv.status_code == 200
    detalles = rv.json()["detalles"]
    assert len(detalles) == 1
    return detalles[0]


def test_endpoint_costo_real_con_llevada(client, cleaner, db):
    """Compra 10 und a 30.000 + pasada 50.000 → costo real 35.000/und."""
    mat = crear_material(client, cleaner, costo_base=30000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 10,
        "costo_unitario": 30000,
        "llevada": 50000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])

    c = _costo_real(client, mat["id"])
    assert c["costo_compra"] == 30000.0
    assert c["pasada_unitaria"] == 5000.0
    assert c["costo_real"] == 35000.0


def test_endpoint_costo_real_sin_llevada_y_sin_entradas(client, cleaner, db):
    """Sin llevada → pasada 0 y costo = último costo de entrada; sin entradas
    → fallback a material.costo_base."""
    mat = crear_material(client, cleaner, costo_base=12000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 4,
        "costo_unitario": 12000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])

    c = _costo_real(client, mat["id"])
    assert c["costo_compra"] == 12000.0
    assert c["pasada_unitaria"] == 0.0
    assert c["costo_real"] == 12000.0

    mat_sin = crear_material(client, cleaner, costo_base=8000.0)
    c2 = _costo_real(client, mat_sin["id"])
    assert c2["costo_compra"] == 8000.0
    assert c2["pasada_unitaria"] == 0.0
    assert c2["costo_real"] == 8000.0


def test_venta_insumo_con_pasada_calcula_utilidad_real(client, cleaner, db):
    """Costo real 35.000 (compra 30.000 + pasada 5.000) vendido a 50.000 →
    utilidad 15.000/und y margen 42.86%. El costo NO puede ser 30.000 (como si
    la pasada no existiera) ni 50.000 (como si se vendiera al costo)."""
    cliente = crear_cliente(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=30000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 10,
        "costo_unitario": 30000,
        "llevada": 50000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])

    precio = 50000.0
    cot = _cotizacion_insumo(client, cleaner, cliente["id"], mat["id"], precio,
                             cantidad=1, costo_total=35000.0)
    pedido = _convertir(client, cleaner, cot["id"], mat["id"], precio, 1)

    d = _detalle_venta(client, pedido["id"])
    assert d["tipo_item"] == "INSUMO"
    assert float(d["costo_unitario"]) == 35000.0, f"costo unitario real: {d['costo_unitario']}"
    assert float(d["precio"]) == 50000.0
    assert float(d["utilidad"]) == 15000.0, f"utilidad real (venta − compra − pasada): {d['utilidad']}"
    assert abs(float(d["porcentaje_ganancia"]) - 42.86) < 0.01, d["porcentaje_ganancia"]


def test_venta_insumo_cantidad_mayor_uno_divides_costo_total(client, cleaner, db):
    """Con cantidad 2 y costo_total = 35.000 × 2, el costo unitario del pedido
    debe ser 35.000 (no 70.000)."""
    cliente = crear_cliente(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=30000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 10,
        "costo_unitario": 30000,
        "llevada": 50000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])

    precio = 50000.0
    cot = _cotizacion_insumo(client, cleaner, cliente["id"], mat["id"], precio,
                             cantidad=2, costo_total=70000.0)
    pedido = _convertir(client, cleaner, cot["id"], mat["id"], precio, 2)

    d = _detalle_venta(client, pedido["id"])
    assert float(d["costo_unitario"]) == 35000.0, f"costo unitario debe dividirse por cantidad: {d['costo_unitario']}"
    assert float(d["cantidad"]) == 2
    assert float(d["utilidad"]) == 15000.0


def test_venta_insumo_sin_costo_guardado_fallback_costo_base(client, cleaner, db):
    """Cotización vieja SIN costo_total guardado (comportamiento anterior) →
    la venta cae al fallback material.costo_base y no rompe."""
    cliente = crear_cliente(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=30000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 10,
        "costo_unitario": 30000,
        "llevada": 50000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])

    precio = 50000.0
    cot = _cotizacion_insumo(client, cleaner, cliente["id"], mat["id"], precio, cantidad=1)
    pedido = _convertir(client, cleaner, cot["id"], mat["id"], precio, 1)

    d = _detalle_venta(client, pedido["id"])
    assert float(d["costo_unitario"]) == 30000.0, f"fallback costo_base: {d['costo_unitario']}"
    assert float(d["utilidad"]) == 20000.0