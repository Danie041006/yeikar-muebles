# -*- coding: utf-8 -*-
"""
test_pago_fecha.py — La fecha de los abonos la elige el usuario.

Caso real: el cliente abona y a veces el cobro se registra días después
(el pago "sale antes"). Reglas:
  - `POST /pago/` con `fecha` → se respeta tal cual.
  - `POST /pago/` SIN `fecha` → el servidor guarda HOY (hora Venezuela).
  - `POST /pago/` guarda `created_at` (registro, hora VE) y `creado_por_id`.
  - `PUT /pago/{id}` corrige fecha/referencia/observaciones (y opcionalmente el
    monto, con su historial de corrección); arrastra el movimiento de caja y
    nunca cambia `created_at`. En este test el monto no se envía, así que se
    conserva intacto.
  - Abono inicial (conversión cotización → pedido): `fecha_adelanto` fija la
    fecha del primer pago de la factura; sin ella → hoy.
  - Fechas futuras se rechazan.

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_pago_fecha.py -v
"""
from datetime import timedelta

from sqlalchemy import text

from app.core.hora_ve import hoy_ve
from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_producto,
    registrar_venta_de_pedido,
)
from helpers_e2e import convertir_cotizacion


def _crear_venta_pendiente(client, cleaner, cliente_id, producto_id, precio=100000):
    """Cotización → pedido → venta pendiente (patrón de test_cuentas_por_persona)."""
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


