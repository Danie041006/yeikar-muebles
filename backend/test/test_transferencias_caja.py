"""
test_transferencias_caja.py — Transferencias de fondos entre cuentas de caja.

Una transferencia es UNA operación contable de dos patas: SALIDA en la cuenta
origen + ENTRADA en la cuenta destino, emparejadas por `transferencia_id`.

Cubre:
- Misma moneda: el saldo se redistribuye, el total del negocio no cambia.
- Rechazos: misma cuenta, saldo insuficiente (409), cuenta inexistente.
- Multimoneda (USD → COP): la pata destino lleva el monto convertido con la
  TRM registrada; tasa indicada desviada >50% se rechaza; sin tasa se usa la
  registrada.
- Borrar una pata borra ambas (la transferencia es una sola operación).
- El resumen diario NO infla ingresos/egresos con las patas de transferencia.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_transferencias_caja.py -v
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from conftest import ADMIN_HEADERS, _uniq


# ---------------------------------------------------------------------------
# Helpers locales (registran todo en el cleaner)
# ---------------------------------------------------------------------------
def _moneda_id(db, codigo):
    row = db.execute(text("SELECT id FROM moneda WHERE codigo = :c"), {"c": codigo}).fetchone()
    return int(row[0]) if row else None


def _cuenta(db, cleaner, codigo_moneda="COP"):
    """Cuenta de caja temporal en la moneda dada (moneda_id 1 = COP)."""
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


def _fondear(client, cleaner, cuenta_id, moneda_id, monto):
    """APERTURA con referencia única para que el cleaner la borre al final."""
    ref = _uniq("fondeo")
    r = client.post(f"/api/v1/cuenta/{cuenta_id}/movimiento", json={
        "metodo_caja_id": cuenta_id,
        "fecha": str(date.today()),
        "tipo": "APERTURA",
        "monto": monto,
        "moneda_id": moneda_id,
        "referencia": ref,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"fondear → {r.status_code}: {r.text}"
    cleaner.registrar_caja_ref(ref)


def _saldo(db, cuenta_id, moneda_id):
    return Decimal(str(db.execute(text(
        "SELECT COALESCE(SUM(CASE WHEN tipo = 'SALIDA' THEN -monto ELSE monto END), 0) "
        "FROM movimiento_caja WHERE metodo_caja_id = :m AND moneda_id = :mo"
    ), {"m": cuenta_id, "mo": moneda_id}).scalar()))


def _transferir(client, origen, destino, monto, **extra):
    payload = {
        "cuenta_origen_id": origen,
        "cuenta_destino_id": destino,
        "monto": monto,
        "fecha": str(date.today()),
    }
    payload.update(extra)
    r = client.post("/api/v1/cuenta/transferencia", json=payload, headers=ADMIN_HEADERS)
    return r, (r.json() if r.status_code in (200, 201) else {})


def _borrar_transferencia(client, body):
    """Borra la transferencia por una pata (endpoint en cascada) y devuelve el status."""
    r = client.delete(f"/api/v1/cuenta/movimiento/{body['pata_salida']['id']}", headers=ADMIN_HEADERS)
    return r.status_code


def _tasa_registrada(db, moneda_id, fecha):
    """La misma resolución que usa el service: última ≤ fecha, si no la más próxima."""
    row = db.execute(text(
        "SELECT valor FROM tasa_cambio WHERE moneda_origen_id = :o AND moneda_destino_id = 1 "
        "AND fecha <= :f ORDER BY fecha DESC LIMIT 1"
    ), {"o": moneda_id, "f": fecha}).fetchone()
    if row is None:
        row = db.execute(text(
            "SELECT valor FROM tasa_cambio WHERE moneda_origen_id = :o AND moneda_destino_id = 1 "
            "ORDER BY fecha ASC LIMIT 1"
        ), {"o": moneda_id}).fetchone()
    return Decimal(str(row[0])) if row else None


def _registrar_tasa(db, cleaner, moneda_id, valor, fecha):
    r = db.execute(text(
        "INSERT INTO tasa_cambio (moneda_origen_id, moneda_destino_id, valor, fecha) "
        "VALUES (:o, 1, :v, :f) RETURNING id"
    ), {"o": moneda_id, "v": valor, "f": fecha}).fetchone()
    db.commit()
    cleaner.registrar("tasa_cambio", r[0])


# ---------------------------------------------------------------------------
# Misma moneda
# ---------------------------------------------------------------------------
def test_transferencia_misma_moneda_moviliza_saldo(client, cleaner, db):
    origen, mo = _cuenta(db, cleaner)
    destino, _ = _cuenta(db, cleaner)
    _fondear(client, cleaner, origen, mo, 100000)

    r, body = _transferir(client, origen, destino, 40000)
    assert r.status_code == 201, f"transferir → {r.status_code}: {r.text}"
    try:
        assert Decimal(str(body["monto_salida"])) == Decimal("40000")
        assert Decimal(str(body["monto_entrada"])) == Decimal("40000")
        assert body["pata_salida"]["tipo"] == "SALIDA" and body["pata_entrada"]["tipo"] == "ENTRADA"
        assert body["pata_salida"]["metodo_caja_id"] == origen
        assert body["pata_entrada"]["metodo_caja_id"] == destino
        tid = body["transferencia_id"]
        assert body["pata_salida"]["transferencia_id"] == tid
        assert body["pata_entrada"]["transferencia_id"] == tid

        assert _saldo(db, origen, mo) == Decimal("60000")
        assert _saldo(db, destino, mo) == Decimal("40000")
    finally:
        # Borrar una pata borra ambas y el saldo vuelve a su lugar.
        assert _borrar_transferencia(client, body) == 204
        n = db.execute(text(
            "SELECT COUNT(*) FROM movimiento_caja WHERE transferencia_id = :t"
        ), {"t": body["transferencia_id"]}).scalar()
        assert n == 0
        assert _saldo(db, origen, mo) == Decimal("100000")
        assert _saldo(db, destino, mo) == Decimal("0")


def test_transferencia_aparece_en_listado(client, cleaner, db):
    origen, mo = _cuenta(db, cleaner)
    destino, _ = _cuenta(db, cleaner)
    _fondear(client, cleaner, origen, mo, 5000)
    r, body = _transferir(client, origen, destino, 2500)
    assert r.status_code == 201, r.text
    try:
        lst = client.get("/api/v1/cuenta/transferencias", headers=ADMIN_HEADERS)
        assert lst.status_code == 200, lst.text
        assert any(t["transferencia_id"] == body["transferencia_id"] for t in lst.json())
    finally:
        _borrar_transferencia(client, body)


def test_transferencia_misma_cuenta_rechazada(client, cleaner, db):
    origen, mo = _cuenta(db, cleaner)
    r, _ = _transferir(client, origen, origen, 1000)
    assert r.status_code == 400, r.text
    assert "distintas" in r.text.lower()


def test_transferencia_cuenta_inexistente_rechazada(client, cleaner, db):
    origen, mo = _cuenta(db, cleaner)
    r, _ = _transferir(client, origen, 99999999, 1000)
    assert r.status_code == 400, r.text


def test_transferencia_saldo_insuficiente_409(client, cleaner, db):
    origen, mo = _cuenta(db, cleaner)
    destino, _ = _cuenta(db, cleaner)
    _fondear(client, cleaner, origen, mo, 10000)
    r, _ = _transferir(client, origen, destino, 50000)
    assert r.status_code == 409, f"esperaba 409 → {r.status_code}: {r.text}"
    assert "saldo insuficiente" in r.text.lower()


def test_transferencia_monto_cero_rechazado(client, cleaner, db):
    origen, mo = _cuenta(db, cleaner)
    destino, _ = _cuenta(db, cleaner)
    r, _ = _transferir(client, origen, destino, 0)
    assert r.status_code == 422, r.text  # pydantic: monto gt=0


# ---------------------------------------------------------------------------
# Multimoneda
# ---------------------------------------------------------------------------
def test_transferencia_usd_a_cop_con_tasa_indicada(client, cleaner, db):
    origen, mo_usd = _cuenta(db, cleaner, "USD")
    destino, mo_cop = _cuenta(db, cleaner, "COP")
    _fondear(client, cleaner, origen, mo_usd, 100)

    tasa = _tasa_registrada(db, mo_usd, date.today()) or Decimal("4000")
    if _tasa_registrada(db, mo_usd, date.today()) is None:
        _registrar_tasa(db, cleaner, mo_usd, 4000, date.today())
        tasa = Decimal("4000")

    r, body = _transferir(client, origen, destino, 50, tasa_cambio=float(tasa))
    assert r.status_code == 201, f"transferir → {r.status_code}: {r.text}"
    assert body["moneda_salida_codigo"] == "USD" and body["moneda_entrada_codigo"] == "COP"
    monto_entrada = (Decimal("50") * tasa).quantize(Decimal("0.01"))
    assert Decimal(str(body["monto_entrada"])) == monto_entrada

    assert _saldo(db, origen, mo_usd) == Decimal("50")
    assert _saldo(db, destino, mo_cop) == monto_entrada

    assert _borrar_transferencia(client, body) == 204
    assert _saldo(db, origen, mo_usd) == Decimal("100")


def test_transferencia_usd_a_cop_sin_tasa_usa_registrada(client, cleaner, db):
    origen, mo_usd = _cuenta(db, cleaner, "USD")
    destino, mo_cop = _cuenta(db, cleaner, "COP")
    _fondear(client, cleaner, origen, mo_usd, 10)

    if _tasa_registrada(db, mo_usd, date.today()) is None:
        _registrar_tasa(db, cleaner, mo_usd, 4000, date.today())
    tasa = _tasa_registrada(db, mo_usd, date.today())

    r, body = _transferir(client, origen, destino, 10)  # sin tasa_cambio
    assert r.status_code == 201, f"transferir → {r.status_code}: {r.text}"
    esperado = (Decimal("10") * tasa).quantize(Decimal("0.01"))
    assert Decimal(str(body["monto_entrada"])) == esperado
    assert Decimal(str(body["pata_entrada"]["monto"])) == esperado
    _borrar_transferencia(client, body)


def test_transferencia_tasa_desviada_rechazada(client, cleaner, db):
    origen, mo_usd = _cuenta(db, cleaner, "USD")
    destino, _ = _cuenta(db, cleaner, "COP")
    _fondear(client, cleaner, origen, mo_usd, 100)

    if _tasa_registrada(db, mo_usd, date.today()) is None:
        _registrar_tasa(db, cleaner, mo_usd, 4000, date.today())
    tasa = _tasa_registrada(db, mo_usd, date.today())
    assert tasa is not None, "se necesitaba una tasa registrada"

    r, _ = _transferir(client, origen, destino, 10, tasa_cambio=float(tasa * 3))
    assert r.status_code == 400, f"esperaba 400 por TRM inventada → {r.status_code}: {r.text}"
    assert "50%" in r.text


def test_tasa_transferencia_prellenado_entre_monedas(client, cleaner, db):
    """El endpoint que prellena el formulario devuelve destino por origen."""
    cop, _ = _cuenta(db, cleaner, "COP")
    usd, mo_usd = _cuenta(db, cleaner, "USD")
    if _tasa_registrada(db, mo_usd, date.today()) is None:
        _registrar_tasa(db, cleaner, mo_usd, 4000, date.today())
    tasa = _tasa_registrada(db, mo_usd, date.today())

    r = client.get(
        "/api/v1/cuenta/tasa-transferencia",
        params={
            "cuenta_origen_id": cop,
            "cuenta_destino_id": usd,
            "fecha": str(date.today()),
        },
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"tasa-transferencia → {r.status_code}: {r.text}"
    body = r.json()
    assert body["monedas_distintas"] is True
    esperada = (Decimal("1") / tasa).quantize(Decimal("0.000001"))
    assert Decimal(str(body["tasa_conversion"])) == esperada
    assert Decimal(str(body["tasa_origen_cop"])) == Decimal("1")
    assert Decimal(str(body["tasa_destino_cop"])) == tasa

    # Misma moneda: la tasa es 1.
    cop2, _ = _cuenta(db, cleaner, "COP")
    r = client.get(
        "/api/v1/cuenta/tasa-transferencia",
        params={"cuenta_origen_id": cop, "cuenta_destino_id": cop2},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["tasa_conversion"])) == Decimal("1")


def test_transferencia_cop_a_usd_con_tasa_editable(client, cleaner, db):
    """2.000.000 COP a 4.000 son 500 USD, no 200.000 USD."""
    origen, mo_cop = _cuenta(db, cleaner, "COP")
    destino, mo_usd = _cuenta(db, cleaner, "USD")
    _fondear(client, cleaner, origen, mo_cop, 2000000)

    if _tasa_registrada(db, mo_usd, date.today()) is None:
        _registrar_tasa(db, cleaner, mo_usd, 4000, date.today())
    tasa = _tasa_registrada(db, mo_usd, date.today())
    tasa_conversion = (Decimal("1") / tasa).quantize(Decimal("0.000001"))

    r, body = _transferir(
        client, origen, destino, 2000000, tasa_conversion=float(tasa_conversion)
    )
    assert r.status_code == 201, f"transferir → {r.status_code}: {r.text}"
    try:
        esperado = (Decimal("2000000") * tasa_conversion).quantize(Decimal("0.01"))
        tasa_implicita = (Decimal("2000000") / esperado).quantize(Decimal("0.000001"))
        assert Decimal(str(body["tasa_conversion"])) == tasa_conversion
        assert Decimal(str(body["monto_convertido"])) == esperado
        assert Decimal(str(body["monto_entrada"])) == esperado
        assert Decimal(str(body["pata_entrada"]["tasa_cambio"])) == tasa_implicita
        assert Decimal(str(body["pata_entrada"]["monto"])) == esperado

        assert _saldo(db, origen, mo_cop) == Decimal("0")
        assert _saldo(db, destino, mo_usd) == esperado
    finally:
        assert _borrar_transferencia(client, body) == 204
        assert _saldo(db, origen, mo_cop) == Decimal("2000000")


def test_transferencia_tasa_conversion_desviada_rechazada(client, cleaner, db):
    """La tasa manual conserva el guardia de ±50% contra la TRM registrada."""
    origen, mo_cop = _cuenta(db, cleaner, "COP")
    destino, mo_usd = _cuenta(db, cleaner, "USD")
    _fondear(client, cleaner, origen, mo_cop, 2000000)

    if _tasa_registrada(db, mo_usd, date.today()) is None:
        _registrar_tasa(db, cleaner, mo_usd, 4000, date.today())
    tasa = _tasa_registrada(db, mo_usd, date.today())
    # 1 USD = 1.600 COP: 60% por debajo de la TRM registrada.
    tasa_inventada = (Decimal("1") / (tasa * Decimal("0.4"))).quantize(Decimal("0.000001"))

    r, _ = _transferir(
        client, origen, destino, 2000000, tasa_conversion=float(tasa_inventada)
    )
    assert r.status_code == 400, f"esperaba 400 por tasa inventada → {r.status_code}: {r.text}"
    assert "50%" in r.text


def test_transferencia_usd_a_usd_valoriza_en_cop(client, cleaner, db):
    """Misma moneda extranjera: la tasa → COP solo valoriza la pata en base."""
    origen, mo_usd = _cuenta(db, cleaner, "USD")
    destino, mo_usd_destino = _cuenta(db, cleaner, "USD")
    _fondear(client, cleaner, origen, mo_usd, 100)

    if _tasa_registrada(db, mo_usd, date.today()) is None:
        _registrar_tasa(db, cleaner, mo_usd, 4000, date.today())
    tasa = _tasa_registrada(db, mo_usd, date.today())

    r, body = _transferir(client, origen, destino, 10, tasa_cambio=float(tasa))
    assert r.status_code == 201, f"transferir → {r.status_code}: {r.text}"
    try:
        assert Decimal(str(body["monto_entrada"])) == Decimal("10")
        assert Decimal(str(body["pata_salida"]["monto_en_moneda_base"])) == (Decimal("10") * tasa)
        assert Decimal(str(body["pata_entrada"]["monto_en_moneda_base"])) == (Decimal("10") * tasa)
        assert _saldo(db, destino, mo_usd_destino) == Decimal("10")
    finally:
        _borrar_transferencia(client, body)


def test_transferencia_interes_suma_y_resta(client, cleaner, db):
    """El interés (en moneda destino) ajusta lo que entra, con signo explícito."""
    origen, mo = _cuenta(db, cleaner)
    destino, _ = _cuenta(db, cleaner)
    _fondear(client, cleaner, origen, mo, 100000)

    # RESTA: llegan 9.500 de 10.000.
    r, resta = _transferir(
        client, origen, destino, 10000,
        interes=500, interes_signo="RESTA", persona_entidad="Prestamista XYZ",
    )
    assert r.status_code == 201, f"transferir → {r.status_code}: {r.text}"
    try:
        assert Decimal(str(resta["monto_convertido"])) == Decimal("10000")
        assert Decimal(str(resta["monto_entrada"])) == Decimal("9500")
        assert Decimal(str(resta["interes"])) == Decimal("500")
        assert resta["interes_signo"] == "RESTA"
        assert resta["persona_entidad"] == "Prestamista XYZ"
        assert resta["pata_salida"]["persona_entidad"] == "Prestamista XYZ"
        assert resta["pata_entrada"]["persona_entidad"] == "Prestamista XYZ"
        assert Decimal(str(resta["pata_entrada"]["interes"])) == Decimal("-500")
        assert _saldo(db, origen, mo) == Decimal("90000")
        assert _saldo(db, destino, mo) == Decimal("9500")
    finally:
        _borrar_transferencia(client, resta)

    # SUMA: llegan 10.500 de 10.000.
    r, suma = _transferir(
        client, origen, destino, 10000,
        interes=500, interes_signo="SUMA", persona_entidad="Tercero ABC",
    )
    assert r.status_code == 201, f"transferir → {r.status_code}: {r.text}"
    try:
        assert Decimal(str(suma["monto_entrada"])) == Decimal("10500")
        assert suma["interes_signo"] == "SUMA"
        assert Decimal(str(suma["pata_entrada"]["interes"])) == Decimal("500")
        assert _saldo(db, origen, mo) == Decimal("90000")
        assert _saldo(db, destino, mo) == Decimal("10500")
    finally:
        _borrar_transferencia(client, suma)


def test_transferencia_interes_no_puede_dejar_entrada_en_cero(client, cleaner, db):
    origen, mo = _cuenta(db, cleaner)
    destino, _ = _cuenta(db, cleaner)
    _fondear(client, cleaner, origen, mo, 10000)

    r, _ = _transferir(
        client, origen, destino, 1000, interes=1000, interes_signo="RESTA"
    )
    assert r.status_code == 400, f"esperaba 400 → {r.status_code}: {r.text}"
    assert "cero o negativo" in r.text.lower()


# ---------------------------------------------------------------------------
# Integración con reportes
# ---------------------------------------------------------------------------
def test_resumen_diario_no_infla_transferencia(client, cleaner, db):
    """Las patas de la transferencia se LISTAN en el estado del día pero no
    suman a total_ingresos ni total_egresos; el saldo final sí se mueve 1:1
    (misma moneda ⇒ neutro en COP)."""
    origen, mo = _cuenta(db, cleaner)
    destino, _ = _cuenta(db, cleaner)
    _fondear(client, cleaner, origen, mo, 80000)

    def _diario():
        rr = client.get("/api/v1/reports/diario", headers=ADMIN_HEADERS)
        assert rr.status_code == 200, f"GET /reports/diario → {rr.status_code}: {rr.text}"
        return rr.json()

    antes = _diario()
    r, body = _transferir(client, origen, destino, 30000)
    assert r.status_code == 201, r.text
    try:
        despues = _diario()
        assert Decimal(str(despues["total_ingresos_cop"])) == Decimal(str(antes["total_ingresos_cop"]))
        assert Decimal(str(despues["total_egresos_cop"])) == Decimal(str(antes["total_egresos_cop"]))

        patas = [m for m in despues["movimientos"] if (m["referencia"] or "").startswith(f"Transferencia #T{body['transferencia_id']}")]
        assert len(patas) == 2, f"esperaba las 2 patas listadas, hubo {len(patas)}"
        assert all(m["concepto"] == "Transferencia entre cuentas" for m in patas)
    finally:
        _borrar_transferencia(client, body)
