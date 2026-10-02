"""
Cuentas por persona — el catálogo metodo_caja es la fuente de verdad.

Cubre:
  1. Crear una cuenta con moneda explícita (POST /cuenta/) y que quede
     registrada con esa moneda.
  2. Cobrar una venta con el código de una cuenta nueva (fuera de la lista
     fija histórica) → 201 y movimiento ENTRADA en esa cuenta.
  3. Cobro con la moneda equivocada respecto a la moneda de la cuenta → 400.
"""
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_cliente,
    crear_cotizacion,
    crear_producto,
    registrar_venta_de_pedido,
)


def _crear_venta_pendiente(client, cleaner, cliente_id, producto_id):
    cot = crear_cotizacion(client, cleaner, cliente_id, producto_id, precio=100000)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": producto_id, "cantidad": 1, "precio": 100000}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    rv = client.get("/api/v1/venta/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    return next(v for v in rv.json() if v["pedido_id"] == pedido["id"])


def _crear_cuenta(client, cleaner, db, nombre, codigo, moneda_id):
    """Crea una cuenta vía API y registra en el cleaner la cuenta y su
    movimiento de apertura automático."""
    r = client.post("/api/v1/cuenta/", json={
        "nombre": nombre, "codigo": codigo, "moneda_id": moneda_id, "orden": 250,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear cuenta → {r.status_code}: {r.text}"
    cuenta = r.json()
    assert cuenta["moneda_id"] == moneda_id, cuenta
    cleaner.registrar("metodo_caja", cuenta["id"])
    for (mid,) in db.execute(
        text("SELECT id FROM movimiento_caja WHERE metodo_caja_id = :m"),
        {"m": cuenta["id"]},
    ).fetchall():
        cleaner.registrar("movimiento_caja", mid)
    return cuenta


def test_crear_cuenta_con_moneda_y_cobrar_con_codigo_propio(client, cleaner, db):
    cuenta = _crear_cuenta(client, cleaner, db, _uniq("cuenta"), _uniq("CTA").upper(), 1)
    assert cuenta["moneda_codigo"] == "COP"

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], producto["id"])

    r = client.post("/api/v1/pago/", json={
        "venta_id": venta["id"], "moneda_id": 1, "monto": 100000,
        "metodo_pago": cuenta["codigo"], "fecha": "2026-08-12",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"cobro con cuenta nueva → {r.status_code}: {r.text}"
    pago = r.json()
    cleaner.registrar("pago", pago["id"])

    fila = db.execute(text(
        "SELECT m.metodo_caja_id, m.monto FROM movimiento_caja m "
        "JOIN pago p ON p.id = m.pago_id WHERE p.id = :p"
    ), {"p": pago["id"]}).fetchone()
    assert fila is not None, "El cobro debe registrar movimiento de caja"
    assert int(fila[0]) == cuenta["id"], f"Debe entrar a la cuenta nueva, fue {fila[0]}"
    assert float(fila[1]) == 100000.0


def test_cobro_en_moneda_distinta_a_la_cuenta_rechazado(client, cleaner, db):
    cuenta = _crear_cuenta(client, cleaner, db, _uniq("cuenta_ves"), _uniq("VES").upper(), 3)
    assert cuenta["moneda_codigo"] == "VES"

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], producto["id"])

    r = client.post("/api/v1/pago/", json={
        "venta_id": venta["id"], "moneda_id": 1, "monto": 100000,
        "metodo_pago": cuenta["codigo"], "fecha": "2026-08-12",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"COP a cuenta VES → 400, fue {r.status_code}: {r.text}"