# ---------------------------------------------------------------------------
# 1. Cobro sin fecha → HOY en hora Venezuela (antes el payload exigía fecha).
# ---------------------------------------------------------------------------
def test_pago_sin_fecha_guarda_hoy_ve(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"])

    r = client.post("/api/v1/pago/", json={
        "venta_id": venta["id"], "moneda_id": 1, "monto": 50000,
        "metodo_pago": "EFECTIVO_COP",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pago sin fecha → {r.status_code}: {r.text}"
    pago = r.json()
    cleaner.registrar("pago", pago["id"])
    assert pago["fecha"][:10] == str(hoy_ve()), (
        f"sin fecha debe guardarse HOY (VE) → {pago['fecha']}"
    )
    assert float(pago["monto"]) == 50000.0


# ---------------------------------------------------------------------------
# 2. Cobro con fecha pasada → se respeta (registrar un abono de días antes).
# ---------------------------------------------------------------------------
def test_pago_con_fecha_pasada_se_respeta(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"])

    fecha_pasada = str(hoy_ve() - timedelta(days=5))
    r = client.post("/api/v1/pago/", json={
        "venta_id": venta["id"], "moneda_id": 1, "monto": 30000,
        "metodo_pago": "EFECTIVO_COP", "fecha": fecha_pasada,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pago con fecha → {r.status_code}: {r.text}"
    pago = r.json()
    cleaner.registrar("pago", pago["id"])
    assert pago["fecha"][:10] == fecha_pasada, (
        f"la fecha enviada debe respetarse → {pago['fecha']}"
    )
    # El registro (cuándo se digitó) es independiente de la fecha del pago.
    assert pago["created_at"] and pago["created_at"][:10] == str(hoy_ve()), (
        f"created_at debe ser HOY (VE) → {pago['created_at']}"
    )
    assert pago["creado_por_id"] is not None, "el cobro debe guardar quién lo registró"
    assert pago["creador_nombre"], "el nombre del creador debe viajar en la respuesta"


# ---------------------------------------------------------------------------
# 2b. Fecha futura → se rechaza (no se puede cobrar algo que aún no pasó).
# ---------------------------------------------------------------------------
def test_pago_con_fecha_futura_se_rechaza(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"])

    manana = str(hoy_ve() + timedelta(days=1))
    r = client.post("/api/v1/pago/", json={
        "venta_id": venta["id"], "moneda_id": 1, "monto": 10000,
        "metodo_pago": "EFECTIVO_COP", "fecha": manana,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"fecha futura debe rechazarse → {r.status_code}: {r.text}"
    assert "futura" in r.text.lower()


# ---------------------------------------------------------------------------
# 2c. Corregir un cobro ya registrado: mueve la fecha del pago y la de caja.
# ---------------------------------------------------------------------------
def test_corregir_fecha_pago_mueve_caja(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"])

    r = client.post("/api/v1/pago/", json={
        "venta_id": venta["id"], "moneda_id": 1, "monto": 25000,
        "metodo_pago": "EFECTIVO_COP",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pago → {r.status_code}: {r.text}"
    pago = r.json()
    cleaner.registrar("pago", pago["id"])

    fecha_corregida = str(hoy_ve() - timedelta(days=4))
    r = client.put(
        f"/api/v1/pago/{pago['id']}",
        json={"fecha": fecha_corregida, "referencia": "CORREGIDO-123"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"corregir pago → {r.status_code}: {r.text}"
    corregido = r.json()
    assert corregido["fecha"][:10] == fecha_corregida
    assert corregido["referencia"] == "CORREGIDO-123"
    assert float(corregido["monto"]) == 25000.0, "la corrección no debe tocar el monto"
    assert corregido["created_at"] == pago["created_at"], (
        "la fecha de registro original no debe cambiar"
    )

    mov = db.execute(text(
        "SELECT fecha, referencia FROM movimiento_caja WHERE pago_id = :pid"
    ), {"pid": pago["id"]}).fetchone()
    assert mov is not None, "el cobro debe tener su movimiento de caja"
    assert str(mov[0])[:10] == fecha_corregida, (
        f"la caja debe moverse con la fecha corregida → {mov[0]}"
    )
    assert "CORREGIDO-123" in (mov[1] or "")


# ---------------------------------------------------------------------------
# 2d. Corregir a una fecha futura también se rechaza.
# ---------------------------------------------------------------------------
def test_corregir_pago_a_fecha_futura_se_rechaza(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], prod["id"])

    r = client.post("/api/v1/pago/", json={
        "venta_id": venta["id"], "moneda_id": 1, "monto": 15000,
        "metodo_pago": "EFECTIVO_COP",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pago → {r.status_code}: {r.text}"
    pago = r.json()
    cleaner.registrar("pago", pago["id"])

    manana = str(hoy_ve() + timedelta(days=1))
    r = client.put(
        f"/api/v1/pago/{pago['id']}",
        json={"fecha": manana},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, f"corrección futura debe rechazarse → {r.status_code}: {r.text}"
    assert "futura" in r.text.lower()


# ---------------------------------------------------------------------------
# 3. Abono inicial con fecha: el primer pago de la factura queda con ella.
# ---------------------------------------------------------------------------
def test_adelanto_inicial_con_fecha(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], prod["id"], precio=100000)

    fecha_pasada = str(hoy_ve() - timedelta(days=3))
    r, pedido = convertir_cotizacion(
        client, cleaner, cot["id"],
        detalles=[{"producto_id": prod["id"], "cantidad": 1, "precio": 100000}],
        adelanto=40000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP",
        fecha_adelanto=fecha_pasada,
    )
    assert r.status_code == 201 and pedido, f"convertir → {r.status_code}: {r.text}"

    row = db.execute(text(
        "SELECT p.fecha FROM pago p JOIN venta v ON v.id = p.venta_id "
        "WHERE v.pedido_id = :pid"
    ), {"pid": pedido["id"]}).fetchone()
    assert row is not None, "el abono inicial debe crear el primer pago de la factura"
    assert str(row[0])[:10] == fecha_pasada, (
        f"el adelanto debe quedar con la fecha elegida → {row[0]}"
    )


# ---------------------------------------------------------------------------
# 4. Abono inicial SIN fecha → hoy (default del servidor).
# ---------------------------------------------------------------------------
def test_adelanto_inicial_sin_fecha_usa_hoy(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], prod["id"], precio=100000)

    r, pedido = convertir_cotizacion(
        client, cleaner, cot["id"],
        detalles=[{"producto_id": prod["id"], "cantidad": 1, "precio": 100000}],
        adelanto=40000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP",
    )
    assert r.status_code == 201 and pedido, f"convertir → {r.status_code}: {r.text}"

    row = db.execute(text(
        "SELECT p.fecha FROM pago p JOIN venta v ON v.id = p.venta_id "
        "WHERE v.pedido_id = :pid"
    ), {"pid": pedido["id"]}).fetchone()
    assert row is not None, "el abono inicial debe crear el primer pago de la factura"
    assert str(row[0])[:10] == str(hoy_ve()), (
        f"sin fecha_adelanto debe usarse HOY → {row[0]}"
    )
