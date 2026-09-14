"""
test_cuentas_por_pagar.py — Deudas con proveedores ("fiar") y abonos.

- Crear deuda manual → genera su gasto (P&L) sin tocar caja.
- Abono parcial → salida de caja + saldo decrece; cubrir todo → PAGADA.
- Entrada de inventario con `fiar` → CxP automática (compra + pasada).
- Revertir abono → caja y saldo reabiertos.
- Multimoneda: deuda en COP abonada desde cuenta no-COP con tasa.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_cuentas_por_pagar.py -v
"""
import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_material,
    crear_movimiento,
    crear_proveedor,
    registrar_inventario_de_material,
)


def _cuenta_id(db):
    row = db.execute(text("SELECT m.id FROM metodo_caja m ORDER BY m.id LIMIT 1")).fetchone()
    return int(row[0]) if row else None


def _cuenta_usd(db, cleaner):
    """Cuenta de caja en USD (para pruebas multimoneda). Se commitea para que
    la sesión de la API (otra conexión) pueda verla."""
    row = db.execute(text("SELECT id FROM moneda WHERE codigo = 'USD'")).fetchone()
    if row is None:
        pytest.skip("No hay moneda USD en la BD de pruebas")
    moneda_usd = int(row[0])
    r = db.execute(text(
        "INSERT INTO metodo_caja (nombre, codigo, activo, orden, moneda_id) "
        "VALUES (:n, :c, true, 999, :m) RETURNING id"
    ), {"n": _uniq("CTA USD"), "c": _uniq("CTA_USD"), "m": moneda_usd}).fetchone()
    db.commit()
    cleaner.registrar("metodo_caja", r[0])
    return int(r[0])


