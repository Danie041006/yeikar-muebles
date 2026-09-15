"""
test_descuento_cobro.py — Descuento otorgado al cobrar (cuentas por cobrar).

Caso del dueño: una deuda de 1.150.000 se deja en 1.000.000. El descuento
resta del saldo pendiente igual que un pago, pero NO genera MovimientoCaja.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_descuento_cobro.py -v
"""
from datetime import datetime

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_producto,
    crear_cotizacion,
    crear_pago,
    crear_descuento,
)


def _convertir(client, cleaner, cot_id, producto_id, precio):
    r = client.post(f"/api/v1/pedido/convertir/{cot_id}", json={
        "detalles": [{
            "producto_id": producto_id,
            "cantidad": 1,
            "precio": precio,
            "costo_unitario": 1000,
            "porcentaje_ganancia": 40,
        }],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    cleaner.registrar("pedido", r.json()["id"])
    return r.json()


def _venta_de_pedido(client, cleaner, db, pedido_id):
    row = db.execute(text("SELECT id FROM venta WHERE pedido_id=:p"), {"p": pedido_id}).fetchone()
    assert row, "la conversión debe generar la factura"
    venta_id = int(row[0])
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    assert det.status_code == 200
    cleaner.registrar("venta", venta_id)
    for d in det.json().get("detalles", []):
        cleaner.registrar("detalle_venta", d["id"])
    return venta_id


def _setup_venta(client, cleaner, db, precio=1150000, moneda_id=1, tasa_cambio=1.0):
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], precio,
                           moneda_id=moneda_id, tasa_cambio=tasa_cambio)
    pedido = _convertir(client, cleaner, cot["id"], prod["id"], precio)
    venta_id = _venta_de_pedido(client, cleaner, db, pedido["id"])
    return venta_id


def _caja_count(db):
    return db.execute(text("SELECT COUNT(*) FROM movimiento_caja")).fetchone()[0]


def test_caso_dueno_1150000_a_1000000(client, db, cleaner):
    """Cobran 1.000.000 y descuentan 150.000 → PAGADA con saldo 0."""
    venta_id = _setup_venta(client, cleaner, db, precio=1150000)

    r, pago = crear_pago(client, cleaner, venta_id, 1, 1000000)
    assert r.status_code == 201, f"pago → {r.status_code}: {pago}"

    r, desc = crear_descuento(client, cleaner, venta_id, 1, 150000, motivo="acuerdo con el dueño")
    assert r.status_code == 201, f"descuento → {r.status_code}: {desc}"
    assert float(desc["monto_en_moneda_base"]) == 150000.0

    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    assert det["estado"] == "PAGADA"
    assert float(det["total_pagado"]) == 1000000.0
    assert float(det["total_descontado"]) == 150000.0
    assert float(det["saldo_pendiente"]) == 0.0
    assert len(det["descuentos"]) == 1


def test_descuento_no_mueve_caja(client, db, cleaner):
    """El descuento no crea ningún MovimientoCaja (ni ENTRADA ni AJUSTE)."""
    venta_id = _setup_venta(client, cleaner, db, precio=500000)
    antes = _caja_count(db)
    r, desc = crear_descuento(client, cleaner, venta_id, 1, 50000)
    assert r.status_code == 201
    db.expire_all()
    assert _caja_count(db) == antes, "el descuento no debe tocar la caja"
    # Y el pago sí mueve caja (sanity: no rompimos los cobros normales).
    r, _ = crear_pago(client, cleaner, venta_id, 1, 100000)
    assert r.status_code == 201
    db.expire_all()
    assert _caja_count(db) == antes + 1


def test_descuento_parcial_deja_abonada(client, db, cleaner):
    """Descuento sin pagos → ABONADA; el pago del resto cierra la venta."""
    venta_id = _setup_venta(client, cleaner, db, precio=1150000)
    r, _ = crear_descuento(client, cleaner, venta_id, 1, 150000)
    assert r.status_code == 201
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    assert det["estado"] == "ABONADA"
    assert float(det["saldo_pendiente"]) == 1000000.0

    r, _ = crear_pago(client, cleaner, venta_id, 1, 1000000)
    assert r.status_code == 201
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    assert det["estado"] == "PAGADA"
    assert float(det["saldo_pendiente"]) == 0.0


