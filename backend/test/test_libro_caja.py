# -*- coding: utf-8 -*-
"""
test_libro_caja.py — Importación del libro de efectivo COP.

Caso real: el negocio lleva el mes en una hoja (fecha, tipo, concepto,
ingreso, egreso, saldo) y marca cada gasto con G D / G C / G P / G F / G I
(Gasto Deducible, de Casa, Personal, Familiar o de Inversión). La importación:

  - crea un movimiento de caja por cada fila (según el cambio de saldo),
  - crea un Gasto clasificado por cada egreso con código G,
  - deja el saldo inicial como APERTURA solo si se pide,
  - rechaza importar dos veces el mismo período,
  - se puede deshacer por período.

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_libro_caja.py -v
"""
from decimal import Decimal
import uuid

from app.modules.gastos.model import Gasto
from app.modules.reports.model import MovimientoCaja
from conftest import ADMIN_HEADERS

LIBRO = "\n".join([
    "FECHA\tTIPO\tCONCEPTO\tINGRESO\tEGRESO\tSALDO",
    "10/1/2026\tSALDO\tMES DE SEPTIEMBRE\t\t\t$ 3,683,600",
    "10/1/2026\tDOÑA ROSA G C\tPAGO DE MERCADO\t\t$ 120,000\t$ 3,563,600",
    "10/1/2026\tCAMARA DE COMERCIO G F\tPAGO DE LUZ\t\t$ 400,000\t$ 3,163,600",
    "10/1/2026\tRAFAEL\tVUELTOS DE LAS COMPRAS\t$ 100,000\t\t$ 3,263,600",
    "10/1/2026\tJACKSON GP\tPROTECCION CIVIL\t\t$ 50,000\t$ 3,213,600",
    "10/2/2026\tGASTO VARIOS\tCOMPRA DE VASOS\t\t$ 20,000\t$ 3,193,600",
    "10/2/2026\tALCALDIA G I\tPAGO DE AGUA\t\t$ 30,000\t$ 3,163,600",
])


