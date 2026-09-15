"""
test_diario_moneda.py — Estado del día desglosado por moneda.

Cubre la iteración 1 del rework del reporte diario:
- El abono a una CxP se lista con concepto corto ("Abono deuda #N — proveedor")
  y la referencia va aparte (antes el concepto ERA la referencia y la UI lo
  mostraba duplicado). El responsable es el nombre visible del usuario.
- `saldos_por_cuenta` trae una fila por (cuenta, moneda) con saldos NATIVOS:
  una cuenta en USD muestra dólares, no una cifra COP que se mezcla con pesos.
- El gasto nacido de una deuda (fiado) se marca "(fiado)" y no tiene cuenta
  de caja (nunca movió dinero), en vez de un "-" ambiguo.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_diario_moneda.py -v
"""
from datetime import date
from decimal import Decimal

from conftest import ADMIN_HEADERS, _uniq, crear_proveedor
from test_cuentas_por_pagar import (
    _abonar,
    _crear_deuda,
    _crear_tipo_gasto,
    _cuenta_usd,
)
from test_transferencias_caja import (
    _cuenta,
    _fondear,
    _moneda_id,
    _registrar_tasa,
)


def _diario(client, moneda=None):
    params = {"moneda": moneda} if moneda else {}
    r = client.get("/api/v1/reports/diario", params=params, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET /reports/diario → {r.status_code}: {r.text}"
    return r.json()


def _nombre_admin(client):
    r = client.get("/api/auth/me", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET /api/auth/me → {r.status_code}: {r.text}"
    me = r.json()
    return me.get("nombre") or me.get("nombre_usuario")


def test_diario_abono_cxp_concepto_limpio_y_quien(client, cleaner, db):
    cuenta, _ = _cuenta(db, cleaner)
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    cxp = _crear_deuda(client, cleaner, proveedor["id"], 300000.0, tg["id"])

    _fondear(client, cleaner, cuenta, 1, 300000)
    pago = _abonar(client, cxp["id"], 40000.0, cuenta)
    ref = f"CxP #{cxp['id']} abono #{pago['id']}"
    cleaner.registrar_caja_ref(ref)

    try:
        lineas = [
            m for m in _diario(client)["movimientos"]
            if (m["referencia"] or "") == ref
        ]
        assert len(lineas) == 1, f"esperaba 1 línea {ref}, hubo {len(lineas)}"
        linea = lineas[0]
        assert linea["tipo"] == "SALIDA"
        # Concepto corto con proveedor; la referencia va aparte, no duplicada.
        assert linea["concepto"] == f"Abono deuda #{cxp['id']} — {proveedor['nombre']}"
        assert linea["concepto"] != linea["referencia"]
        assert linea["quien"] == _nombre_admin(client)
    finally:
        client.delete(f"/api/v1/cuentas-por-pagar/abonos/{pago['id']}", headers=ADMIN_HEADERS)


def test_diario_saldos_desglosados_por_moneda(client, cleaner, db):
    moneda_usd = _moneda_id(db, "USD")
    if moneda_usd is None:
        import pytest
        pytest.skip("No hay moneda USD en la BD de pruebas")
    _registrar_tasa(db, cleaner, moneda_usd, 4000.0, date.today())
    cuenta_usd = _cuenta_usd(db, cleaner)

    # APERTURA de USD 50 hoy, con tasa explícita.
    ref = _uniq("fondeo-usd")
    r = client.post(f"/api/v1/cuenta/{cuenta_usd}/movimiento", json={
        "metodo_caja_id": cuenta_usd,
        "fecha": str(date.today()),
        "tipo": "APERTURA",
        "monto": 50,
        "moneda_id": moneda_usd,
        "tasa_cambio": 4000.0,
        "referencia": ref,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"fondear USD → {r.status_code}: {r.text}"
    cleaner.registrar_caja_ref(ref)

    filas = [
        s for s in _diario(client, "USD")["saldos_por_cuenta"]
        if s["metodo_caja_id"] == cuenta_usd
    ]
    assert len(filas) == 1, f"esperaba 1 fila (USD) para la cuenta, hubo {len(filas)}"
    fila = filas[0]
    assert fila["moneda_codigo"] == "USD"
    # Nativo en dólares: NO mezclado con COP.
    assert Decimal(str(fila["saldo_inicial"])) == Decimal("0")
    assert Decimal(str(fila["saldo_final"])) == Decimal("50")
    # COP solo como referencia convertida.
    assert Decimal(str(fila["saldo_final_cop"])) == Decimal("200000")


def test_diario_vista_usd_muestra_solo_dolares_en_nativo(client, cleaner, db):
    """?moneda=USD filtra la vista a dólares en valor nativo, SIN convertir.

    Aunque haya movimientos en COP el mismo día, la vista USD solo trae lo
    de USD y sus totales son nativos (no necesitan tasa registrada).
    """
    moneda_usd = _moneda_id(db, "USD")
    if moneda_usd is None:
        import pytest
        pytest.skip("No hay moneda USD en la BD de pruebas")
    cuenta_usd = _cuenta_usd(db, cleaner)
    cuenta_cop, _ = _cuenta(db, cleaner)

    ref_usd = _uniq("fondeo-usd-vista")
    r = client.post(f"/api/v1/cuenta/{cuenta_usd}/movimiento", json={
        "metodo_caja_id": cuenta_usd,
        "fecha": str(date.today()),
        "tipo": "APERTURA",
        "monto": 50,
        "moneda_id": moneda_usd,
        "tasa_cambio": 4000.0,
        "referencia": ref_usd,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"fondear USD → {r.status_code}: {r.text}"
    cleaner.registrar_caja_ref(ref_usd)
    # Ruido en COP el mismo día: no debe colarse en la vista USD.
    _fondear(client, cleaner, cuenta_cop, 1, 999000)

    r = client.get("/api/v1/reports/diario", params={"moneda": "USD"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["moneda_vista"] == "USD"

    # Tabs: COP siempre + USD por el movimiento.
    codigos = [m["codigo"] for m in body["monedas"]]
    assert "COP" in codigos and "USD" in codigos

    # Solo líneas en USD, en nativo.
    assert body["movimientos"], "la vista USD debería traer la APERTURA"
    assert all(m["moneda_codigo"] == "USD" for m in body["movimientos"])
    lineas = [m for m in body["movimientos"] if (m["referencia"] or "") == ref_usd]
    assert len(lineas) == 1
    assert Decimal(str(lineas[0]["monto"])) == Decimal("50")

    # Solo saldos en USD.
    assert body["saldos_por_cuenta"], "la vista USD debería traer el saldo"
    assert all(s["moneda_codigo"] == "USD" for s in body["saldos_por_cuenta"])
    filas = [s for s in body["saldos_por_cuenta"] if s["metodo_caja_id"] == cuenta_usd]
    assert len(filas) == 1
    assert Decimal(str(filas[0]["saldo_final"])) == Decimal("50")

    # Totales de la vista en nativo (la APERTURA suma como ingreso).
    assert Decimal(str(body["total_ingresos_vista"])) >= Decimal("50")
    # por_moneda sigue multimoneda (resumen general, no filtrado).
    assert {m["codigo"] for m in body["por_moneda"]} >= {"COP", "USD"}


def test_diario_vista_moneda_desconocida_400(client):
    r = client.get("/api/v1/reports/diario", params={"moneda": "XXX"}, headers=ADMIN_HEADERS)
    assert r.status_code == 400


def test_diario_gasto_fiado_sin_caja(client, cleaner):
    proveedor = crear_proveedor(client, cleaner)
    tg = _crear_tipo_gasto(client)
    cxp = _crear_deuda(client, cleaner, proveedor["id"], 123456.0, tg["id"])
    assert cxp["gasto_id"], "la deuda debió generar su gasto P&L"

    lineas = [
        m for m in _diario(client)["movimientos"]
        if (m["referencia"] or "") == f"Gasto #{cxp['gasto_id']}"
    ]
    assert len(lineas) == 1, f"esperaba 1 EGRESO del gasto fiado, hubo {len(lineas)}"
    linea = lineas[0]
    assert linea["tipo"] == "EGRESO"
    assert "(fiado)" in linea["concepto"]
    assert linea["cuenta_nombre"] is None
