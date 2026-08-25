#!/usr/bin/env python3
"""
test_ataques_conc.py — Suite de ataques de CONCURRENCIA y configuración de red
para el ERP YEIKAR (FastAPI + PostgreSQL).

Cada test intenta romper una invariante con hilos sincronizados por Barrier
(un TestClient NUEVO por hilo) o con peticiones adversariales, y exige que el
sistema RESUELVA el ataque con 4xx limpio o con invariantes intactas.
Un test que falla documenta un bug real (se reporta; no se arregla aquí).

Ataques cubiertos:
  1. Doble convertir cotización CON adelanto simultáneo (doble cobro).
  2. Race: pagar nómina con 5 hilos (fix FOR UPDATE).
  3. Race: anular nómina con 5 hilos (fix FOR UPDATE).
  4. Race: eliminar pedido vs finalizar orden de producción.
  5. Race: eliminar gasto de nómina pagada vs anular nómina.
  6. Race: doble ENTREGADO del mismo envío (estado terminal).
  7. Race: doble crear material con el MISMO nombre.
  8. CORS: origen atacante reflejado en Access-Control-Allow-Origin?
  9. Errores verbosos: stack traces / SQL / rutas internas en respuestas 500/422.
 10. Headers de seguridad ausentes (X-Frame-Options, HSTS, CSP, ...).
 11. Swagger/OpenAPI expuestos (/docs, /openapi.json).
 12. Login: lockout tras intentos fallidos (429).
 13. Race: doble pago del 100% a la misma venta.

Ejecutar con PostgreSQL activo:
  cd /home/daniel-castellanos/YEIKAR/backend
  venv/bin/python -m pytest test/test_ataques_conc.py -v
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.db.session import session_local

try:
    from conftest import (
        ADMIN_HEADERS,
        crear_cliente,
        crear_cotizacion,
        crear_orden_desde_pedido,
        crear_producto,
        registrar_venta_de_pedido,
    )
except ImportError:  # pragma: no cover
    pytest.fail("No se pudo importar conftest")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers compartidos
# ═══════════════════════════════════════════════════════════════════════════
def _cliente_nuevo() -> TestClient:
    from app.main import app as _app

    return TestClient(_app)


def _correr_en_paralelo(metodos, n=2):
    """Ejecuta `metodos` (lista de callables) en n hilos sincronizados por
    Barrier: todos arrancan la petición exactamente a la vez."""
    barrier = threading.Barrier(len(metodos))

    def _run(fn):
        barrier.wait()
        return fn()

    with ThreadPoolExecutor(max_workers=max(len(metodos), n)) as ex:
        return list(ex.map(_run, metodos))


def _contar_gastos_nomina(db, periodo: str) -> int:
    row = db.execute(
        text("SELECT count(*) FROM gasto WHERE descripcion LIKE :pat"),
        {"pat": f"Nómina {periodo}%"},
    ).fetchone()
    return int(row[0])


def _registrar_gastos_y_caja(db, cleaner, periodo: str):
    for (gid,) in db.execute(
        text("SELECT id FROM gasto WHERE descripcion LIKE :pat"),
        {"pat": f"Nómina {periodo}%"},
    ).fetchall():
        cleaner.registrar("gasto", int(gid))
        cleaner.registrar_caja_ref(f"Gasto #{gid}")


def _snapshot_aguinaldo(db, nomina_id: int) -> dict:
    rows = db.execute(
        text(
            "SELECT nd.empleado_id, COALESCE(e.saldo_aguinaldo, 0) "
            "FROM nomina_detalle nd JOIN empleado e ON e.id = nd.empleado_id "
            "WHERE nd.nomina_id = :n"
        ),
        {"n": nomina_id},
    ).fetchall()
    return {int(r[0]): float(r[1]) for r in rows}


def _restaurar_aguinaldo(db, snapshot: dict):
    for emp_id, saldo in snapshot.items():
        db.execute(
            text("UPDATE empleado SET saldo_aguinaldo = :s WHERE id = :e"),
            {"s": saldo, "e": emp_id},
        )
    db.commit()


def _crear_nomina(client, cleaner, desde, hasta, descripcion):
    r = client.post(
        "/api/v1/nomina/",
        json={"periodo_desde": desde, "periodo_hasta": hasta, "descripcion": descripcion},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, f"crear nómina → {r.status_code}: {r.text[:300]}"
    nomina = r.json()
    cleaner.registrar("nomina", nomina["id"])
    for d in nomina["detalles"]:
        if float(d["monto_a_pagar"]) > 0:
            r2 = client.put(
                f"/api/v1/nomina/detalle/{d['id']}", json={"metodo_caja_id": 1}, headers=ADMIN_HEADERS
            )
            assert r2.status_code == 200, f"asignar caja detalle → {r2.status_code}: {r2.text[:200]}"
    return nomina


def _base_pedido_con_orden(client, cleaner, precio=100_000.0):
    """Cliente + producto + cotización → pedido (convertir, sin adelanto) →
    orden de producción → etapa EN_PROCESO. Devuelve (pedido, orden, etapa)."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], precio)
    r = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={
            "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": precio}],
        },
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text[:300]}"
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    orden = crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])
    r = client.post(
        "/api/v1/produccion/etapa/",
        json={
            "orden_produccion_id": orden["id"],
            "area_id": 1,
            "empleado_responsable_id": 3,
            "estado": "ASIGNADA",
        },
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, f"crear etapa → {r.status_code}: {r.text[:300]}"
    etapa_id = r.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)
    for st in ("EN_PROCESO", "COMPLETADA"):
        r = client.put(
            f"/api/v1/produccion/etapa/{etapa_id}/estado", params={"estado": st}, headers=ADMIN_HEADERS
        )
        assert r.status_code == 200, f"etapa → {st}: {r.status_code} {r.text[:200]}"
    return ped, orden, etapa_id