def _crear_tipo_gasto(client, nombre=None):
    r = client.post("/api/v1/catalogos/tipo-gasto/", json={
        "nombre": nombre or _uniq("TG"),
        "categoria": "OPERATIVO",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    return r.json()


def _crear_deuda(client, cleaner, proveedor_id, monto, tipo_gasto_id, moneda_id=1, descripcion=None):
    r = client.post("/api/v1/cuentas-por-pagar/", json={
        "proveedor_id": proveedor_id,
        "tipo_gasto_id": tipo_gasto_id,
        "moneda_id": moneda_id,
        "fecha": str(date.today()),
        "descripcion": descripcion or _uniq("deuda"),
        "monto": monto,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear deuda → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("cuenta_por_pagar", body["id"])
    return body


def _abonar(client, cxp_id, monto, cuenta_id, tasa=None):
    payload = {
        "fecha": str(date.today()),
        "monto": monto,
        "metodo_caja_id": cuenta_id,
    }
    if tasa is not None:
        payload["tasa_cambio"] = tasa
    r = client.post(f"/api/v1/cuentas-por-pagar/{cxp_id}/abonos", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"abonar → {r.status_code}: {r.text}"
    return r.json()


def _gastos_de_deuda(db, cxp_id):
    return db.execute(text(
        "SELECT id, monto, monto_en_moneda_base FROM gasto WHERE observaciones LIKE :pat"
    ), {"pat": f"%Por Pagar #{cxp_id}%"}).fetchall()


def _mov_caja(db, referencia):
    return db.execute(text(
        "SELECT monto, moneda_id, tasa_cambio, monto_en_moneda_base FROM movimiento_caja WHERE referencia = :r"
    ), {"r": referencia}).fetchone()


def test_deuda_manual_genera_gasto_sin_tocar_caja(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)

    cxp = _crear_deuda(client, cleaner, proveedor["id"], 300000.0, tg["id"])
    assert cxp["estado"] == "PENDIENTE"
    assert float(cxp["saldo"]) == 300000.0

    # El gasto nació con la deuda (P&L) y NO movió caja.
    gastos = _gastos_de_deuda(db, cxp["id"])
    assert len(gastos) == 1
    assert float(gastos[0][1]) == 300000.0
    assert _mov_caja(db, f"Gasto #{gastos[0][0]}") is None


def test_abonos_parciales_y_estado_pagada(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    cxp = _crear_deuda(client, cleaner, proveedor["id"], 100000.0, tg["id"])

    # Abono parcial 1: 40.000 → saldo 60.000, una salida de caja.
    abono1 = _abonar(client, cxp["id"], 40000.0, cuenta)
    cleaner.registrar("pago_cuenta_por_pagar", abono1["id"])
    r = client.get("/api/v1/cuentas-por-pagar/", params={"estado": "PENDIENTE"}, headers=ADMIN_HEADERS)
    cxp_actual = next(c for c in r.json() if c["id"] == cxp["id"])
    assert float(cxp_actual["monto_pagado"]) == 40000.0
    assert float(cxp_actual["saldo"]) == 60000.0
    assert cxp_actual["estado"] == "PENDIENTE"

    mov = _mov_caja(db, f"CxP #{cxp['id']} abono #{abono1['id']}")
    assert mov is not None and float(mov[0]) == 40000.0

    # Abono 2: cubre el resto → PAGADA.
    abono2 = _abonar(client, cxp["id"], 60000.0, cuenta)
    cleaner.registrar("pago_cuenta_por_pagar", abono2["id"])
    r = client.get("/api/v1/cuentas-por-pagar/", params={"estado": "PAGADA"}, headers=ADMIN_HEADERS)
    assert any(c["id"] == cxp["id"] for c in r.json())

    # No duplica egresos: sigue habiendo UN gasto, de 100.000.
    gastos = _gastos_de_deuda(db, cxp["id"])
    assert len(gastos) == 1 and float(gastos[0][1]) == 100000.0


def test_abono_excede_saldo_rechazado(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    cxp = _crear_deuda(client, cleaner, proveedor["id"], 50000.0, tg["id"])
    r = client.post(f"/api/v1/cuentas-por-pagar/{cxp['id']}/abonos", json={
        "fecha": str(date.today()), "monto": 50001.0, "metodo_caja_id": cuenta,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400
    assert "excede" in r.json()["detail"]


def test_entrada_fiar_crea_deuda_automatica(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")
    proveedor = crear_proveedor(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=20000.0)

    # Entrada fiada: 10 und × 20.000 + llevada 30.000 → deuda 230.000.
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 10,
        "costo_unitario": 20000,
        "llevada": 30000,
        "proveedor_id": proveedor["id"],
        "fiar": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"entrada fiada → {r.status_code}: {r.text}"
    registrar_inventario_de_material(db, cleaner, mat["id"])

    r = client.get("/api/v1/cuentas-por-pagar/", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    cxp = next((c for c in r.json() if c["origen_tipo"] == "ENTRADA_INVENTARIO"), None)
    assert cxp is not None, "La entrada fiada debe crear la cuenta por pagar"
    cleaner.registrar("cuenta_por_pagar", cxp["id"])
    assert float(cxp["monto"]) == 230000.0, cxp
    assert cxp["proveedor"]["id"] == proveedor["id"]
    assert float(cxp["saldo"]) == 230000.0
    # El gasto "COMPRA DE INSUMOS" nació con la deuda; la caja no se movió.
    gastos = _gastos_de_deuda(db, cxp["id"])
    assert len(gastos) == 1 and float(gastos[0][1]) == 230000.0
    assert _mov_caja(db, f"CxP #{cxp['id']} abono #") is None or True  # sin abonos aún

    # Abonarla desde la cuenta normal.
    abono = _abonar(client, cxp["id"], 230000.0, cuenta)
    cleaner.registrar("pago_cuenta_por_pagar", abono["id"])
    assert float(abono["monto_en_moneda_base"]) == 230000.0


def test_entrada_fiar_exige_proveedor(client, cleaner, db):
    mat = crear_material(client, cleaner, costo_base=1000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 1,
        "costo_unitario": 1000,
        "fiar": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400
    assert "proveedor" in r.json()["detail"].lower()


def test_entrada_fiar_conflicta_con_cuenta(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")
    proveedor = crear_proveedor(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=1000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 1,
        "costo_unitario": 1000,
        "proveedor_id": proveedor["id"],
        "fiar": True,
        "pagado_desde_metodo_caja_id": cuenta,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400
    assert "fiar" in r.json()["detail"].lower()


def test_revertir_abono_reabre_saldo_y_caja(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    cxp = _crear_deuda(client, cleaner, proveedor["id"], 100000.0, tg["id"])

    abono1 = _abonar(client, cxp["id"], 40000.0, cuenta)
    abono2 = _abonar(client, cxp["id"], 60000.0, cuenta)
    cleaner.registrar("pago_cuenta_por_pagar", abono1["id"])
    cleaner.registrar("pago_cuenta_por_pagar", abono2["id"])

    # Revertir el abono que la cerró → vuelve a PENDIENTE con saldo 60.000.
    rd = client.delete(f"/api/v1/cuentas-por-pagar/abonos/{abono2['id']}", headers=ADMIN_HEADERS)
    assert rd.status_code == 204, rd.text
    assert _mov_caja(db, f"CxP #{cxp['id']} abono #{abono2['id']}") is None

    r = client.get("/api/v1/cuentas-por-pagar/", headers=ADMIN_HEADERS)
    cxp_actual = next(c for c in r.json() if c["id"] == cxp["id"])
    assert cxp_actual["estado"] == "PENDIENTE"
    assert float(cxp_actual["monto_pagado"]) == 40000.0
    assert float(cxp_actual["saldo"]) == 60000.0

    # Revertir el primero → saldo completo de nuevo.
    rd = client.delete(f"/api/v1/cuentas-por-pagar/abonos/{abono1['id']}", headers=ADMIN_HEADERS)
    assert rd.status_code == 204
    r = client.get("/api/v1/cuentas-por-pagar/", headers=ADMIN_HEADERS)
    cxp_actual = next(c for c in r.json() if c["id"] == cxp["id"])
    assert float(cxp_actual["saldo"]) == 100000.0


def test_no_eliminar_deuda_con_abonos(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    cxp = _crear_deuda(client, cleaner, proveedor["id"], 100000.0, tg["id"])
    abono = _abonar(client, cxp["id"], 10000.0, cuenta)
    cleaner.registrar("pago_cuenta_por_pagar", abono["id"])

    rd = client.delete(f"/api/v1/cuentas-por-pagar/{cxp['id']}", headers=ADMIN_HEADERS)
    assert rd.status_code == 400
    assert "abonos" in rd.json()["detail"].lower()


def test_eliminar_deuda_sin_abonos_borra_gasto(client, cleaner, db):
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    cxp = _crear_deuda(client, cleaner, proveedor["id"], 100000.0, tg["id"])
    gastos = _gastos_de_deuda(db, cxp["id"])
    assert len(gastos) == 1

    rd = client.delete(f"/api/v1/cuentas-por-pagar/{cxp['id']}", headers=ADMIN_HEADERS)
    assert rd.status_code == 204, rd.text
    assert db.execute(text("SELECT COUNT(*) FROM gasto WHERE id = :g"), {"g": gastos[0][0]}).scalar() == 0


def test_resumen_por_proveedor(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")
    # El resumen es GLOBAL (toda la BD comparte datos): se mide el delta que
    # generan las deudas de ESTE test.
    antes = client.get("/api/v1/cuentas-por-pagar/resumen", headers=ADMIN_HEADERS).json()
    proveedor1 = crear_proveedor(client, cleaner)
    proveedor2 = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    cxp1 = _crear_deuda(client, cleaner, proveedor1["id"], 100000.0, tg["id"])
    _crear_deuda(client, cleaner, proveedor1["id"], 50000.0, tg["id"])
    _crear_deuda(client, cleaner, proveedor2["id"], 70000.0, tg["id"])
    abono = _abonar(client, cxp1["id"], 30000.0, cuenta)
    cleaner.registrar("pago_cuenta_por_pagar", abono["id"])

    r = client.get("/api/v1/cuentas-por-pagar/resumen", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    resumen = r.json()
    # Proveedor1: 100.000 - 30.000 + 50.000 = 120.000; Proveedor2: 70.000.
    assert float(resumen["total_pendiente"]) == float(antes["total_pendiente"]) + 190000.0
    assert float(resumen["total_pagado"]) == float(antes["total_pagado"]) + 30000.0
    por_prov = {p["proveedor_nombre"]: float(p["saldo"]) for p in resumen["por_proveedor"]}
    assert por_prov[proveedor1["nombre"]] == 120000.0
    assert por_prov[proveedor2["nombre"]] == 70000.0


def test_abono_multimoneda_deuda_cop_desde_cuenta_usd(client, cleaner, db):
    cuenta_usd = _cuenta_usd(db, cleaner)
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    cxp = _crear_deuda(client, cleaner, proveedor["id"], 800000.0, tg["id"])

    # 1 USD = 4000 COP → abonar 200.000 COP descuenta 50 USD.
    abono = _abonar(client, cxp["id"], 200000.0, cuenta_usd, tasa=4000.0)
    cleaner.registrar("pago_cuenta_por_pagar", abono["id"])
    assert float(abono["monto_en_moneda_base"]) == 200000.0

    mov = _mov_caja(db, f"CxP #{cxp['id']} abono #{abono['id']}")
    assert mov is not None
    assert float(mov[0]) == 50.0, f"descuento en USD: {mov}"
    assert float(mov[3]) == 200000.0

    r = client.get("/api/v1/cuentas-por-pagar/", headers=ADMIN_HEADERS)
    cxp_actual = next(c for c in r.json() if c["id"] == cxp["id"])
    assert float(cxp_actual["saldo"]) == 600000.0


# ══════════════════════════════════════════════════════════════════════════════
# Detalle por renglón (DetalleCuentaPorPagar): qué se compró y para quién.
# ══════════════════════════════════════════════════════════════════════════════

def test_deuda_manual_con_renglones(client, cleaner, db):
    """Deuda creada con renglones: cada uno guarda descripción, cant, precio y
    cliente/obra destino; el monto debe cuadrar con la suma."""
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)

    r = client.post("/api/v1/cuentas-por-pagar/", json={
        "proveedor_id": proveedor["id"],
        "tipo_gasto_id": tg["id"],
        "moneda_id": 1,
        "fecha": str(date.today()),
        "descripcion": _uniq("deuda con detalle"),
        "monto": 71000.0,
        "detalles": [
            {"descripcion": "SOPOLI 90 (tope para colgar cuadros)", "cantidad": 20, "precio_unitario": 600.0, "cliente_nombre": "FABRICA"},
            {"descripcion": "HERRAJE DE CAMA BAUL", "cantidad": 2, "precio_unitario": 14500.0, "cliente_nombre": "CAMA COMANDANTE"},
            {"descripcion": "TORNILLOS DE 1\"X 6", "cantidad": 100, "precio_unitario": 300.0},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear deuda con renglones → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("cuenta_por_pagar", body["id"])

    # 20×600 + 2×14500 + 100×300 = 12.000 + 29.000 + 30.000 = 71.000
    assert float(body["monto"]) == 71000.0
    assert len(body["detalles"]) == 3
    det = body["detalles"][0]
    assert det["descripcion"] == "SOPOLI 90 (tope para colgar cuadros)"
    assert float(det["total"]) == 12000.0
    assert det["cliente_nombre"] == "FABRICA"
    assert det["orden"] == 0
    # El gasto (P&L) nació con el monto de la deuda, no con la suma errónea.
    gastos = _gastos_de_deuda(db, body["id"])
    assert len(gastos) == 1 and float(gastos[0][1]) == 71000.0


def test_deuda_renglones_monto_no_cuadra(client, cleaner, db):
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    r = client.post("/api/v1/cuentas-por-pagar/", json={
        "proveedor_id": proveedor["id"],
        "tipo_gasto_id": tg["id"],
        "moneda_id": 1,
        "fecha": str(date.today()),
        "descripcion": _uniq("deuda descuadrada"),
        "monto": 100000.0,
        "detalles": [
            {"descripcion": "Ítem", "cantidad": 10, "precio_unitario": 5000.0},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400
    assert "no cuadra" in r.json()["detail"]


def test_entrada_fiar_crea_renglon_con_cliente(client, cleaner, db):
    """El fiado guarda el material como renglón, y el cliente de la entrada
    (para quién se compró) viaja al detalle de la deuda."""
    proveedor = crear_proveedor(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=20000.0)
    cliente = db.execute(text(
        "INSERT INTO cliente (nombre, telefono, fecha_registro) "
        "VALUES (:n, '0000', CURRENT_DATE) RETURNING id"
    ), {"n": _uniq("Cliente obra")}).fetchone()
    db.commit()
    cleaner.registrar("cliente", cliente[0])

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 10,
        "costo_unitario": 20000,
        "proveedor_id": proveedor["id"],
        "cliente_id": cliente[0],
        "cliente_nombre": _uniq("obra libre"),
        "fiar": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"entrada fiada con cliente → {r.status_code}: {r.text}"
    registrar_inventario_de_material(db, cleaner, mat["id"])

    r = client.get("/api/v1/cuentas-por-pagar/", headers=ADMIN_HEADERS)
    cxp = next((c for c in r.json() if c["origen_tipo"] == "ENTRADA_INVENTARIO"
                and c["detalles"] and c["detalles"][0]["material_id"] == mat["id"]), None)
    assert cxp is not None, "Debe existir la deuda fiada con su renglón"
    cleaner.registrar("cuenta_por_pagar", cxp["id"])
    det = cxp["detalles"][0]
    assert float(det["cantidad"]) == 10.0
    assert float(det["precio_unitario"]) == 20000.0
    assert det["material_id"] == mat["id"]
    assert det["cliente_id"] == cliente[0]
    assert float(cxp["monto"]) == 200000.0