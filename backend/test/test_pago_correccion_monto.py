# -*- coding: utf-8 -*-
"""
test_pago_correccion_monto.py — Corregir el MONTO de un abono ya registrado.

Caso real: en Ventas y Cobros se podía corregir la fecha/la referencia de un
cobro, pero no el monto. Al corregirlo, TODO lo que depende debe quedar
cuadrado:
  - `Pago.monto` y su equivalente en la moneda de la venta.
  - El movimiento de caja (ENTRADA): se actualiza en sitio, sin duplicarlo.
  - El estado y el saldo de la venta (PAGADA ↔ ABONADA).
  - El historial de correcciones visible en Ventas y Cobros.
  - La auditoría del sistema con el antes/después.
La cotización no muestra el historial de correcciones: solo el monto vigente.

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_pago_correccion_monto.py -v
"""
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_producto,
    registrar_venta_de_pedido,
)


def _crear_venta_pendiente(client, cleaner, cliente_id, producto_id, precio=100000):
    """Cotización → pedido → venta pendiente (patrón de test_pago_fecha)."""
    cot = crear_cotizacion(client, cleaner, cliente_id, producto_id, precio=precio)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": producto_id, "cantidad": 1, "precio": precio}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    rv = client.get("/api/v1/venta/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    return next(v for v in rv.json() if v["pedido_id"] == pedido["id"])


