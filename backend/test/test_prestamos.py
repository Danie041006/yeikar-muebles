"""
test_prestamos.py — Préstamos por cobrar desde Cuentas.

Flujo (decisión del dueño 31/10/2026):
  * El préstamo NACE en una SALIDA de caja clasificada PRESTAMO. La persona
    (persona_entidad) es obligatoria: es a quien se le va a cobrar.
  * El cobro se registra como ENTRADA con `cobro_prestamo`; la entrada de caja
    y el abono al préstamo son una sola operación.
  * Si la cuenta donde entra el dinero tiene otra moneda que el préstamo, la
    tasa de conversión es obligatoria.
  * Eliminar la entrada de cobro devuelve el saldo; eliminar la salida borra el
    préstamo (solo si no tiene cobros).

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_prestamos.py -v
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from conftest import ADMIN_HEADERS, _uniq


def _moneda_id(db, codigo):
    row = db.execute(text("SELECT id FROM moneda WHERE codigo = :c"), {"c": codigo}).fetchone()
    return int(row[0]) if row else None


def _cuenta(db, cleaner, codigo_moneda="COP"):
    mid = 1 if codigo_moneda == "COP" else _moneda_id(db, codigo_moneda)
    if mid is None:
        pytest.skip(f"No hay moneda {codigo_moneda} en la BD de pruebas")
    r = db.execute(text(
        "INSERT INTO metodo_caja (nombre, codigo, activo, orden, moneda_id) "
        "VALUES (:n, :c, true, 999, :m) RETURNING id"
    ), {"n": _uniq("CTA"), "c": _uniq("CTA"), "m": mid}).fetchone()
    db.commit()
    cleaner.registrar("metodo_caja", r[0])
    return int(r[0]), mid


def _prestar(client, db, cleaner, cuenta_id, moneda_id, monto, persona, **extra):
    """SALIDA clasificada PRESTAMO. Registra en el cleaner el gasto espejo, su
    movimiento y el préstamo creado."""
    concepto = _uniq("prestamo")
    payload = {
        "metodo_caja_id": cuenta_id,
        "fecha": str(date.today()),
        "tipo": "SALIDA",
        "monto": monto,
        "moneda_id": moneda_id,
        "persona_entidad": persona,
        "concepto": concepto,
        "clasificacion": "PRESTAMO",
        "tipo_prestamo": "POR_COBRAR",
    }
    payload.update(extra)
    r = client.post(f"/api/v1/cuenta/{cuenta_id}/movimiento", json=payload, headers=ADMIN_HEADERS)
    if r.status_code != 201:
        return r, None, None

    fila = db.execute(text(
        "SELECT g.id, mc.id FROM gasto g "
        "JOIN movimiento_caja mc ON mc.referencia = ('Gasto #' || g.id) "
        "WHERE g.descripcion = :d ORDER BY g.id DESC LIMIT 1"
    ), {"d": concepto}).fetchone()
    prestamo_id = None
    if fila:
        cleaner.registrar("gasto", fila[0])
        cleaner.registrar("movimiento_caja", fila[1])
        prestamo_id = db.execute(text(
            "SELECT id FROM prestamo WHERE movimiento_caja_id = :m"
        ), {"m": fila[1]}).scalar()
        if prestamo_id:
            cleaner.registrar("prestamo", prestamo_id)
    return r, r.json(), prestamo_id


def _cobrar(client, cleaner, cuenta_id, moneda_cuenta_id, persona, moneda_prestamo_id,
            monto, **extra):
    payload = {
        "metodo_caja_id": cuenta_id,
        "fecha": str(date.today()),
        "tipo": "ENTRADA",
        "monto": monto,
        "moneda_id": moneda_cuenta_id,
        "cobro_prestamo": {
            "persona_nombre": persona,
            "moneda_id": moneda_prestamo_id,
            "monto": monto,
        },
    }
    payload["cobro_prestamo"].update(extra)
    r = client.post(f"/api/v1/cuenta/{cuenta_id}/movimiento", json=payload, headers=ADMIN_HEADERS)
    if r.status_code == 201:
        cleaner.registrar("movimiento_caja", r.json()["id"])
    return r, r.json() if r.status_code == 201 else r.text


def _prestamo(db, prestamo_id):
    return db.execute(text(
        "SELECT persona_nombre, monto, monto_abonado, estado, movimiento_caja_id "
        "FROM prestamo WHERE id = :i"
    ), {"i": prestamo_id}).fetchone()


def _saldo_prestamo(db, prestamo_id):
    return Decimal(str(db.execute(text(
        "SELECT monto - monto_abonado FROM prestamo WHERE id = :i"
    ), {"i": prestamo_id}).scalar()))


def _pendientes(client):
    r = client.get("/api/v1/prestamo/pendientes", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _gasto_id(db, prestamo_id):
    return db.execute(text(
        "SELECT g.id FROM prestamo p "
        "JOIN movimiento_caja mc ON mc.id = p.movimiento_caja_id "
        "JOIN gasto g ON mc.referencia = ('Gasto #' || g.id) "
        "WHERE p.id = :i"
    ), {"i": prestamo_id}).scalar()


# ---------------------------------------------------------------------------
# Alta del préstamo en la salida
# ---------------------------------------------------------------------------
def test_salida_prestamo_crea_la_deuda(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    r, mov, prestamo_id = _prestar(client, db, cleaner, cuenta, moneda, 100000, persona)

    assert r.status_code == 201, r.text
    assert mov["tipo"] == "SALIDA"
    assert mov["persona_entidad"] == persona
    assert prestamo_id, "la salida PRESTAMO debe crear el préstamo por cobrar"

    fila = _prestamo(db, prestamo_id)
    assert fila[0] == persona
    assert Decimal(str(fila[1])) == Decimal("100000")
    assert Decimal(str(fila[2])) == Decimal("0")
    assert fila[3] == "PENDIENTE"
    assert fila[4] == mov["id"]


def test_salida_prestamo_sin_persona_se_rechaza(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    r, _, prestamo_id = _prestar(client, db, cleaner, cuenta, moneda, 50000, "")
    assert r.status_code == 400
    assert "persona" in r.json()["detail"].lower()
    assert prestamo_id is None


def test_salida_prestamo_pago_de_deuda_propia_no_crea_deuda(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("prestamista")
    r, _, prestamo_id = _prestar(
        client, db, cleaner, cuenta, moneda, 200000, persona,
        tipo_prestamo="PAGO_DEUDA",
    )
    assert r.status_code == 201, r.text
    assert prestamo_id is None


# ---------------------------------------------------------------------------
# Cobro desde la entrada
# ---------------------------------------------------------------------------
def test_cobro_parcial_y_total_misma_moneda(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    _, _, prestamo_id = _prestar(client, db, cleaner, cuenta, moneda, 100000, persona)

    r, mov = _cobrar(client, cleaner, cuenta, moneda, persona, moneda, 40000)
    assert r.status_code == 201, r.text
    assert mov["tipo"] == "ENTRADA"
    assert Decimal(str(mov["monto"])) == Decimal("40000")
    assert _saldo_prestamo(db, prestamo_id) == Decimal("60000")
    assert _prestamo(db, prestamo_id)[3] == "PENDIENTE"

    r, mov2 = _cobrar(client, cleaner, cuenta, moneda, persona, moneda, 60000)
    assert r.status_code == 201, r.text
    assert _saldo_prestamo(db, prestamo_id) == Decimal("0")
    assert _prestamo(db, prestamo_id)[3] == "PAGADO"

    pagos = db.execute(text(
        "SELECT monto, movimiento_caja_id FROM pago_prestamo WHERE prestamo_id = :i ORDER BY id"
    ), {"i": prestamo_id}).fetchall()
    assert [Decimal(str(p[0])) for p in pagos] == [Decimal("40000"), Decimal("60000")]
    assert [p[1] for p in pagos] == [mov["id"], mov2["id"]]


def test_cobro_excede_el_saldo_se_rechaza(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    _prestar(client, db, cleaner, cuenta, moneda, 50000, persona)

    r, body = _cobrar(client, cleaner, cuenta, moneda, persona, moneda, 50001)
    assert r.status_code == 400
    assert "excede" in body.lower()


def test_cobro_sin_prestamos_se_rechaza(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    r, body = _cobrar(client, cleaner, cuenta, moneda, _uniq("nadie"), moneda, 10000)
    assert r.status_code == 400
    assert "no tiene" in body.lower()


def test_cobro_en_moneda_distinta_exige_tasa(client, db, cleaner):
    cuenta_usd, moneda_usd = _cuenta(db, cleaner, "USD")
    cuenta_cop, moneda_cop = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor_usd")
    _, _, prestamo_id = _prestar(client, db, cleaner, cuenta_usd, moneda_usd, 100, persona)

    # Sin tasa → 400
    r, body = _cobrar(client, cleaner, cuenta_cop, moneda_cop, persona, moneda_usd, 100)
    assert r.status_code == 400
    assert "tasa" in body.lower()

    # Con tasa: 1 USD = 4.000 COP → entran 400.000 COP
    r, mov = _cobrar(
        client, cleaner, cuenta_cop, moneda_cop, persona, moneda_usd, 100,
        tasa_conversion=4000,
    )
    assert r.status_code == 201, r.text
    assert mov["moneda_id"] == moneda_cop
    assert Decimal(str(mov["monto"])) == Decimal("400000")

    saldo = _saldo_prestamo(db, prestamo_id)
    assert saldo == Decimal("0")

    pago = db.execute(text(
        "SELECT moneda_cuenta_id, tasa_conversion, monto_en_moneda_cuenta "
        "FROM pago_prestamo WHERE prestamo_id = :i"
    ), {"i": prestamo_id}).fetchone()
    assert int(pago[0]) == moneda_cop
    assert Decimal(str(pago[1])) == Decimal("4000")
    assert Decimal(str(pago[2])) == Decimal("400000")


def test_cobro_fifo_entre_varios_prestamos(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor_fifo")
    _, _, primero = _prestar(client, db, cleaner, cuenta, moneda, 30000, persona)
    _, _, segundo = _prestar(client, db, cleaner, cuenta, moneda, 70000, persona)
    assert primero and segundo and primero != segundo

    r, _ = _cobrar(client, cleaner, cuenta, moneda, persona, moneda, 50000)
    assert r.status_code == 201, r.text

    # El más antiguo se cubre completo y el siguiente queda a medias.
    assert _prestamo(db, primero)[3] == "PAGADO"
    assert _saldo_prestamo(db, segundo) == Decimal("50000")


# ---------------------------------------------------------------------------
# Borrados: el saldo siempre cuadra
# ---------------------------------------------------------------------------
def test_eliminar_la_entrada_revierte_el_saldo(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    _, _, prestamo_id = _prestar(client, db, cleaner, cuenta, moneda, 80000, persona)
    r, mov = _cobrar(client, cleaner, cuenta, moneda, persona, moneda, 30000)
    assert r.status_code == 201, r.text
    assert _saldo_prestamo(db, prestamo_id) == Decimal("50000")

    r = client.delete(f"/api/v1/cuenta/movimiento/{mov['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 204, r.text
    assert _saldo_prestamo(db, prestamo_id) == Decimal("80000")
    assert _prestamo(db, prestamo_id)[3] == "PENDIENTE"
    assert db.execute(text(
        "SELECT count(*) FROM pago_prestamo WHERE prestamo_id = :i"
    ), {"i": prestamo_id}).scalar() == 0


def test_eliminar_la_salida_borra_el_prestamo(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    r, mov, prestamo_id = _prestar(client, db, cleaner, cuenta, moneda, 25000, persona)
    assert r.status_code == 201

    r = client.delete(f"/api/v1/cuenta/movimiento/{mov['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 204, r.text
    assert db.execute(text("SELECT count(*) FROM prestamo WHERE id = :i"), {"i": prestamo_id}).scalar() == 0


def test_eliminar_la_salida_con_cobros_se_bloquea(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    _, mov, prestamo_id = _prestar(client, db, cleaner, cuenta, moneda, 60000, persona)
    r, _ = _cobrar(client, cleaner, cuenta, moneda, persona, moneda, 10000)
    assert r.status_code == 201

    r = client.delete(f"/api/v1/cuenta/movimiento/{mov['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 409
    assert "cobros" in r.json()["detail"].lower()
    assert _saldo_prestamo(db, prestamo_id) == Decimal("50000")


def test_editar_la_salida_sincroniza_el_prestamo(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    _, mov, prestamo_id = _prestar(client, db, cleaner, cuenta, moneda, 40000, persona)

    nueva_persona = _uniq("renombrado")
    r = client.put(f"/api/v1/cuenta/movimiento/{mov['id']}", json={
        "monto": 70000,
        "persona_entidad": nueva_persona,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    fila = _prestamo(db, prestamo_id)
    assert fila[0] == nueva_persona
    assert Decimal(str(fila[1])) == Decimal("70000")


def test_editar_la_salida_con_cobros_se_bloquea(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    _, mov, prestamo_id = _prestar(client, db, cleaner, cuenta, moneda, 40000, persona)
    r, _ = _cobrar(client, cleaner, cuenta, moneda, persona, moneda, 10000)
    assert r.status_code == 201

    r = client.put(f"/api/v1/cuenta/movimiento/{mov['id']}", json={"monto": 90000}, headers=ADMIN_HEADERS)
    assert r.status_code == 409
    assert "cobros" in r.json()["detail"].lower()


def test_editar_solo_el_concepto_con_cobros_funciona(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    _, mov, _ = _prestar(client, db, cleaner, cuenta, moneda, 40000, persona)
    r, _ = _cobrar(client, cleaner, cuenta, moneda, persona, moneda, 10000)
    assert r.status_code == 201

    # El formulario reenvía monto/fecha aunque no cambien: solo el concepto es nuevo.
    r = client.put(f"/api/v1/cuenta/movimiento/{mov['id']}", json={
        "monto": mov["monto"],
        "fecha": mov["fecha"],
        "tipo": "SALIDA",
        "persona_entidad": persona,
        "concepto": "concepto corregido",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["concepto"] == "concepto corregido"


def test_borrar_el_gasto_desde_gastos_se_bloquea(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor")
    _, _, prestamo_id = _prestar(client, db, cleaner, cuenta, moneda, 30000, persona)
    gasto_id = _gasto_id(db, prestamo_id)
    assert gasto_id

    r = client.delete(f"/api/v1/gasto/gastos/{gasto_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 400
    assert "cuentas" in r.json()["detail"].lower()
    assert _saldo_prestamo(db, prestamo_id) == Decimal("30000")


# ---------------------------------------------------------------------------
# Consultas para la UI
# ---------------------------------------------------------------------------
def test_pendientes_y_resumen(client, db, cleaner):
    cuenta, moneda = _cuenta(db, cleaner, "COP")
    persona = _uniq("deudor_resumen")
    _prestar(client, db, cleaner, cuenta, moneda, 120000, persona)
    r, _ = _cobrar(client, cleaner, cuenta, moneda, persona, moneda, 20000)
    assert r.status_code == 201

    pendientes = _pendientes(client)
    fila = next(p for p in pendientes if p["persona_nombre"] == persona)
    assert Decimal(str(fila["saldo"])) == Decimal("100000")
    assert fila["moneda_id"] == moneda

    r = client.get("/api/v1/prestamo/resumen", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["personas_con_saldo"] >= 1
    persona_resumen = next(p for p in body["por_persona"] if p["persona_nombre"] == persona)
    assert Decimal(str(persona_resumen["saldo"])) == Decimal("100000")
    moneda_resumen = next(m for m in body["por_moneda"] if m["moneda_id"] == moneda)
    assert Decimal(str(moneda_resumen["saldo"])) >= Decimal("100000")