def _crear_cuenta(client, cleaner, db, codigo=None):
    codigo = codigo or f"TEST_LIBRO_{uuid.uuid4().hex[:6].upper()}"
    r = client.post("/api/v1/cuenta/", json={
        "nombre": "Cuenta de prueba libro",
        "codigo": codigo,
        "moneda_id": 1,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cuenta = r.json()
    cleaner.registrar("metodo_caja", cuenta["id"])
    # Al crear una cuenta COP el sistema le pone una apertura por defecto de
    # 1.000.000; para probar el libro desde cero se elimina.
    db.query(MovimientoCaja).filter(
        MovimientoCaja.metodo_caja_id == cuenta["id"],
        MovimientoCaja.referencia == "Saldo inicial por defecto",
    ).delete(synchronize_session=False)
    db.commit()
    return cuenta


def _payload(cuenta_id, **extra):
    data = {"texto": LIBRO, "metodo_caja_id": cuenta_id}
    data.update(extra)
    return data


def test_preview_e_importacion_del_libro(client, cleaner, db):
    cuenta = _crear_cuenta(client, cleaner, db)

    # 1. Vista previa: no escribe nada.
    r = client.post("/api/v1/cuenta/libro/preview", json=_payload(cuenta["id"]), headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    prev = r.json()
    assert prev["periodo"] == "2026-10"
    assert prev["filas"] == 7
    assert prev["movimientos"] == 6
    assert prev["gastos"] == 4
    assert Decimal(str(prev["saldo_inicial"])) == Decimal("3683600")
    assert Decimal(str(prev["saldo_final"])) == Decimal("3163600")
    assert Decimal(str(prev["total_ingresos"])) == Decimal("100000")
    assert Decimal(str(prev["total_egresos"])) == Decimal("620000")
    assert Decimal(str(prev["diferencia_saldo_inicial"])) == Decimal("3683600")
    consultados = db.query(MovimientoCaja).filter(
        MovimientoCaja.metodo_caja_id == cuenta["id"]
    ).count()
    assert consultados == 0, "la vista previa no debe escribir movimientos"

    # 2. Importar cuadrando el saldo inicial (la cuenta de prueba nace en 0).
    r = client.post(
        "/api/v1/cuenta/libro/importar",
        json=_payload(cuenta["id"], cuadrar_saldo_inicial=True),
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    res = r.json()

    db.expire_all()
    movs = db.query(MovimientoCaja).filter(
        MovimientoCaja.metodo_caja_id == cuenta["id"]
    ).all()
    for mov in movs:
        cleaner.registrar("movimiento_caja", mov.id)
    tag = f"Libro {cuenta['codigo']} 2026-10"
    gastos = db.query(Gasto).filter(Gasto.observaciones.like(f"[{tag}]%")).all()
    for gasto in gastos:
        cleaner.registrar("gasto", gasto.id)

    assert res["movimientos"] == 7
    assert res["gastos"] == 4

    assert len(movs) == 7
    saldo = sum(
        (-Decimal(str(m.monto)) if m.tipo == "SALIDA" else Decimal(str(m.monto)))
        for m in movs
    )
    assert saldo == Decimal("3163600"), f"saldo final {saldo}"

    assert len(gastos) == 4
    assert {g.clasificacion for g in gastos} == {
        "GASTO_CASA", "GASTO_FAMILIAR", "GASTO_PERSONAL", "GASTO_INVERSION",
    }
    # Los cuatro gastos descontaron la cuenta: la suma de sus montos es 600.000.
    assert sum(Decimal(str(g.monto)) for g in gastos) == Decimal("600000")

    # 2b. El libro se ve como la hoja: tipo, concepto y saldo corrido.
    r = client.get("/api/v1/cuenta/libro", params={
        "metodo_caja_id": cuenta["id"],
        "fecha_desde": "2026-10-01",
        "fecha_hasta": "2026-10-31",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    libro = r.json()
    assert Decimal(str(libro["saldo_inicial"])) == Decimal("0")
    assert Decimal(str(libro["saldo_final"])) == Decimal("3163600")
    assert len(libro["filas"]) == 7
    primera = libro["filas"][0]
    assert primera["tipo"] == "APERTURA"
    assert "Ajuste para cuadrar" in primera["concepto"]
    assert Decimal(str(primera["saldo"])) == Decimal("3683600")
    segunda = libro["filas"][1]
    assert segunda["persona_entidad"] == "DOÑA ROSA G C"
    assert segunda["tipo"] == "DOÑA ROSA G C"
    assert segunda["concepto"] == "PAGO DE MERCADO"
    assert segunda["clasificacion"] == "GASTO_CASA"
    assert segunda["tipo_movimiento"] == "SALIDA"
    assert Decimal(str(segunda["saldo"])) == Decimal("3563600")

    # 3. No se puede importar dos veces el mismo período.
    r = client.post(
        "/api/v1/cuenta/libro/importar",
        json=_payload(cuenta["id"], cuadrar_saldo_inicial=True),
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400
    assert "ya fue importado" in r.json()["detail"].lower()

    # 4. Deshacer deja la cuenta limpia.
    r = client.delete(
        f"/api/v1/cuenta/libro/2026-10",
        params={"metodo_caja_id": cuenta["id"]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    assert r.json()["gastos_borrados"] == 4
    assert r.json()["movimientos_borrados"] == 3  # apertura + 2 movimientos sin G
    db.expire_all()
    assert db.query(MovimientoCaja).filter(
        MovimientoCaja.metodo_caja_id == cuenta["id"]
    ).count() == 0
    assert db.query(Gasto).filter(Gasto.observaciones.like(f"[{tag}]%")).count() == 0


def test_omitir_duplicados_que_ya_estan_en_la_cuenta(client, cleaner, db):
    """Una venta ya cobrada en el ERP no se duplica al importar el libro."""
    cuenta = _crear_cuenta(client, cleaner, db)
    # Movimiento preexistente: el cobro de 100.000 del 1/10 ya está en caja.
    r = client.post(f"/api/v1/cuenta/{cuenta['id']}/movimiento", json={
        "metodo_caja_id": cuenta["id"],
        "fecha": "2026-10-01",
        "tipo": "ENTRADA",
        "monto": 100000,
        "moneda_id": 1,
        "tasa_cambio": 1,
        "referencia": "Cobro de RAFAEL · Venta de prueba",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cleaner.registrar("movimiento_caja", r.json()["id"])

    r = client.post("/api/v1/cuenta/libro/preview", json=_payload(cuenta["id"]), headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    prev = r.json()
    assert prev["duplicados"] == 1, prev
    duplicado = next(f for f in prev["filas_detalle"] if f["duplicado_de"])
    assert duplicado["linea"] == 5  # la fila de los vueltos de las compras

    r = client.post(
        "/api/v1/cuenta/libro/importar",
        json=_payload(cuenta["id"], cuadrar_saldo_inicial=True, omitir_duplicados=True),
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["omitidos"] == 1
    assert res["movimientos"] == 6  # ajuste + 2 sin G + 4 gastos, sin el ingreso duplicado

    db.expire_all()
    movs = db.query(MovimientoCaja).filter(
        MovimientoCaja.metodo_caja_id == cuenta["id"]
    ).all()
    for mov in movs:
        cleaner.registrar("movimiento_caja", mov.id)
    tag = f"Libro {cuenta['codigo']} 2026-10"
    for gasto in db.query(Gasto).filter(Gasto.observaciones.like(f"[{tag}]%")).all():
        cleaner.registrar("gasto", gasto.id)
    saldo = sum(
        (-Decimal(str(m.monto)) if m.tipo == "SALIDA" else Decimal(str(m.monto)))
        for m in movs
    )
    # El cobro preexistente + el ajuste de cuadre + el libro sin el duplicado
    # dejan la cuenta exactamente en el saldo final del libro.
    assert saldo == Decimal("3163600"), f"saldo final {saldo}"

    # Limpieza explícita de la importación (el cleaner también borra los ids).
    client.delete(
        "/api/v1/cuenta/libro/2026-10",
        params={"metodo_caja_id": cuenta["id"]},
        headers=ADMIN_HEADERS,
    )


def test_clasificacion_del_gasto_es_opcional_y_explicita(client, cleaner):
    # Se crea sin clasificación (opcional) y luego se le pone "G F".
    r = client.post("/api/v1/gasto/gastos/", json={
        "tipo_gasto_id": 1,
        "moneda_id": 1,
        "fecha": "2026-10-20",
        "descripcion": "test clasificacion opcional",
        "monto": 1000,
        "clasificacion": None,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    gasto = r.json()
    cleaner.registrar("gasto", gasto["id"])
    assert gasto["clasificacion"] is None

    r = client.put(f"/api/v1/gasto/gastos/{gasto['id']}", json={
        "clasificacion": "G F",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["clasificacion"] == "GASTO_FAMILIAR"

    r = client.get("/api/v1/gasto/gastos/", params={
        "clasificacion": "GASTO_FAMILIAR",
        "fecha_desde": "2026-10-20",
        "fecha_hasta": "2026-10-20",
        "limit": 500,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert any(g["id"] == gasto["id"] for g in r.json())

    # Se puede volver a dejar sin clasificación.
    r = client.put(f"/api/v1/gasto/gastos/{gasto['id']}", json={
        "clasificacion": None,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["clasificacion"] is None


def test_fechas_mezcladas_y_gf_es_gasto_familiar():
    """El libro mezcla 10/1/2026 (M/D) y 1/10/2026 (D/M): manda el mes del período."""
    from app.modules.reports.libro_caja import parsear_libro

    texto = "\n".join([
        "10/1/2026\tSALDO\tMES DE SEPTIEMBRE\t\t\t$ 1,000,000",
        "10/1/2026\tDOÑA ROSA G F\tMERCADO\t\t$ 100,000\t$ 900,000",
        "1/10/202\tCAMARA G C\tLUZ\t\t$ 50,000\t$ 850,000",
        "6/10/226\tJACKSON GP\tSACO\t\t$ 25,000\t$ 825,000",
    ])
    parsed = parsear_libro(texto)
    assert parsed.periodo == "2026-10"
    assert [f.fecha.isoformat() for f in parsed.filas] == [
        "2026-10-01", "2026-10-01", "2026-10-01", "2026-10-06",
    ]
    assert [f.clasificacion for f in parsed.filas] == [
        None, "GASTO_FAMILIAR", "GASTO_CASA", "GASTO_PERSONAL",
    ]


def test_tipo_solo_sin_concepto_y_tipo_con_concepto():
    """El TIPO no se debe perder cuando la fila no trae CONCEPTO."""
    from app.modules.reports.libro_caja import parsear_libro

    texto = "\n".join([
        "10/1/2026\tSALDO\tMES DE SEPTIEMBRE\t\t\t$ 1,000,000",
        "10/1/2026\tQUESILLO GP\t\t\t$ 12,000\t$ 988,000",
        "10/1/2026\tDOÑA ROSA G C\tPAGO DE MERCADO\t\t$ 100,000\t$ 888,000",
    ])
    parsed = parsear_libro(texto)
    assert parsed.filas[1].tipo == "QUESILLO GP"
    assert parsed.filas[1].concepto == ""
    assert parsed.filas[2].tipo == "DOÑA ROSA G C"
    assert parsed.filas[2].concepto == "PAGO DE MERCADO"


def test_vista_conserva_tipo_sin_concepto():
    """La vista no debe convertir el TIPO en 'GASTO' cuando no hay CONCEPTO."""
    from app.modules.reports.libro_caja import _tipo_concepto_movimiento

    class Mov:
        concepto = "[Libro EFECTIVO_COP 2026-10] QUESILLO GP · "
        persona_entidad = None
        tipo = "SALIDA"
        pago_id = None
        transferencia_id = None
        referencia = "Gasto #180"

    tipo, concepto = _tipo_concepto_movimiento(Mov(), None)
    assert tipo == "QUESILLO GP"
    assert concepto == ""


def test_movimiento_manual_persona_concepto_sin_tasa_ni_referencia(client, cleaner, db):
    """El formulario de caja ya no pide tasa ni referencia; sí persona/concepto."""
    cuenta = _crear_cuenta(client, cleaner, db)
    r = client.post(f"/api/v1/cuenta/{cuenta['id']}/movimiento", json={
        "metodo_caja_id": cuenta["id"],
        "fecha": "2026-10-05",
        "tipo": "ENTRADA",
        "monto": 50000,
        "moneda_id": 1,
        "persona_entidad": "CLIENTE DE PRUEBA",
        "concepto": "Abono de prueba",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    mov = r.json()
    cleaner.registrar("movimiento_caja", mov["id"])
    assert mov["persona_entidad"] == "CLIENTE DE PRUEBA"
    assert mov["concepto"] == "Abono de prueba"
    assert mov["referencia"] is None
    assert Decimal(str(mov["tasa_cambio"])) == Decimal("1")

    r = client.put(f"/api/v1/cuenta/movimiento/{mov['id']}", json={
        "persona_entidad": "OTRO CLIENTE",
        "concepto": "Abono corregido",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["persona_entidad"] == "OTRO CLIENTE"
    assert r.json()["concepto"] == "Abono corregido"


def test_clasificacion_invalida_se_rechaza(client, cleaner):
    r = client.post("/api/v1/gasto/gastos/", json={
        "tipo_gasto_id": 1,
        "moneda_id": 1,
        "fecha": "2026-10-20",
        "descripcion": "test clasificacion invalida",
        "monto": 1000,
        "clasificacion": "G X",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "clasificación inválida" in r.json()["detail"].lower()


def test_libro_en_la_moneda_de_la_cuenta_usd(client, cleaner, db):
    """El libro se importa en la moneda de la cuenta (no solo COP).

    Caso real: el libro de "Efectivo en Dólares" (USD). Cada movimiento y
    gasto queda en la moneda de la cuenta con la tasa del día hacia COP
    (1.0 si nunca se registró tasa para esa moneda).
    """
    from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop

    r = client.post("/api/v1/cuenta/", json={
        "nombre": "Cuenta USD de prueba libro",
        "codigo": f"TEST_LIBRO_USD_{uuid.uuid4().hex[:6].upper()}",
        "moneda_id": 2,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cuenta = r.json()
    cleaner.registrar("metodo_caja", cuenta["id"])
    db.query(MovimientoCaja).filter(
        MovimientoCaja.metodo_caja_id == cuenta["id"],
        MovimientoCaja.referencia == "Saldo inicial por defecto",
    ).delete(synchronize_session=False)
    db.commit()

    # Preview: misma aritmética que en COP, pero para la cuenta en USD.
    r = client.post("/api/v1/cuenta/libro/preview", json=_payload(cuenta["id"]), headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    prev = r.json()
    assert prev["periodo"] == "2026-10"
    assert prev["filas"] == 7
    assert Decimal(str(prev["saldo_final"])) == Decimal("3163600")

    r = client.post(
        "/api/v1/cuenta/libro/importar",
        json=_payload(cuenta["id"], cuadrar_saldo_inicial=True),
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text

    db.expire_all()
    movs = db.query(MovimientoCaja).filter(
        MovimientoCaja.metodo_caja_id == cuenta["id"]
    ).all()
    for mov in movs:
        cleaner.registrar("movimiento_caja", mov.id)
    tag = f"Libro {cuenta['codigo']} 2026-10"
    gastos = db.query(Gasto).filter(Gasto.observaciones.like(f"[{tag}]%")).all()
    for gasto in gastos:
        cleaner.registrar("gasto", gasto.id)

    assert len(movs) == 7
    assert all(m.moneda_id == 2 for m in movs), "los movimientos quedan en USD"
    for m in movs:
        esperada = obtener_tasa_moneda_a_cop(db, 2, m.fecha)
        assert Decimal(str(m.tasa_cambio)) == esperada
        assert Decimal(str(m.monto_en_moneda_base)) == (
            Decimal(str(m.monto)) * esperada
        )

    assert len(gastos) == 4
    assert all(g.moneda_id == 2 for g in gastos), "los gastos quedan en USD"
    for g in gastos:
        esperada = obtener_tasa_moneda_a_cop(db, 2, g.fecha)
        assert Decimal(str(g.tasa_cambio)) == esperada
        assert Decimal(str(g.monto_en_moneda_base)) == (
            Decimal(str(g.monto)) * esperada
        )

    # El saldo de la cuenta queda exactamente al del libro.
    saldo = sum(
        (-Decimal(str(m.monto)) if m.tipo == "SALIDA" else Decimal(str(m.monto)))
        for m in movs
    )
    assert saldo == Decimal("3163600"), f"saldo final {saldo}"