def _registrar_pago(client, cleaner, venta, monto, moneda_id=1,
                    metodo_pago="EFECTIVO_COP", tasa_cambio=None):
    payload = {
        "venta_id": venta["id"],
        "moneda_id": moneda_id,
        "monto": monto,
        "metodo_pago": metodo_pago,
    }
    if tasa_cambio is not None:
        payload["tasa_cambio"] = tasa_cambio
    r = client.post("/api/v1/pago/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pago → {r.status_code}: {r.text}"
    pago = r.json()
    cleaner.registrar("pago", pago["id"])
    return pago


def _movimientos_del_pago(db, pago_id):
    return db.execute(text(
        "SELECT id, monto, monto_en_moneda_base, fecha, referencia "
        "FROM movimiento_caja WHERE pago_id = :pid ORDER BY id"
    ), {"pid": pago_id}).fetchall()


# ---------------------------------------------------------------------------
# 1. Corregir el monto hacia abajo: pago, caja, saldo, estado e historial.
# ---------------------------------------------------------------------------
def test_corregir_monto_actualiza_pago_caja_saldo_e_historial(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"], precio=100000)
    pago = _registrar_pago(client, cleaner, venta, 30000)

    r = client.put(
        f"/api/v1/pago/{pago['id']}",
        json={"monto": 20000, "motivo_correccion": "Se digitó 30.000 en vez de 20.000"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"corregir monto → {r.status_code}: {r.text}"
    corregido = r.json()
    assert float(corregido["monto"]) == 20000.0
    assert float(corregido["monto_en_moneda_base"]) == 20000.0
    assert len(corregido["correcciones"]) == 1, (
        f"debe quedar 1 corrección visible → {corregido['correcciones']}"
    )
    hist = corregido["correcciones"][0]
    assert float(hist["monto_anterior"]) == 30000.0
    assert float(hist["monto_nuevo"]) == 20000.0
    assert hist["motivo"] == "Se digitó 30.000 en vez de 20.000"
    assert hist["usuario_nombre"], "la corrección debe decir quién la hizo"
    assert corregido["created_at"] == pago["created_at"], (
        "la fecha de registro original no debe cambiar"
    )

    # La venta y la caja quedan cuadradas con el nuevo monto.
    detalle = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert float(detalle["total_pagado"]) == 20000.0
    assert float(detalle["saldo_pendiente"]) == 80000.0
    assert detalle["estado"] == "ABONADA"

    movs = _movimientos_del_pago(db, pago["id"])
    assert len(movs) == 1, f"no debe duplicar el movimiento de caja → {movs}"
    assert float(movs[0][1]) == 20000.0
    assert float(movs[0][2]) == 20000.0

    estado_db = db.execute(text(
        "SELECT estado FROM venta WHERE id = :vid"
    ), {"vid": venta["id"]}).scalar_one()
    assert estado_db == "ABONADA"

    # La auditoría guarda el antes/después (para "correcciones").
    audit = db.execute(text(
        "SELECT before_data->>'monto', after_data->>'monto' "
        "FROM audit_event WHERE entity_type = 'pago' AND entity_id = :eid "
        "ORDER BY id DESC LIMIT 1"
    ), {"eid": str(pago["id"])}).fetchone()
    assert audit is not None, "debe quedar evento de auditoría de la corrección"
    assert float(audit[0]) == 30000.0 and float(audit[1]) == 20000.0


# ---------------------------------------------------------------------------
# 2. Corregir hacia arriba, cerrar la venta y rechazar un exceso de saldo.
# ---------------------------------------------------------------------------
def test_corregir_monto_hacia_arriba_y_rechazar_exceso(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"], precio=100000)
    pago = _registrar_pago(client, cleaner, venta, 30000)

    r = client.put(
        f"/api/v1/pago/{pago['id']}", json={"monto": 60000}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, f"subir monto → {r.status_code}: {r.text}"
    assert float(r.json()["monto_en_moneda_base"]) == 60000.0

    detalle = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert float(detalle["saldo_pendiente"]) == 40000.0
    assert detalle["estado"] == "ABONADA"

    # El exceso se rechaza y NO deja rastro (rollback limpio).
    r = client.put(
        f"/api/v1/pago/{pago['id']}", json={"monto": 200000}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 400, f"exceso debe rechazarse → {r.status_code}: {r.text}"
    assert "saldo" in r.text.lower()

    pago_db = db.execute(text(
        "SELECT monto, monto_en_moneda_base FROM pago WHERE id = :pid"
    ), {"pid": pago["id"]}).fetchone()
    assert float(pago_db[0]) == 60000.0
    assert float(pago_db[1]) == 60000.0
    historial = db.execute(text(
        "SELECT count(*) FROM pago_correccion WHERE pago_id = :pid"
    ), {"pid": pago["id"]}).scalar_one()
    assert historial == 1, "el intento rechazado no debe crear historial"

    # Exactamente el saldo restante cierra la venta (PAGADA).
    r = client.put(
        f"/api/v1/pago/{pago['id']}", json={"monto": 100000}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, f"cerrar venta → {r.status_code}: {r.text}"
    detalle = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert float(detalle["saldo_pendiente"]) == 0.0
    assert detalle["estado"] == "PAGADA"


# ---------------------------------------------------------------------------
# 3. Bajar un abono que había dejado la venta PAGADA → vuelve a ABONADA.
# ---------------------------------------------------------------------------
def test_bajar_abono_devuelve_la_venta_a_abonada(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"], precio=50000)
    pago = _registrar_pago(client, cleaner, venta, 50000)

    detalle = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert detalle["estado"] == "PAGADA"

    r = client.put(
        f"/api/v1/pago/{pago['id']}", json={"monto": 20000}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, f"bajar monto → {r.status_code}: {r.text}"

    detalle = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert detalle["estado"] == "ABONADA"
    assert float(detalle["saldo_pendiente"]) == 30000.0


# ---------------------------------------------------------------------------
# 4. Pago en moneda extranjera: recalcula el equivalente con la tasa del pago.
# ---------------------------------------------------------------------------
def test_corregir_monto_multimoneda_recalcula_base_y_caja(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"], precio=400000)
    # 50 USD × 4.000 = 200.000 COP.
    pago = _registrar_pago(
        client, cleaner, venta, 50, moneda_id=2,
        metodo_pago="EFECTIVO_USD", tasa_cambio=4000,
    )
    assert float(pago["monto_en_moneda_base"]) == 200000.0

    r = client.put(
        f"/api/v1/pago/{pago['id']}", json={"monto": 20}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, f"corregir USD → {r.status_code}: {r.text}"
    corregido = r.json()
    assert float(corregido["monto"]) == 20.0
    # 20 USD × 4.000 = 80.000 COP (redondeo al millar de la factura COP).
    assert float(corregido["monto_en_moneda_base"]) == 80000.0

    movs = _movimientos_del_pago(db, pago["id"])
    assert len(movs) == 1
    assert float(movs[0][1]) == 20.0
    assert float(movs[0][2]) == 80000.0

    detalle = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert float(detalle["total_pagado"]) == 80000.0
    assert float(detalle["saldo_pendiente"]) == 320000.0


# ---------------------------------------------------------------------------
# 5. Corregir fecha/referencia/observaciones NO marca "monto corregido".
# ---------------------------------------------------------------------------
def test_corregir_fecha_o_referencia_no_crea_historial_de_monto(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"])
    pago = _registrar_pago(client, cleaner, venta, 25000)

    r = client.put(
        f"/api/v1/pago/{pago['id']}",
        json={"referencia": "REF-CORREGIDA", "observaciones": "nota"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"corregir referencia → {r.status_code}: {r.text}"
    assert r.json()["correcciones"] == [], (
        "una corrección que no toca el monto no debe aparecer como monto corregido"
    )
    assert float(r.json()["monto"]) == 25000.0

    # Reenviar el mismo monto tampoco crea historial.
    r = client.put(
        f"/api/v1/pago/{pago['id']}", json={"monto": 25000}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200
    assert r.json()["correcciones"] == []


# ---------------------------------------------------------------------------
# 6. Un monto <= 0 se rechaza antes de tocar la BD.
# ---------------------------------------------------------------------------
def test_monto_cero_o_negativo_se_rechaza(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"])
    pago = _registrar_pago(client, cleaner, venta, 30000)

    for invalido in (0, -5):
        r = client.put(
            f"/api/v1/pago/{pago['id']}", json={"monto": invalido}, headers=ADMIN_HEADERS
        )
        assert r.status_code == 422, (
            f"monto {invalido} debe rechazarse → {r.status_code}: {r.text}"
        )

    pago_db = db.execute(text(
        "SELECT monto FROM pago WHERE id = :pid"
    ), {"pid": pago["id"]}).scalar_one()
    assert float(pago_db) == 30000.0
