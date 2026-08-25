"""
Fase 2 — Circuito contable: cada peso debe quedar en su cuenta.

Cubre los fixes de la auditoría E2E:
  H1: compra RECIBIDA descuenta la caja (movimiento SALIDA)
  H3: CANCELADA→RECIBIDA vuelve a registrar el stock
  H4: cancelar compra sin stock → 400 claro (no 500)
  H2: gasto con método de caja descuenta la cuenta
  H7: movimiento de caja con monto negativo → 422
  V2: tasa de pago absurda → 400; método↔moneda incoherente → 400
  D1: devolución > pagado → 400; devolución válida reembolsa caja
  P1: inventarios_finales NO incluyen caja; gastos PRODUCCION en el ER
"""
import pytest
from decimal import Decimal
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_movimiento,
    crear_producto,
    registrar_venta_de_pedido,
)


def _metodo_caja_id(db, codigo="EFECTIVO_COP"):
    return db.execute(
        text("SELECT id FROM metodo_caja WHERE codigo = :c"),
        {"c": codigo},
    ).scalar()


def _saldo_caja(db, metodo_caja_id):
    return db.execute(text(
        "SELECT COALESCE(SUM(CASE WHEN tipo IN ('APERTURA','ENTRADA') THEN monto ELSE -monto END), 0) "
        "FROM movimiento_caja WHERE metodo_caja_id = :m"
    ), {"m": metodo_caja_id}).scalar()


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
    venta = next(v for v in rv.json() if v["pedido_id"] == pedido["id"])
    cleaner.registrar("venta", venta["id"])
    return venta


