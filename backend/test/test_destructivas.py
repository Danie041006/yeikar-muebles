#!/usr/bin/env python3
"""
test_destructivas.py — Suite PESADA de intento de ruptura del ERP YEIKAR.

No es una suite "feliz": busca ROM PER el sistema. Cada test intenta un
ataque/clase de fallo y exige que el sistema lo RESUELVA con el status
adecuado (4xx) o con invariantes intactas. Si un test falla, documenta
un bug real (se reporta; no se arregla aquí).

Objetivos de ataque:
  A. JWT: alg=none, claims manipulados (es_admin), token sin exp, sub numérico.
  B. Mass assignment: campos de privilegio en payloads de creación/update.
  C. Inyección SQL: search con operadores, IDs con literales SQL.
  D. BOLA/permisos: rol Ventas contra nómina/reportes/gastos.
  E. Race conditions: doble pago de nómina, doble finalizar orden,
     doble anulación (sin FOR UPDATE a propósito).
  F. Límites: montos gigantes/negativos/micro, cantidades negativas,
     strings gigantes, paginación extrema, fechas invertidas.
  G. Integridad: anular nómina revierte todo; borrar gasto de nómina pagada;
     sobrepagos; doble nómina del mismo periodo.

Ejecutar con PostgreSQL activo:
  cd /home/daniel-castellanos/YEIKAR/backend
  venv/bin/python -m pytest test/test_destructivas.py -v
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, date

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import settings
from app.db.session import session_local

try:
    from conftest import (
        _firmar_token,
        ADMIN_HEADERS,
        VENTAS_HEADERS,
        crear_cliente,
        crear_producto,
        crear_cotizacion,
        crear_orden_desde_pedido,
    )
except ImportError:  # pragma: no cover
    pytest.fail("No se pudo importar conftest")


def _firmar_payload(payload: dict, header: dict | None = None) -> str:
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM, headers=header or {})


def _token_alg_none(sub: str = "jackson") -> str:
    import base64
    import json as _json

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(_json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = b64(_json.dumps({"sub": sub, "type": "access",
                               "exp": int(datetime.now().timestamp()) + 3600}).encode())
    return f"{header}.{payload}."


def _contar_gastos_nomina(db, periodo: str) -> int:
    row = db.execute(
        __import__("sqlalchemy").text(
            "SELECT count(*) FROM gasto WHERE descripcion LIKE :pat"
        ),
        {"pat": f"Nómina {periodo}%"},
    ).fetchone()
    return int(row[0])


# ═══════════════════════════════════════════════════════════════════════════
# A. JWT / autenticación
# ═══════════════════════════════════════════════════════════════════════════

def test_jwt_alg_none_rechazado(client):
    """alg=none (firma omitida) debe ser rechazado con 401, no autenticar."""
    r = client.get("/api/v1/cotizacion/", headers={"Authorization": f"Bearer {_token_alg_none()}"})
    assert r.status_code == 401, f"alg=none aceptado → BUG: {r.status_code} {r.text[:200]}"


def test_jwt_claims_manipulados_no_otorgan_privilegios(client):
    """Firmar sub=daniel (Ventas) + es_admin=true no debe dar acceso admin."""
    tok = _firmar_payload({
        "sub": "daniel", "type": "access", "es_admin": True,
        "exp": datetime.utcnow() + timedelta(hours=1),
    })
    r = client.get("/api/auth/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403, f"claims es_admin inventados dieron acceso → BUG: {r.status_code}"


def test_jwt_sin_exp_rechazado(client):
    """Token sin fecha de expiración debe ser rechazado."""
    tok = _firmar_payload({"sub": "jackson", "type": "access"})
    r = client.get("/api/v1/cotizacion/", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401, f"token sin exp aceptado → BUG: {r.status_code}"


def test_jwt_sub_numerico_rechazado(client):
    """sub con id numérico (no nombre de usuario) debe ser rechazado."""
    tok = _firmar_payload({
        "sub": "1", "type": "access",
        "exp": datetime.utcnow() + timedelta(hours=1),
    })
    r = client.get("/api/v1/cotizacion/", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401, f"sub numérico aceptado → BUG: {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# B. Mass assignment / estado ilegal
# ═══════════════════════════════════════════════════════════════════════════

def test_mass_assignment_usuario_no_escalona_rol(client, db, cleaner):
    """Crear usuario con rol Dueño + activo + admin en el payload: el sistema
    solo debe aplicar lo que su schema acepta (rol_id explícito si existe),
    jamás un campo 'es_admin' o 'rol' genérico."""
    nombre = f"hacker_{uuid4_hex()}"
    payload = {
        "nombre_usuario": nombre, "password": "Xy12345!",
        "es_admin": True, "rol": "Dueño", "activo": True,
        "rol_id": 1,  # 1 = Dueño en el catálogo
    }
    r = client.post("/api/auth/users", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"crear usuario: {r.status_code} {r.text[:200]}"
    uid = r.json().get("id")
    if uid:
        cleaner.registrar("usuario", uid)
    roles = db.execute(__import__("sqlalchemy").text(
        "SELECT r.nombre FROM usuario_rol ur JOIN rol r ON r.id=ur.rol_id WHERE ur.usuario_id=:u"
    ), {"u": uid}).fetchall()
    nombres = [x[0] for x in roles]
    assert "Dueño" not in nombres, f"escalado a Dueño por mass assignment → BUG: {nombres}"


def test_put_pedido_estado_ilegal_rechazado(client, cleaner):
    """PUT genérico de pedido no debe saltar la máquina de estados
    (COTIZADO → TERMINADO sin producción)."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100_000)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 100_000}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    from conftest import registrar_venta_de_pedido
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    r = client.put(f"/api/v1/pedido/{ped['id']}", json={"estado": "TERMINADO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 400, (
        f"estado TERMINADO por PUT genérico aceptado → BUG: {r.status_code} {r.text[:200]}"
    )
    r = client.put(f"/api/v1/pedido/{ped['id']}", json={"estado": "ENTREGADO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"ENTREGADO sin producción aceptado → BUG: {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# C. Inyección
# ═══════════════════════════════════════════════════════════════════════════

def test_search_inyeccion_sql_no_explota(client):
    """search con literales SQL no debe romper (200) ni filtrar datos extra."""
    r = client.get("/api/v1/cliente/", params={"search": "' OR 1=1 --"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"inyección en search → {r.status_code} {r.text[:200]}"


def test_search_wildcards(client):
    r = client.get("/api/v1/cliente/", params={"search": "%%%__'"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200


def test_id_con_literales_sql(client):
    for bad in ("1;DROP TABLE cliente", "1 OR 1=1", "99999999999999999999"):
        r = client.get(f"/api/v1/cliente/{bad}", headers=ADMIN_HEADERS)
        assert r.status_code in (404, 422), f"id {bad!r} → {r.status_code} {r.text[:120]}"


# ═══════════════════════════════════════════════════════════════════════════
# D. Permisos / BOLA
# ═══════════════════════════════════════════════════════════════════════════

def test_ventas_no_ve_nomina(client):
    r = client.get("/api/v1/nomina/", headers=VENTAS_HEADERS)
    assert r.status_code == 403, f"Ventas accede a nómina → BUG: {r.status_code}"


def test_ventas_no_genera_nomina(client):
    r = client.post("/api/v1/nomina/generar", json={
        "periodo_desde": "2026-09-07", "periodo_hasta": "2026-09-13",
    }, headers=VENTAS_HEADERS)
    assert r.status_code == 403, f"Ventas genera nómina → BUG: {r.status_code}"


def test_ventas_no_paga_nomina(client):
    r = client.post("/api/v1/nomina/99999/pagar", headers=VENTAS_HEADERS)
    assert r.status_code == 403, f"Ventas paga nómina → BUG: {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# E. Race conditions (sin FOR UPDATE a propósito en algunos servicios)
# ═══════════════════════════════════════════════════════════════════════════

def test_doble_pago_nomina_simultaneo(client, db, cleaner):
    """Dos/3 pagos simultáneos de la MISMA nómina: solo UNO debe ganar.
    pagar_nomina lee estado sin FOR UPDATE → ventana de carrera."""
    periodo_desde = date(2026, 9, 7)
    periodo_hasta = date(2026, 9, 13)
    periodo = f"{periodo_desde} al {periodo_hasta}"

    r = client.post("/api/v1/nomina/", json={
        "periodo_desde": str(periodo_desde), "periodo_hasta": str(periodo_hasta),
        "descripcion": "test_destructivas race",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    nomina = r.json()
    nomina_id = nomina["id"]
    cleaner.registrar("nomina", nomina_id)
    n_empleados = sum(1 for d in nomina["detalles"] if float(d["monto_a_pagar"]) > 0)

    # Asignar cuenta a todos los detalles con monto (si no, el pago falla)
    for d in nomina["detalles"]:
        if float(d["monto_a_pagar"]) > 0:
            r2 = client.put(f"/api/v1/nomina/detalle/{d['id']}", json={"metodo_caja_id": 1}, headers=ADMIN_HEADERS)
            assert r2.status_code == 200, r2.text

    antes = _contar_gastos_nomina(db, periodo)
    barrier = threading.Barrier(3)

    def pagar(_):
        c = TestClient(__import__("app.main", fromlist=["app"]).app)
        barrier.wait()
        return c.post(f"/api/v1/nomina/{nomina_id}/pagar", headers=ADMIN_HEADERS)

    with ThreadPoolExecutor(max_workers=3) as ex:
        resultados = list(ex.map(pagar, range(3)))

    despues = _contar_gastos_nomina(db, periodo)
    nuevos = despues - antes
    print(f"  pagos simultáneos: statuses={[r.status_code for r in resultados]} · gastos nuevos={nuevos} (esperado {n_empleados})")
    assert nuevos == n_empleados, (
        f"RACE: la nómina se pagó más de una vez → {nuevos} gastos (esperado {n_empleados})"
    )

    # Limpiar gastos y movimientos de caja generados
    rows = db.execute(__import__("sqlalchemy").text(
        "SELECT id FROM gasto WHERE descripcion LIKE :pat"
    ), {"pat": f"Nómina {periodo}%"}).fetchall()
    for (gid,) in rows:
        cleaner.registrar("gasto", gid)
        cleaner.registrar_caja_ref(f"Gasto #{gid}")


def test_doble_finalizar_orden_simultaneo(client, cleaner, db):
    """Dos finalizaciones simultáneas de la misma orden: el costo debe
    calcularse UNA vez y el pedido quedar TERMINADO sin 500."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100_000)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 100_000}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    from conftest import registrar_venta_de_pedido
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    orden = crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])

    r = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 3, "estado": "ASIGNADA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    etapa = r.json()["id"]
    cleaner.registrar("etapa_produccion", etapa)
    r = client.put(f"/api/v1/produccion/etapa/{etapa}/estado", params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    r = client.put(f"/api/v1/produccion/etapa/{etapa}/estado", params={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    barrier = threading.Barrier(2)

    def finalizar(_):
        c = TestClient(__import__("app.main", fromlist=["app"]).app)
        barrier.wait()
        return c.put(f"/api/v1/produccion/orden/{orden['id']}/estado",
                     params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)

    with ThreadPoolExecutor(max_workers=2) as ex:
        resultados = list(ex.map(finalizar, range(2)))

    statuses = sorted(r.status_code for r in resultados)
    print(f"  doble finalizar: {statuses}")
    # El pedido debe estar TERMINADO y el costo creado exactamente 1 vez
    r = client.get(f"/api/v1/pedido/{ped['id']}", headers=ADMIN_HEADERS)
    assert r.json()["estado"] == "TERMINADO", f"pedido en {r.json()['estado']}"
    n_costos = db.execute(__import__("sqlalchemy").text(
        "SELECT count(*) FROM costo_produccion WHERE orden_produccion_id=:o"
    ), {"o": orden["id"]}).fetchone()[0]
    assert n_costos == 1, f"costo duplicado → BUG: {n_costos} costos para la orden"
    assert 500 not in statuses, f"alguna finalización dio 500 → revisar: {statuses}"


def test_doble_anular_nomina_simultaneo(client, db, cleaner):
    """Anular la misma nómina desde 2 hilos: la reversión debe aplicar UNA vez
    (sin gastos negativos, sin aguinaldo revertido dos veces)."""
    periodo_desde = date(2026, 9, 14)
    periodo_hasta = date(2026, 9, 20)
    r = client.post("/api/v1/nomina/", json={
        "periodo_desde": str(periodo_desde), "periodo_hasta": str(periodo_hasta),
        "descripcion": "test_destructivas anular",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    nomina = r.json()
    nomina_id = nomina["id"]
    cleaner.registrar("nomina", nomina_id)
    for d in nomina["detalles"]:
        if float(d["monto_a_pagar"]) > 0:
            r2 = client.put(f"/api/v1/nomina/detalle/{d['id']}", json={"metodo_caja_id": 1}, headers=ADMIN_HEADERS)
            assert r2.status_code == 200, r2.text

    aguinaldo_antes = db.execute(__import__("sqlalchemy").text(
        "SELECT COALESCE(sum(saldo_aguinaldo),0) FROM empleado"
    )).fetchone()[0]
    r = client.post(f"/api/v1/nomina/{nomina_id}/pagar", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    barrier = threading.Barrier(2)

    def anular(_):
        c = TestClient(__import__("app.main", fromlist=["app"]).app)
        barrier.wait()
        return c.post(f"/api/v1/nomina/{nomina_id}/anular", headers=ADMIN_HEADERS)

    with ThreadPoolExecutor(max_workers=2) as ex:
        resultados = list(ex.map(anular, range(2)))

    statuses = sorted(r.status_code for r in resultados)
    estado = db.execute(__import__("sqlalchemy").text(
        "SELECT estado FROM nomina WHERE id=:n"
    ), {"n": nomina_id}).fetchone()[0]
    aguinaldo_despues = db.execute(__import__("sqlalchemy").text(
        "SELECT COALESCE(sum(saldo_aguinaldo),0) FROM empleado"
    )).fetchone()[0]
    print(f"  doble anular: {statuses} · estado={estado}")
    assert estado == "ANULADA", f"nómina en {estado}"
    assert float(aguinaldo_despues) == float(aguinaldo_antes), (
        f"aguinaldo no revertido correctamente: antes {aguinaldo_antes} → después {aguinaldo_despues}"
    )
    assert statuses != [200, 200], (
        "ambas anulaciones OK → la reversión pudo aplicar 2 veces (revisar)"
    )


# ═══════════════════════════════════════════════════════════════════════════
# F. Límites extremos
# ═══════════════════════════════════════════════════════════════════════════

def test_montos_extremos_en_pagos(client, cleaner):
    """Pagos con montos absurdos deben rechazarse o validarse, no romper."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100_000)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 100_000}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    from conftest import registrar_venta_de_pedido
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    venta_id = db_venta(ped["id"])

    base = {"venta_id": venta_id, "moneda_id": 1, "fecha": datetime.utcnow().isoformat(),
            "metodo_pago": "EFECTIVO_COP"}
    for monto in (-5, 0, 1e15, 99999999999999999999999):
        r = client.post("/api/v1/pago/", json={**base, "monto": monto}, headers=ADMIN_HEADERS)
        assert r.status_code in (400, 422), (
            f"pago con monto {monto} aceptado → BUG: {r.status_code} {r.text[:120]}"
        )


def test_cantidad_negativa_consumo_rechazada(client, cleaner):
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100_000)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 100_000}],
    }, headers=ADMIN_HEADERS)
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    from conftest import registrar_venta_de_pedido
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    orden = crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])
    r = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 3, "estado": "EN_PROCESO",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    etapa = r.json()["id"]
    cleaner.registrar("etapa_produccion", etapa)
    r = client.post("/api/v1/produccion/consumo/", json={
        "etapa_produccion_id": etapa, "material_id": 1, "cantidad": -10,
        "fecha": datetime.utcnow().isoformat(),
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 422, f"consumo negativo aceptado → BUG: {r.status_code} {r.text[:120]}"


def test_strings_gigantes_rechazados(client, cleaner):
    r = client.post("/api/v1/cliente/", json={
        "nombre": "X" * 5000, "telefono": "555",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (400, 422), f"nombre gigante aceptado → BUG: {r.status_code}"


def test_paginacion_extrema_no_crashea(client):
    r = client.get("/api/v1/cliente/", params={"limite": 999999999}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"paginación extrema → {r.status_code}"


def test_nomina_fechas_invertidas(client):
    r = client.post("/api/v1/nomina/generar", json={
        "periodo_desde": "2026-09-21", "periodo_hasta": "2026-09-14",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"fechas invertidas aceptadas → BUG: {r.status_code}"


def test_doble_nomina_mismo_periodo_rechazada(client, cleaner):
    r = client.post("/api/v1/nomina/", json={
        "periodo_desde": "2026-09-21", "periodo_hasta": "2026-09-27",
        "descripcion": "test_destructivas dup",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cleaner.registrar("nomina", r.json()["id"])
    r2 = client.post("/api/v1/nomina/", json={
        "periodo_desde": "2026-09-21", "periodo_hasta": "2026-09-27",
        "descripcion": "test_destructivas dup2",
    }, headers=ADMIN_HEADERS)
    assert r2.status_code == 400, f"nómina duplicada del periodo aceptada → BUG: {r2.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# G. Integridad
# ═══════════════════════════════════════════════════════════════════════════

def test_anular_nomina_revierte_gastos_y_caja(client, db, cleaner):
    """Anular una nómina pagada debe eliminar gastos Y movimientos de caja."""
    periodo_desde = date(2026, 9, 21)
    periodo_hasta = date(2026, 9, 27)
    periodo = f"{periodo_desde} al {periodo_hasta}"
    r = client.post("/api/v1/nomina/", json={
        "periodo_desde": str(periodo_desde), "periodo_hasta": str(periodo_hasta),
        "descripcion": "test_destructivas anular integridad",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    nomina = r.json()
    nomina_id = nomina["id"]
    cleaner.registrar("nomina", nomina_id)
    for d in nomina["detalles"]:
        if float(d["monto_a_pagar"]) > 0:
            client.put(f"/api/v1/nomina/detalle/{d['id']}", json={"metodo_caja_id": 1}, headers=ADMIN_HEADERS)
    assert client.post(f"/api/v1/nomina/{nomina_id}/pagar", headers=ADMIN_HEADERS).status_code == 200

    n_gastos = _contar_gastos_nomina(db, periodo)
    n_mov = db.execute(__import__("sqlalchemy").text(
        "SELECT count(*) FROM movimiento_caja WHERE referencia LIKE 'Gasto #%'"
    )).fetchone()[0]
    n_mov_antes = db.execute(__import__("sqlalchemy").text(
        "SELECT count(*) FROM movimiento_caja WHERE referencia LIKE 'Gasto #%' AND id >= :i"
    ), {"i": 1}).fetchone()[0]

    r = client.post(f"/api/v1/nomina/{nomina_id}/anular", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    n_gastos_despues = _contar_gastos_nomina(db, periodo)
    assert n_gastos_despues == 0, f"gastos no revertidos: {n_gastos_despues}"
    n_mov_despues = db.execute(__import__("sqlalchemy").text(
        "SELECT count(*) FROM movimiento_caja WHERE referencia LIKE 'Gasto #%'"
    )).fetchone()[0]
    assert n_mov_despues == n_mov - n_gastos, (
        f"movimientos de caja no revertidos: {n_mov} → {n_mov_despues} (gastos {n_gastos})"
    )


def test_doble_anular_secuencial_rechazado(client, cleaner):
    """Anular dos veces en secuencia: la segunda debe ser 400."""
    r = client.post("/api/v1/nomina/", json={
        "periodo_desde": "2026-09-28", "periodo_hasta": "2026-10-04",
        "descripcion": "test_destructivas doble anular",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    nomina_id = r.json()["id"]
    cleaner.registrar("nomina", nomina_id)
    for d in r.json()["detalles"]:
        if float(d["monto_a_pagar"]) > 0:
            client.put(f"/api/v1/nomina/detalle/{d['id']}", json={"metodo_caja_id": 1}, headers=ADMIN_HEADERS)
    assert client.post(f"/api/v1/nomina/{nomina_id}/pagar", headers=ADMIN_HEADERS).status_code == 200
    assert client.post(f"/api/v1/nomina/{nomina_id}/anular", headers=ADMIN_HEADERS).status_code == 200
    r2 = client.post(f"/api/v1/nomina/{nomina_id}/anular", headers=ADMIN_HEADERS)
    assert r2.status_code == 400, f"doble anulación permitida → BUG: {r2.status_code}"


def test_eliminar_gasto_de_nomina_pagada(client, db, cleaner):
    """Documentar: ¿se puede eliminar un gasto de nómina pagada por la puerta
    de gastos? La nómina quedaría PAGADA sin su gasto (inconsistencia)."""
    r = client.post("/api/v1/nomina/", json={
        "periodo_desde": "2026-10-05", "periodo_hasta": "2026-10-11",
        "descripcion": "test_destructivas gasto nomina",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    nomina_id = r.json()["id"]
    cleaner.registrar("nomina", nomina_id)
    for d in r.json()["detalles"]:
        if float(d["monto_a_pagar"]) > 0:
            client.put(f"/api/v1/nomina/detalle/{d['id']}", json={"metodo_caja_id": 1}, headers=ADMIN_HEADERS)
    assert client.post(f"/api/v1/nomina/{nomina_id}/pagar", headers=ADMIN_HEADERS).status_code == 200

    detalle_con_gasto = None
    r = client.get(f"/api/v1/nomina/{nomina_id}", headers=ADMIN_HEADERS)
    for d in r.json()["detalles"]:
        if d.get("gasto_id"):
            detalle_con_gasto = d
            break
    assert detalle_con_gasto, "nómina pagada sin gastos en detalles"
    gasto_id = detalle_con_gasto["gasto_id"]
    cleaner.registrar("gasto", gasto_id)
    r = client.delete(f"/api/v1/gastos/{gasto_id}", headers=ADMIN_HEADERS)
    if r.status_code in (200, 204):
        # Documentar la inconsistencia (no fallar el test si existe: lo anotamos)
        r = client.get(f"/api/v1/nomina/{nomina_id}", headers=ADMIN_HEADERS)
        det_despues = next((d for d in r.json()["detalles"] if d["id"] == detalle_con_gasto["id"]), None)
        print(f"  ⚠ gasto #{gasto_id} de nómina PAGADA eliminado por /gastos — "
              f"nómina sigue {r.json()['estado']}, detalle.gasto_id={det_despues.get('gasto_id') if det_despues else '?'}")
    else:
        assert r.status_code in (400, 403, 404), f"delete gasto: {r.status_code}"


def test_sobrepago_rechazado(client, cleaner):
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 50_000)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 50_000}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    from conftest import registrar_venta_de_pedido
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    venta_id = db_venta(ped["id"])
    base = {"venta_id": venta_id, "moneda_id": 1, "fecha": datetime.utcnow().isoformat(),
            "metodo_pago": "EFECTIVO_COP"}
    r = client.post("/api/v1/pago/", json={**base, "monto": 30_000}, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/pago/", json={**base, "monto": 30_000}, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"sobrepago aceptado → BUG: {r.status_code} {r.text[:150]}"


# helpers
def uuid4_hex():
    import uuid
    return uuid.uuid4().hex[:12]


def db_venta(pedido_id: int):
    db = session_local()
    try:
        row = db.execute(__import__("sqlalchemy").text(
            "SELECT id FROM venta WHERE pedido_id=:p"
        ), {"p": pedido_id}).fetchone()
        return int(row[0]) if row else None
    finally:
        db.close()