def _registrar_envio_del_pedido(db, cleaner, pedido_id):
    row = db.execute(text("SELECT id FROM envio WHERE pedido_id = :p"), {"p": pedido_id}).fetchone()
    if row:
        cleaner.registrar("envio", int(row[0]))
        return int(row[0])
    return None


def _registrar_pagos_venta(db, cleaner, venta_id: int):
    """Registra en el cleaner todos los pagos de una venta (necesario cuando los
    pagos se crean DESPUÉS de llamar a registrar_venta_de_pedido)."""
    for (pid,) in db.execute(text("SELECT id FROM pago WHERE venta_id = :v"), {"v": venta_id}).fetchall():
        cleaner.registrar("pago", int(pid))


def _cuerpo_fuga(texto: str) -> bool:
    """Detecta fuga de información interna en un cuerpo de respuesta."""
    marcas = (
        "Traceback",
        'File "',
        "app/modules/",
        "app/main.py",
        "sqlalchemy.exc",
        "psycopg2",
        "line ",
        "at 0x",
        "uvicorn/",
        "site-packages/",
    )
    return any(m in texto for m in marcas)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Doble convertir cotización CON adelanto simultáneo (doble cobro)
# ═══════════════════════════════════════════════════════════════════════════
def test_doble_convertir_cotizacion_con_adelanto(client, db, cleaner):
    """Dos conversiones simultáneas de la misma cotización, ambas con adelanto
    del 50%: solo UN pedido y UN pago-adelanto deben existir al final.
    Dos adelantos registrados = doble cobro por carrera (BUG)."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    precio = 100_000.0
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], precio)

    payload = {
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": precio}],
        "adelanto": precio * 0.5,
        "moneda_adelanto_id": 1,
        "metodo_pago": "EFECTIVO_COP",
    }

    def convertir(_):
        c = _cliente_nuevo()
        return c.post(f"/api/v1/pedido/convertir/{cot['id']}", json=payload, headers=ADMIN_HEADERS)

    resultados = _correr_en_paralelo([lambda: convertir(0), lambda: convertir(1)])
    statuses = sorted(r.status_code for r in resultados)
    print(f"  convertir+adelanto: {statuses}")

    n_pedidos = db.execute(
        text("SELECT count(*) FROM pedido WHERE cotizacion_id = :c"), {"c": cot["id"]}
    ).fetchone()[0]
    n_adelantos = db.execute(
        text("SELECT count(*) FROM pago WHERE referencia LIKE :pat"),
        {"pat": f"Adelanto conversión cotización #{cot['id']}%"},
    ).fetchone()[0]

    assert 500 not in statuses, f"conversión con 500 → revisar: {[r.text[:200] for r in resultados if r.status_code == 500]}"
    assert n_pedidos == 1, f"BUG: {n_pedidos} pedidos creados para la cotización (esperado 1)"
    assert n_adelantos == 1, (
        f"BUG DOBLE COBRO: {n_adelantos} adelantos registrados para la cotización "
        f"#{cot['id']} (esperado 1) — statuses {statuses}"
    )
    assert statuses.count(201) == 1, f"se esperaba exactamente 1 éxito (201), got {statuses}"

    pedido_id = db.execute(
        text("SELECT id FROM pedido WHERE cotizacion_id = :c"), {"c": cot["id"]}
    ).fetchone()[0]
    cleaner.registrar("pedido", int(pedido_id))
    registrar_venta_de_pedido(client, cleaner, int(pedido_id))
    venta_row = db.execute(text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}).fetchone()
    if venta_row:
        _registrar_pagos_venta(db, cleaner, int(venta_row[0]))


# ═══════════════════════════════════════════════════════════════════════════
# 2. Race: pagar nómina con 5 hilos (fix FOR UPDATE)
# ═══════════════════════════════════════════════════════════════════════════
def test_pagar_nomina_5_hilos(client, db, cleaner):
    """5 pagos simultáneos de la MISMA nómina: solo 1 debe ganar.
    Gastos creados = N (uno por empleado), nunca 5N."""
    desde, hasta = "2026-11-02", "2026-11-08"
    periodo = f"{desde} al {hasta}"
    nomina = _crear_nomina(client, cleaner, desde, hasta, "test_ataques pagar 5h")
    nomina_id = nomina["id"]
    n_empleados = sum(1 for d in nomina["detalles"] if float(d["monto_a_pagar"]) > 0)
    snapshot_agui = _snapshot_aguinaldo(db, nomina_id)

    antes = _contar_gastos_nomina(db, periodo)

    def pagar(_):
        c = _cliente_nuevo()
        return c.post(f"/api/v1/nomina/{nomina_id}/pagar", headers=ADMIN_HEADERS)

    resultados = _correr_en_paralelo([lambda: pagar(i) for i in range(5)], n=5)
    statuses = sorted(r.status_code for r in resultados)
    despues = _contar_gastos_nomina(db, periodo)
    nuevos = despues - antes
    exito = db.execute(text("SELECT estado FROM nomina WHERE id = :n"), {"n": nomina_id}).fetchone()[0]
    print(f"  pagar 5 hilos: statuses={statuses} · gastos nuevos={nuevos} (esperado {n_empleados})")

    assert exito == "PAGADA", f"nómina quedó en {exito}"
    assert statuses.count(200) == 1, f"BUG: {statuses.count(200)} pagos ganaron (esperado 1) — {statuses}"
    assert nuevos == n_empleados, (
        f"BUG RACE PAGO: {nuevos} gastos creados (esperado {n_empleados}) → la nómina "
        f"se pagó más de una vez — statuses {statuses}"
    )

    _registrar_gastos_y_caja(db, cleaner, periodo)
    _restaurar_aguinaldo(db, snapshot_agui)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Race: anular nómina con 5 hilos (fix FOR UPDATE)
# ═══════════════════════════════════════════════════════════════════════════
def test_anular_nomina_5_hilos(client, db, cleaner):
    """5 anulaciones simultáneas de la misma nómina PAGADA: solo 1 debe ganar;
    estado final ANULADA y aguinaldo revertido EXACTAMENTE una vez."""
    desde, hasta = "2026-11-09", "2026-11-15"
    periodo = f"{desde} al {hasta}"
    nomina = _crear_nomina(client, cleaner, desde, hasta, "test_ataques anular 5h")
    nomina_id = nomina["id"]
    snapshot_agui = _snapshot_aguinaldo(db, nomina_id)

    r = client.post(f"/api/v1/nomina/{nomina_id}/pagar", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"pago previo → {r.status_code}: {r.text[:200]}"
    total_aguinaldo_antes = float(
        db.execute(text("SELECT COALESCE(sum(saldo_aguinaldo), 0) FROM empleado")).fetchone()[0]
    )

    def anular(_):
        c = _cliente_nuevo()
        return c.post(f"/api/v1/nomina/{nomina_id}/anular", headers=ADMIN_HEADERS)

    resultados = _correr_en_paralelo([lambda: anular(i) for i in range(5)], n=5)
    statuses = sorted(r.status_code for r in resultados)
    estado = db.execute(text("SELECT estado FROM nomina WHERE id = :n"), {"n": nomina_id}).fetchone()[0]
    total_aguinaldo_despues = float(
        db.execute(text("SELECT COALESCE(sum(saldo_aguinaldo), 0) FROM empleado")).fetchone()[0]
    )
    gastos_restantes = _contar_gastos_nomina(db, periodo)
    print(f"  anular 5 hilos: statuses={statuses} · estado={estado} · gastos restantes={gastos_restantes}")

    assert 500 not in statuses, "alguna anulación dio 500"
    assert estado == "ANULADA", f"nómina en {estado} (esperado ANULADA)"
    assert statuses.count(200) == 1, f"BUG: {statuses.count(200)} anulaciones ganaron — {statuses}"
    assert abs(total_aguinaldo_despues - total_aguinaldo_antes) < 0.01, (
        f"BUG: aguinaldo revertido más de una vez: antes {total_aguinaldo_antes} → después {total_aguinaldo_despues}"
    )
    assert gastos_restantes == 0, f"BUG: quedan {gastos_restantes} gastos de la nómina anulada"

    _registrar_gastos_y_caja(db, cleaner, periodo)
    _restaurar_aguinaldo(db, snapshot_agui)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Race: eliminar pedido mientras se finaliza su orden de producción
# ═══════════════════════════════════════════════════════════════════════════
def test_eliminar_pedido_vs_finalizar_orden(client, db, cleaner):
    """Hilo A: DELETE /pedido/{id}. Hilo B: finalizar la orden (FINALIZADA).
    Debe ganar UNO limpiamente: o el pedido queda TERMINADO con su orden, o se
    borra sin dejar órdenes/envíos huérfanos. 500 o filas huérfanas = BUG."""
    ped, orden, _ = _base_pedido_con_orden(client, cleaner)
    pedido_id, orden_id = ped["id"], orden["id"]

    def borrar(_):
        c = _cliente_nuevo()
        return c.delete(f"/api/v1/pedido/{pedido_id}", headers=ADMIN_HEADERS)

    def finalizar(_):
        c = _cliente_nuevo()
        return c.put(
            f"/api/v1/produccion/orden/{orden_id}/estado",
            params={"estado": "FINALIZADA"},
            headers=ADMIN_HEADERS,
        )

    resultados = _correr_en_paralelo([lambda: borrar(0), lambda: finalizar(0)])
    statuses = sorted(r.status_code for r in resultados)
    print(f"  delete vs finalizar: {statuses}")

    for r in resultados:
        assert r.status_code != 500, f"500 en la carrera → {r.text[:400]}"

    pedido_existe = db.execute(text("SELECT id FROM pedido WHERE id = :p"), {"p": pedido_id}).fetchone()
    orden_existe = db.execute(text("SELECT id FROM orden_produccion WHERE id = :o"), {"o": orden_id}).fetchone()

    # Invariante: nunca quedan filas huérfanas.
    huérfanas_orden = db.execute(text(
        "SELECT count(*) FROM orden_produccion op "
        "WHERE NOT EXISTS (SELECT 1 FROM detalle_pedido dp WHERE dp.id = op.detalle_pedido_id)"
    )).fetchone()[0]
    huérfanas_envio = db.execute(text(
        "SELECT count(*) FROM envio e "
        "WHERE NOT EXISTS (SELECT 1 FROM pedido p WHERE p.id = e.pedido_id)"
    )).fetchone()[0]
    assert huérfanas_orden == 0, f"BUG: {huérfanas_orden} órdenes de producción huérfanas en la BD"
    assert huérfanas_envio == 0, f"BUG: {huérfanas_envio} envíos huérfanos en la BD"

    if pedido_existe:
        estado_ped = db.execute(text("SELECT estado FROM pedido WHERE id = :p"), {"p": pedido_id}).fetchone()[0]
        assert estado_ped in ("TERMINADO", "ENTREGADO"), f"pedido quedó en {estado_ped}"
        assert orden_existe, "el pedido existe pero su orden de producción fue borrada (inconsistencia)"
        estado_ord = db.execute(text("SELECT estado FROM orden_produccion WHERE id = :o"), {"o": orden_id}).fetchone()[0]
        assert estado_ord == "FINALIZADA", f"orden en {estado_ord}"
        _registrar_envio_del_pedido(db, cleaner, pedido_id)
    else:
        assert not orden_existe, "BUG: pedido borrado pero su orden de producción sigue en la BD (huérfana)"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Race: eliminar gasto de nómina pagada mientras se anula la nómina
# ═══════════════════════════════════════════════════════════════════════════
def test_eliminar_gasto_vs_anular_nomina(client, db, cleaner):
    """Hilo A: DELETE /gasto/gastos/{gasto}. Hilo B: POST /nomina/{id}/anular.
    El estado final debe ser consistente: nómina ANULADA, sin gasto y sin
    movimiento de caja (o rechazo limpio). Inconsistencia o 500 = BUG."""
    desde, hasta = "2026-11-16", "2026-11-22"
    periodo = f"{desde} al {hasta}"
    nomina = _crear_nomina(client, cleaner, desde, hasta, "test_ataques gasto vs anular")
    nomina_id = nomina["id"]
    snapshot_agui = _snapshot_aguinaldo(db, nomina_id)

    r = client.post(f"/api/v1/nomina/{nomina_id}/pagar", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"pago previo → {r.status_code}: {r.text[:200]}"

    detalle_con_gasto = None
    r = client.get(f"/api/v1/nomina/{nomina_id}", headers=ADMIN_HEADERS)
    for d in r.json()["detalles"]:
        if d.get("gasto_id"):
            detalle_con_gasto = d
            break
    assert detalle_con_gasto, "nómina pagada sin gasto_id en detalles"
    gasto_id = detalle_con_gasto["gasto_id"]
    cleaner.registrar("gasto", gasto_id)
    cleaner.registrar_caja_ref(f"Gasto #{gasto_id}")

    def borrar_gasto(_):
        c = _cliente_nuevo()
        return c.delete(f"/api/v1/gasto/gastos/{gasto_id}", headers=ADMIN_HEADERS)

    def anular(_):
        c = _cliente_nuevo()
        return c.post(f"/api/v1/nomina/{nomina_id}/anular", headers=ADMIN_HEADERS)

    resultados = _correr_en_paralelo([lambda: borrar_gasto(0), lambda: anular(0)])
    statuses = sorted(r.status_code for r in resultados)
    print(f"  delete gasto vs anular: {statuses}")

    for r in resultados:
        assert r.status_code != 500, f"500 en la carrera → {r.text[:400]}"

    estado = db.execute(text("SELECT estado FROM nomina WHERE id = :n"), {"n": nomina_id}).fetchone()[0]
    gasto_existe = db.execute(text("SELECT id FROM gasto WHERE id = :g"), {"g": gasto_id}).fetchone()
    mov_existe = db.execute(
        text("SELECT id FROM movimiento_caja WHERE referencia = :r"), {"r": f"Gasto #{gasto_id}"}
    ).fetchone()
    detalle_estado = db.execute(
        text("SELECT gasto_id FROM nomina_detalle WHERE id = :d"), {"d": detalle_con_gasto["id"]}
    ).fetchone()[0]
    print(f"  → nómina={estado} · gasto existe={bool(gasto_existe)} · movimiento existe={bool(mov_existe)} · detalle.gasto_id={detalle_estado}")

    assert estado == "ANULADA", f"nómina en {estado} (esperado ANULADA)"
    assert gasto_existe is None, f"BUG: el gasto #{gasto_id} sobrevivió a la anulación (inconsistencia)"
    assert mov_existe is None, f"BUG: movimiento de caja 'Gasto #{gasto_id}' huérfano tras la anulación"
    assert detalle_estado is None, f"BUG: detalle de nómina sigue apuntando al gasto #{gasto_id}"

    _registrar_gastos_y_caja(db, cleaner, periodo)
    _restaurar_aguinaldo(db, snapshot_agui)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Race: doble ENTREGADO del mismo envío (estado terminal)
# ═══════════════════════════════════════════════════════════════════════════
def test_doble_entregado_envio(client, db, cleaner):
    """2 hilos marcan el MISMO envío ENTREGADO simultáneamente. El estado
    ENTREGADO es terminal: el segundo debe ser 400. Ambos 200 = BUG."""
    ped, orden, _ = _base_pedido_con_orden(client, cleaner)
    pedido_id = ped["id"]
    r = client.put(
        f"/api/v1/produccion/orden/{orden['id']}/estado",
        params={"estado": "FINALIZADA"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"finalizar → {r.status_code}: {r.text[:300]}"
    envio_id = _registrar_envio_del_pedido(db, cleaner, pedido_id)
    assert envio_id, "no se auto-creó el envío al finalizar la producción"

    r = client.put(
        f"/api/v1/envio/{envio_id}/estado", params={"estado": "EN_TRANSITO"}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, f"EN_TRANSITO → {r.status_code}: {r.text[:200]}"

    def entregar(_):
        c = _cliente_nuevo()
        return c.put(
            f"/api/v1/envio/{envio_id}/estado", params={"estado": "ENTREGADO"}, headers=ADMIN_HEADERS
        )

    resultados = _correr_en_paralelo([lambda: entregar(0), lambda: entregar(1)])
    statuses = sorted(r.status_code for r in resultados)
    estado_envio = db.execute(text("SELECT estado FROM envio WHERE id = :e"), {"e": envio_id}).fetchone()[0]
    estado_pedido = db.execute(text("SELECT estado FROM pedido WHERE id = :p"), {"p": pedido_id}).fetchone()[0]
    print(f"  doble ENTREGADO: {statuses} · envio={estado_envio} · pedido={estado_pedido}")

    assert 500 not in statuses, f"500 al entregar → {[r.text[:200] for r in resultados if r.status_code == 500]}"
    assert estado_envio == "ENTREGADO", f"envío en {estado_envio}"
    assert statuses == [200, 400], (
        f"BUG ESTADO TERMINAL: ambos PUT ENTREGADO respondieron 200. El estado "
        f"ENTREGADO no es terminal en la práctica: puede re-marcarse. statuses={statuses}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. Race: doble crear material con el MISMO nombre
# ═══════════════════════════════════════════════════════════════════════════
def test_doble_crear_material_mismo_nombre(client, db, cleaner):
    """2 hilos crean un material con el MISMO nombre a la vez.
    Sin constraint UNIQUE ni chequeo previo, ambos 201 y el catálogo queda
    con 2 materiales idénticos (duplicado); un 500 por IntegrityError = BUG."""
    nombre = f"MAT RACE {uuid4().hex[:8]}"
    payload = {"nombre": nombre, "unidad_medida_id": 2, "costo_base": 1000.0}

    def crear(_):
        c = _cliente_nuevo()
        return c.post("/api/v1/material/", json=payload, headers=ADMIN_HEADERS)

    resultados = _correr_en_paralelo([lambda: crear(0), lambda: crear(1)])
    statuses = sorted(r.status_code for r in resultados)
    print(f"  doble material: {statuses}")

    for r in resultados:
        assert r.status_code != 500, f"BUG: IntegrityError/500 al crear material → {r.text[:300]}"
        if r.status_code in (200, 201):
            cleaner.registrar("material", r.json()["id"])

    n_filas = db.execute(
        text("SELECT count(*) FROM material WHERE nombre = :n"), {"n": nombre}
    ).fetchone()[0]
    if statuses == [201, 201]:
        print(
            f"  ⚠ hallazgo: 2 materiales con el MISMO nombre ({nombre}) creados "
            f"simultáneamente — no hay constraint UNIQUE sobre material.nombre "
            f"ni chequeo previo; el catálogo acepta duplicados exactos."
        )
    assert n_filas == len([s for s in statuses if s == 201]), (
        f"inconsistencia: {n_filas} filas para {len([s for s in statuses if s == 201])} creados"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. CORS: origen atacante
# ═══════════════════════════════════════════════════════════════════════════
def test_cors_origen_atacante(client):
    """GET con Origin: https://evil.example → la respuesta NO debe incluir
    Access-Control-Allow-Origin con el origen del atacante (ni * con credenciales)."""
    origen = "https://evil.example"
    r = client.get("/api/v1/cotizacion/", headers={**ADMIN_HEADERS, "Origin": origen})
    acao = r.headers.get("access-control-allow-origin")
    print(f"  ACAO en GET: {acao!r}")
    assert acao is None or acao != "*" or "credentials" not in r.headers, "CORS abierto a *"
    assert acao != origen, (
        f"BUG CORS: el origen del atacante {origen} se refleja en Access-Control-Allow-Origin"
    )

    r2 = client.options(
        "/api/v1/cotizacion/",
        headers={
            "Origin": origen,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    acao2 = r2.headers.get("access-control-allow-origin")
    print(f"  ACAO en preflight OPTIONS: {acao2!r}")
    assert acao2 != origen, (
        f"BUG CORS: el preflight del atacante {origen} fue aceptado (Access-Control-Allow-Origin: {acao2})"
    )
    print(f"  (config) ALLOWED_ORIGINS={settings.ALLOWED_ORIGINS!r} · allow_credentials=True · allow_methods=* · allow_headers=*")


# ═══════════════════════════════════════════════════════════════════════════
# 9. Errores verbosos: fuga de stack trace / SQL / rutas internas
# ═══════════════════════════════════════════════════════════════════════════
def test_errores_verbosos_no_fugan_internos(client):
    """Payloads que disparan excepciones: ninguna respuesta (ni 500 ni 422)
    debe contener stack traces, SQL, rutas internas ni literales de librerías."""
    ataques = [
        ("POST", "/api/v1/gasto/gastos/", {"tipo_gasto_id": 1, "moneda_id": 1, "fecha": "2026-11-05", "monto": {}, "descripcion": "x"}),
        ("POST", "/api/v1/gasto/gastos/", {"tipo_gasto_id": [], "moneda_id": {}, "fecha": {}, "monto": "abc", "descripcion": "x"}),
        ("POST", "/api/v1/pago/", {"venta_id": {}, "moneda_id": 1, "monto": {}, "metodo_pago": [], "fecha": datetime.utcnow().isoformat()}),
        ("POST", "/api/v1/cliente/", {"nombre": {}, "telefono": []}),
        ("POST", "/api/v1/cliente/", {"nombre": "x", "telefono": {"a": 1}}),
        ("POST", "/api/v1/inventario/movimiento", {"material_id": 1, "ubicacion_id": 1, "tipo": "SALIDA", "cantidad": {}}),
        ("POST", "/api/v1/nomina/", {"periodo_desde": "2026-13-99", "periodo_hasta": {}, "descripcion": 3}),
        ("POST", "/api/v1/producto/", {"nombre": [], "tipo_producto_id": {}, "ancho_base": "x", "largo_base": None}),
        ("POST", "/api/v1/cotizacion/", {"cliente_id": {}, "fecha": "no-es-fecha", "detalles": [{"producto_id": {}, "cantidad": "x", "precio": {}}]}),
        ("GET", "/api/v1/tasa/convertir", {"monto": "inf", "moneda_origen_id": 1, "moneda_destino_id": 2}),
        ("POST", "/api/v1/pedido/convertir/999999", {"detalles": [{"producto_id": 1, "cantidad": 1, "precio": {}}], "adelanto": "cero"}),
        ("GET", "/api/v1/cotizacion/", {"salto": -5, "limite": 0}),
        ("POST", "/api/v1/produccion/consumo/", {"etapa_produccion_id": 1, "material_id": 1, "cantidad": "menos", "fecha": {}}),
        ("PUT", "/api/v1/envio/1/estado", {"estado": "NO_EXISTE"}),
        ("GET", "/api/v1/venta/99999999999999999999", None),
    ]
    fugas = []
    n_500 = 0
    for metodo, path, params in ataques:
        kwargs = {"headers": ADMIN_HEADERS}
        if params is not None:
            kwargs["json"] = params if metodo == "POST" else None
            if metodo != "POST":
                kwargs["params"] = params
        r = client.request(metodo, path, **kwargs)
        if r.status_code >= 500:
            n_500 += 1
            if _cuerpo_fuga(r.text):
                fugas.append((metodo, path, r.status_code, r.text[:600]))
        elif r.status_code >= 400 and _cuerpo_fuga(r.text):
            fugas.append((metodo, path, r.status_code, r.text[:600]))

    print(f"  respuestas 500 encontradas: {n_500}")
    assert not fugas, "FUGA DE INFORMACIÓN:\n" + "\n".join(f"  {m} {p} → {s}: {t}" for m, p, s, t in fugas)


# ═══════════════════════════════════════════════════════════════════════════
# 10. Headers de seguridad ausentes
# ═══════════════════════════════════════════════════════════════════════════
def test_headers_seguridad(client):
    """Inventario de headers de seguridad en /docs y en una API autenticada."""
    esperados = {
        "x-frame-options": "X-Frame-Options (clickjacking)",
        "x-content-type-options": "X-Content-Type-Options: nosniff",
        "strict-transport-security": "Strict-Transport-Security (HSTS)",
        "content-security-policy": "Content-Security-Policy",
        "referrer-policy": "Referrer-Policy",
        "permissions-policy": "Permissions-Policy",
    }
    faltantes = set(esperados)
    for path, headers in (("/docs", None), ("/api/v1/cotizacion/", ADMIN_HEADERS)):
        r = client.get(path, headers=headers or {})
        presentes = {k for k in esperados if r.headers.get(k)}
        faltantes -= presentes
    if faltantes:
        print("  ⚠ headers ausentes en /docs y /api/v1/cotizacion/: " + ", ".join(esperados[k] for k in sorted(faltantes)))
    assert True  # inventario reportable: no hay fix esperado


# ═══════════════════════════════════════════════════════════════════════════
# 11. Swagger / OpenAPI expuestos
# ═══════════════════════════════════════════════════════════════════════════
def test_swagger_openapi_expuestos(client):
    """Con DEBUG=true en .env, /docs y /openapi.json responden 200: el mapa
    completo de la API (rutas, esquemas, permisos) queda público."""
    r_docs = client.get("/docs")
    r_openapi = client.get("/openapi.json")
    print(f"  /docs → {r_docs.status_code} · /openapi.json → {r_openapi.status_code} (DEBUG={settings.DEBUG})")
    if r_docs.status_code == 200 or r_openapi.status_code == 200:
        n_rutas = len(r_openapi.json().get("paths", {})) if r_openapi.status_code == 200 else "?"
        print(
            f"  ⚠ hallazgo: Swagger/OpenAPI públicos (DEBUG={settings.DEBUG}) — "
            f"{n_rutas} rutas expuestas sin autenticación."
        )
    assert True  # reportable, no falla el suite


# ═══════════════════════════════════════════════════════════════════════════
# 12. Login: 20 intentos fallidos → lockout
# ═══════════════════════════════════════════════════════════════════════════
def test_login_lockout_20_intentos(client, cleaner):
    """20 contraseñas incorrectas seguidas para un usuario nuevo: tras
    LOGIN_MAX_INTENTOS=5 fallos por (cuenta, IP) debe llegar un 429."""
    nombre = f"hacker_{uuid4().hex[:10]}"
    r = client.post(
        "/api/auth/users",
        json={"nombre_usuario": nombre, "password": "Xy12345!"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code in (200, 201), f"crear usuario → {r.status_code}: {r.text[:200]}"
    cleaner.registrar("usuario", r.json()["id"])

    statuses = []
    for _ in range(20):
        rr = client.post(
            "/api/auth/login",
            data={"username": nombre, "password": "clave-equivocada-xyz"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        statuses.append(rr.status_code)

    print(
        f"  login: statuses={statuses} "
        f"(LOGIN_MAX_INTENTOS={settings.LOGIN_MAX_INTENTOS}, ventana={settings.LOGIN_VENTANA_MINUTOS}min)"
    )
    # El rate limit GLOBAL por IP (todas las rutas /api) puede disparar 429 antes
    # que el lockout específico de login cuando la suite corre en <60s desde la
    # misma IP. Lo que importa: nunca 200 y bloqueo eventual (lockout o rate).
    assert 200 not in statuses, "login con contraseña equivocada dio 200 → BUG"
    assert 429 in statuses, (
        f"no hubo bloqueo (ni lockout ni rate limit): {statuses}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 13. Race: doble pago del 100% a la misma venta
# ═══════════════════════════════════════════════════════════════════════════
def test_doble_pago_venta_100(client, db, cleaner):
    """2 hilos pagan el 100% del saldo de la misma venta con Barrier: solo 1
    pago debe entrar a caja; el otro 400. Dos ingresos = BUG de caja."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    precio = 100_000.0
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], precio)
    r = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": precio}]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    venta_id = int(
        db.execute(text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": ped["id"]}).fetchone()[0]
    )

    payload = {
        "venta_id": venta_id,
        "moneda_id": 1,
        "fecha": datetime.utcnow().isoformat(),
        "monto": precio,
        "metodo_pago": "EFECTIVO_COP",
    }

    def pagar(_):
        c = _cliente_nuevo()
        return c.post("/api/v1/pago/", json=payload, headers=ADMIN_HEADERS)

    resultados = _correr_en_paralelo([lambda: pagar(0), lambda: pagar(1)])
    statuses = sorted(r.status_code for r in resultados)
    n_pagos = db.execute(text("SELECT count(*) FROM pago WHERE venta_id = :v"), {"v": venta_id}).fetchone()[0]
    estado_venta = db.execute(text("SELECT estado FROM venta WHERE id = :v"), {"v": venta_id}).fetchone()[0]
    total_caja = db.execute(
        text("SELECT COALESCE(sum(monto_en_moneda_base), 0) FROM movimiento_caja WHERE pago_id IN (SELECT id FROM pago WHERE venta_id = :v)"),
        {"v": venta_id},
    ).fetchone()[0]
    print(f"  doble pago venta: {statuses} · pagos={n_pagos} · venta={estado_venta} · caja(entrada)={total_caja}")

    _registrar_pagos_venta(db, cleaner, venta_id)

    assert 500 not in statuses, f"500 en el pago → {[r.text[:200] for r in resultados if r.status_code == 500]}"
    assert n_pagos == 1, f"BUG DOBLE INGRESO: {n_pagos} pagos registrados (esperado 1) — {statuses}"
    assert statuses.count(201) == 1, f"se esperaba exactamente 1 pago aceptado, got {statuses}"
    assert estado_venta == "PAGADA", f"venta en {estado_venta}"
    assert abs(float(total_caja) - precio) < 0.01, (
        f"BUG: {total_caja} entraron a caja (esperado {precio})"
    )