def test_descuento_mayor_al_saldo_rechazado(client, db, cleaner):
    """No se puede perdonar más de lo que se debe (ni solo ni con pagos)."""
    venta_id = _setup_venta(client, cleaner, db, precio=100000)
    r, body = crear_descuento(client, cleaner, venta_id, 1, 100001)
    assert r.status_code == 400, f"descuento > total → {r.status_code}: {body}"

    r, _ = crear_pago(client, cleaner, venta_id, 1, 80000)
    assert r.status_code == 201
    r, body = crear_descuento(client, cleaner, venta_id, 1, 20001)
    assert r.status_code == 400, f"descuento > saldo → {r.status_code}: {body}"
    # El pago tampoco puede cobrar lo ya descontado.
    r, _ = crear_descuento(client, cleaner, venta_id, 1, 15000)
    assert r.status_code == 201
    r, body = crear_pago(client, cleaner, venta_id, 1, 6000)
    assert r.status_code == 400, f"pago > saldo tras descuento → {r.status_code}: {body}"
    r, _ = crear_pago(client, cleaner, venta_id, 1, 5000)
    assert r.status_code == 201
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    assert det["estado"] == "PAGADA"


def test_descuento_en_venta_pagada_rechazado(client, db, cleaner):
    venta_id = _setup_venta(client, cleaner, db, precio=100000)
    r, _ = crear_pago(client, cleaner, venta_id, 1, 100000)
    assert r.status_code == 201
    r, body = crear_descuento(client, cleaner, venta_id, 1, 1000)
    assert r.status_code == 400, f"descuento en PAGADA → {r.status_code}: {body}"


def test_anular_descuento_devuelve_saldo(client, db, cleaner):
    """Anular el descuento sube el saldo y reabre la venta (PAGADA → ABONADA)."""
    venta_id = _setup_venta(client, cleaner, db, precio=1150000)
    r, _ = crear_pago(client, cleaner, venta_id, 1, 1000000)
    assert r.status_code == 201
    r, desc = crear_descuento(client, cleaner, venta_id, 1, 150000)
    assert r.status_code == 201
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    assert det["estado"] == "PAGADA"

    r = client.delete(f"/api/v1/pago/descuento/{desc['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 204, f"anular → {r.status_code}: {r.text}"
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    assert det["estado"] == "ABONADA"
    assert float(det["total_descontado"]) == 0.0
    assert float(det["saldo_pendiente"]) == 150000.0
    assert det["descuentos"] == []

    r = client.delete("/api/v1/pago/descuento/999999999", headers=ADMIN_HEADERS)
    assert r.status_code == 404


def test_descuento_moneda_distinta_con_tasa(client, db, cleaner):
    """Venta en USD con descuento en COP: convierte con la tasa (sin redondeo
    al millar porque la factura no es COP) y exige tasa si falta."""
    venta_id = _setup_venta(client, cleaner, db, precio=1000, moneda_id=2, tasa_cambio=4200.0)
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    assert float(det["total"]) == 1000.0

    r, body = crear_descuento(client, cleaner, venta_id, 1, 420000)
    assert r.status_code == 400, f"sin tasa → {r.status_code}: {body}"

    r, desc = crear_descuento(client, cleaner, venta_id, 1, 420000, tasa_cambio=1 / 4200)
    assert r.status_code == 201, f"con tasa → {r.status_code}: {desc}"
    assert abs(float(desc["monto_en_moneda_base"]) - 100.0) < 0.01
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    assert abs(float(det["saldo_pendiente"]) - 900.0) < 0.01


def test_cuentas_por_cobrar_resta_descuento(client, db, cleaner):
    venta_id = _setup_venta(client, cleaner, db, precio=1150000)
    r, _ = crear_descuento(client, cleaner, venta_id, 1, 150000)
    assert r.status_code == 201
    r = client.get("/api/v1/venta/cuentas-por-cobrar/", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    cuenta = next((c for c in r.json() if c["venta_id"] == venta_id), None)
    assert cuenta is not None
    assert float(cuenta["total_descontado"]) == 150000.0
    assert float(cuenta["saldo_pendiente"]) == 1000000.0


def test_eliminar_venta_con_descuento_bloqueada(client, db, cleaner):
    venta_id = _setup_venta(client, cleaner, db, precio=200000)
    r, _ = crear_descuento(client, cleaner, venta_id, 1, 50000)
    assert r.status_code == 201
    r = client.delete(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"eliminar con descuento → {r.status_code}: {r.text}"