# ---------------------------------------------------------------------------
# H1 + H3 + H4 — Compra con salida de caja y reversas correctas
# ---------------------------------------------------------------------------
def test_compra_contado_recibida_descarga_caja_y_reversa_ok(client, cleaner, db):
    """Compra CONTADO RECIBIDA → SALIDA de caja; CANCELADA → se revierte;
    CANCELADA→RECIBIDA de nuevo → stock y caja vuelven a entrar."""
    proveedor = client.post("/api/v1/proveedor/", json={"nombre": _uniq("prov")}, headers=ADMIN_HEADERS)
    proveedor_id = proveedor.json()["id"]
    cleaner.registrar("proveedor", proveedor_id)
    material = crear_material(client, cleaner, costo_base=2000.0)
    metodo_id = _metodo_caja_id(db)
    saldo_antes = _saldo_caja(db, metodo_id)

    payload = {
        "proveedor_id": proveedor_id, "moneda_id": 1,
        "fecha": "2026-08-12", "estado": "RECIBIDA", "tipo_pago": "CONTADO",
        "metodo_caja_id": metodo_id,
        "detalle": [{"material_id": material["id"], "cantidad": 50, "costo_unitario": 2000.0}],
        "observaciones": _uniq("e2e"),
    }
    r = client.post("/api/v1/compras/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"compra RECIBIDA → {r.status_code}: {r.text}"
    compra_id = r.json()["id"]
    cleaner.registrar("compra", compra_id)
    cleaner.registrar_caja_ref(f"Compra #{compra_id}")
    stock = db.execute(text("SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"),
                       {"m": material["id"]}).scalar()
    assert stock == pytest.approx(50)
    # La caja bajó exactamente el total (50 × 2000 = 100.000 COP)
    assert _saldo_caja(db, metodo_id) == pytest.approx(saldo_antes - 100000), (
        "H1: la compra RECIBIDA debe descargar la caja (SALIDA)"
    )

    # CANCELADA → stock revertido + caja restaurada
    r = client.put(f"/api/v1/compras/{compra_id}/estado", params={"estado": "CANCELADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"cancelar → {r.status_code}: {r.text}"
    stock = db.execute(text("SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"),
                       {"m": material["id"]}).scalar()
    assert stock == pytest.approx(0)
    assert _saldo_caja(db, metodo_id) == pytest.approx(saldo_antes), (
        "H1: cancelar la compra debe restaurar la caja"
    )

    # CANCELADA → RECIBIDA de nuevo: el stock DEBE volver a entrar (fix H3)
    r = client.put(f"/api/v1/compras/{compra_id}/estado", params={"estado": "RECIBIDA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"re-recibir → {r.status_code}: {r.text}"
    stock = db.execute(text("SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"),
                       {"m": material["id"]}).scalar()
    assert stock == pytest.approx(50), (
        "H3: CANCELADA→RECIBIDA debe re-registrar la entrada de stock"
    )
    assert _saldo_caja(db, metodo_id) == pytest.approx(saldo_antes - 100000)


def test_compra_contado_sin_metodo_caja_rechazada(client, cleaner, db):
    """Una compra CONTADO sin método de caja no puede recibirse: la plata
    debe salir de una cuenta (antes 'desaparecía')."""
    proveedor = client.post("/api/v1/proveedor/", json={"nombre": _uniq("prov")}, headers=ADMIN_HEADERS)
    proveedor_id = proveedor.json()["id"]
    cleaner.registrar("proveedor", proveedor_id)
    material = crear_material(client, cleaner, costo_base=2000.0)
    r = client.post("/api/v1/compras/", json={
        "proveedor_id": proveedor_id, "moneda_id": 1,
        "fecha": "2026-08-12", "estado": "RECIBIDA", "tipo_pago": "CONTADO",
        "detalle": [{"material_id": material["id"], "cantidad": 5, "costo_unitario": 2000.0}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"debe rechazar compra CONTADO sin método → {r.status_code}: {r.text}"
    assert "método de caja" in r.text.lower() or "metodo_caja" in r.text.lower()


# ---------------------------------------------------------------------------
# H2 — Gasto con salida de caja
# ---------------------------------------------------------------------------
def test_gasto_con_metodo_caja_descarga_cuenta(client, cleaner, db):
    tipo = db.execute(text("SELECT id FROM tipo_gasto LIMIT 1")).scalar()
    metodo_id = _metodo_caja_id(db)
    saldo_antes = _saldo_caja(db, metodo_id)
    r = client.post("/api/v1/gasto/gastos/", json={
        "tipo_gasto_id": tipo, "moneda_id": 1, "fecha": "2026-08-12",
        "monto": 300000, "metodo_caja_id": metodo_id,
        "observaciones": _uniq("e2e"),
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"gasto → {r.status_code}: {r.text}"
    gasto_id = r.json()["id"]
    cleaner.registrar("gasto", gasto_id)
    cleaner.registrar_caja_ref(f"Gasto #{gasto_id}")
    assert _saldo_caja(db, metodo_id) == pytest.approx(saldo_antes - 300000), (
        "H2: el gasto debe descargar la cuenta (SALIDA)"
    )
    # Eliminar el gasto revierte la caja
    r = client.delete(f"/api/v1/gasto/gastos/{gasto_id}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 204)
    assert _saldo_caja(db, metodo_id) == pytest.approx(saldo_antes)


# ---------------------------------------------------------------------------
# H7 — Movimiento de caja manual con monto negativo
# ---------------------------------------------------------------------------
def test_movimiento_caja_monto_negativo_rechazado(client, cleaner, db):
    metodo_id = _metodo_caja_id(db)
    r = client.post(f"/api/v1/cuenta/{metodo_id}/movimiento", json={
        "fecha": "2026-08-12", "tipo": "SALIDA", "monto": -100000, "moneda_id": 1,
        "observaciones": "intento drenar caja",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 422, f"monto negativo → 422, fue {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# V2 — Tasa absurda y método↔moneda incoherente
# ---------------------------------------------------------------------------
def test_pago_tasa_absurda_rechazado(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], producto["id"])
    r = client.post("/api/v1/pago/", json={
        "fecha": "2026-08-12", "monto": 100, "metodo_pago": "ZELLE",
        "venta_id": venta["id"], "moneda_id": 2, "tasa_cambio": 1e-10,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"tasa 1e-10 → 400, fue {r.status_code}: {r.text}"


def test_pago_metodo_moneda_incoherente_rechazado(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], producto["id"])
    # Pago USD entrando a la caja de pesos (EFECTIVO_COP) — descuadra el arqueo
    r = client.post("/api/v1/pago/", json={
        "fecha": "2026-08-12", "monto": 100, "metodo_pago": "EFECTIVO_COP",
        "venta_id": venta["id"], "moneda_id": 2, "tasa_cambio": 3130,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"USD con EFECTIVO_COP → 400, fue {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# D1 — Devolución limitada a lo pagado y con reembolso
# ---------------------------------------------------------------------------
def test_devolucion_no_supera_pagado_y_reembolsa(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    venta = _crear_venta_pendiente(client, cleaner, cliente["id"], producto["id"])
    # Pagar todo (COP)
    r = client.post("/api/v1/pago/", json={
        "fecha": "2026-08-12", "monto": 100000, "metodo_pago": "EFECTIVO_COP",
        "venta_id": venta["id"], "moneda_id": 1,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pago → {r.status_code}: {r.text}"
    cleaner.registrar("pago", r.json()["id"])

    # Devolución absurda (> pagado) → 400
    r = client.post("/api/v1/reports/devoluciones", json={
        "venta_id": venta["id"], "fecha": "2026-08-12", "cantidad": 1,
        "monto_devuelto": 999999999, "moneda_id": 1,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"devolución > pagado → 400, fue {r.status_code}: {r.text}"

    # Devolución válida → reembolso sale de caja
    metodo_id = _metodo_caja_id(db)
    saldo_antes = _saldo_caja(db, metodo_id)
    cleaner.registrar_caja_ref(f"Devolución venta #{venta['id']}")
    r = client.post("/api/v1/reports/devoluciones", json={
        "venta_id": venta["id"], "fecha": "2026-08-12", "cantidad": 1,
        "monto_devuelto": 50000, "moneda_id": 1, "motivo": "test e2e",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"devolución → {r.status_code}: {r.text}"
    dev_id = r.json()["id"]
    cleaner.registrar("devolucion_venta", dev_id)
    assert _saldo_caja(db, metodo_id) == pytest.approx(saldo_antes - 50000), (
        "D1: la devolución debe reembolsar desde la caja (SALIDA)"
    )


# ---------------------------------------------------------------------------
# P1 — Estado de resultados: inventarios limpios + gastos de producción
# ---------------------------------------------------------------------------
def test_informe_inventarios_no_incluyen_caja_y_si_produccion(client, cleaner, db):
    r = client.get("/api/v1/reports/informe-mensual", params={"mes": "2026-08"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"informe → {r.status_code}: {r.text}"
    informe = r.json()
    er = informe["estado_resultados"]
    nombres_inv = [l["nombre"] for l in er["inventarios_finales"]]
    assert not any("Caja" in n for n in nombres_inv), (
        "P1: los saldos de caja NO deben estar dentro de inventarios_finales "
        "(fabricaban utilidad ficticia)"
    )
    assert "saldos_caja" in informe and len(informe["saldos_caja"]) >= 0
    # El ER incluye la categoría PRODUCCION (consumo de materia prima)
    assert "total_gastos_produccion" in er["gastos"]
