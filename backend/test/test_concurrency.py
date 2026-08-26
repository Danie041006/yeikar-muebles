# -*- coding: utf-8 -*-
"""
test_concurrency.py — Carreras (race conditions) sobre dinero e inventario.

Objetivo: lanzar requests en paralelo (threads) sobre las mismas entidades y
verificar que el estado final respeta las invariantes:

  * dos pagos simultáneos no pueden cobrar más del total de la venta
  * dos conversiones simultáneas de la SAME cotización crean UN solo pedido/venta
  * dos salidas de inventario simultáneas no pueden negativizar el stock
  * dos consumos de producción simultáneos no pueden exceder el stock

Estos tests NO arreglan nada: si una invariante se viola (saldo < 0, stock < 0,
doble pedido) es un BUG de concurrencia y el test debe fallar para reportarlo.

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_concurrency.py -v
"""
import threading
from datetime import datetime

import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_movimiento,
    crear_orden_desde_pedido,
    crear_producto,
)


def run_parallel(fn, args_list):
    """Ejecuta fn(*args) para cada tupla de args_list en un thread propio.

    Todos los threads arrancan juntos (barrier) para maximizar el solape.
    Cada thread hace su propio request contra el mismo TestClient. Devuelve
    (resultados, errores): resultados[i] = fn(*args_list[i]) o None, errores[i]
    = excepción si el thread lanzó.
    """
    n = len(args_list)
    resultados = [None] * n
    errores = [None] * n
    barrier = threading.Barrier(n)

    def tarea(i, *args):
        try:
            if barrier is not None:
                barrier.wait(timeout=30)
            resultados[i] = fn(*args)
        except Exception as e:  # noqa: BLE001 — cualquier fallo del thread se reporta
            errores[i] = e

    threads = [
        threading.Thread(target=tarea, args=(i,) + tuple(a))
        for i, a in enumerate(args_list)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return resultados, errores


# ---------------------------------------------------------------------------
# Helpers locales vía HTTP puro (no tocan el cleaner desde hilos)
# ---------------------------------------------------------------------------
def _post(client, url, payload):
    """POST directo con ADMIN_HEADERS. Devuelve (status, body|text)."""
    r = client.post(url, json=payload, headers=ADMIN_HEADERS)
    body = r.json() if r.status_code in (200, 201) else r.text
    return r.status_code, body


def _convertir_body(producto_id, precio, costo=None):
    return {
        "detalles": [{
            "producto_id": producto_id,
            "cantidad": 1,
            "precio": precio,
            "costo_unitario": costo,
        }],
        "adelanto": None,
    }


def _registrar_resultados_ok(cleaner, resultados, tabla="pago"):
    """Registra en el cleaner los ids devueltos por respuestas 2xx."""
    for resultado in resultados:
        if resultado is None:
            continue
        status, body = resultado
        if status in (200, 201) and isinstance(body, dict) and "id" in body:
            cleaner.registrar(tabla, body["id"])


# ===========================================================================
# TEST 1 — Dos pagos simultáneos no sobrepasan el saldo
# ===========================================================================
def test_dos_pagos_simultaneos_no_sobrepasan_saldo(client, db, cleaner):
    total_venta = 100000.0
    monto_pago = 60000.0

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], total_venta)

    # Convertir cotización → pedido (crea la venta automáticamente)
    body = _convertir_body(producto["id"], total_venta)
    status, pedido = _post(client, f"/api/v1/pedido/convertir/{cot['id']}", body)
    assert status == 201, f"convertir cotización → {status}: {pedido}"
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])

    # Localizar la venta creada (GET /api/v1/venta/ filtrando por pedido)
    r_ventas = client.get(
        "/api/v1/venta/", params={"buscar": cliente["nombre"], "limite": 1000},
        headers=ADMIN_HEADERS,
    )
    assert r_ventas.status_code == 200, f"GET /api/v1/venta/ → {r_ventas.status_code}"
    ventas = [v for v in r_ventas.json() if v["pedido_id"] == pedido["id"]]
    assert len(ventas) == 1, f"ventas para pedido {pedido['id']}: {ventas}"
    venta_id = ventas[0]["id"]
    assert float(ventas[0]["total"]) == pytest.approx(total_venta), (
        f"total venta esperado {total_venta}, se obtuvo {ventas[0]['total']}"
    )
    cleaner.registrar("venta", venta_id)

    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    for d in det.get("detalles", []):
        cleaner.registrar("detalle_venta", d["id"])

    # Dos pagos de 60000 en paralelo a la misma venta
    def do_pago(venta_id_, monto_):
        return _post(client, "/api/v1/pago/", {
            "venta_id": venta_id_,
            "moneda_id": 1,
            "fecha": datetime.utcnow().isoformat(),
            "monto": monto_,
            "metodo_pago": "EFECTIVO_COP",
            "referencia": "pago-concurrente",
        })

    args = [(venta_id, monto_pago), (venta_id, monto_pago)]
    resultados, errores = run_parallel(do_pago, args)
    assert not any(errores), f"errores en threads: {errores}"
    _registrar_resultados_ok(cleaner, resultados, tabla="pago")

    statuses = [s for s, _ in resultados]
    bodies = [b for _, b in resultados]
    print(f"[pagos] statuses={statuses} bodies={bodies}")

    # Invariante clave: A LO SUMO un pago pudo pasar (aunque ambos 201 sería
    # aceptable SOLO si el total pagado final no excede el total).
    exitosos = [s for s in statuses if s in (200, 201)]
    assert len(exitosos) == 1, (
        f"se esperaba EXACTAMENTE un pago exitoso; statuses reales: {statuses}"
    )
    assert any(s in (400, 409) for s in statuses), (
        f"se esperaba el segundo pago rechazado (400/409); statuses reales: {statuses}"
    )

    # Estado final: saldo_pendiente >= 0 y total_pagado <= total
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    total_pagado = float(det["total_pagado"])
    saldo_pendiente = float(det["saldo_pendiente"])
    total = float(det["total"])
    print(f"[pagos] final: total={total} total_pagado={total_pagado} saldo_pendiente={saldo_pendiente}")

    assert total_pagado <= total + 0.01, (
        f"INVARIANTE VIOLADA: se pagaron {total_pagado} sobre un total de {total}"
    )
    assert saldo_pendiente >= -0.01, (
        f"INVARIANTE VIOLADA: saldo pendiente negativo ({saldo_pendiente}) para total {total}"
    )
    assert saldo_pendiente == pytest.approx(total_venta - monto_pago, abs=0.01), (
        f"saldo final esperado {total_venta - monto_pago}, se obtuvo {saldo_pendiente}"
    )
    assert total_pagado == pytest.approx(monto_pago, abs=0.01), (
        f"total pagado esperado {monto_pago}, se obtuvo {total_pagado}"
    )


# ===========================================================================
# TEST 2 — Dos conversiones simultáneas de la misma cotización
# ===========================================================================
def test_dos_conversiones_simultaneas_mismo_pedido(client, db, cleaner):
    precio = 50000.0

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio)

    # Dos conversiones idénticas en paralelo
    def do_convertir(cot_id, producto_id):
        return _post(client, f"/api/v1/pedido/convertir/{cot_id}", _convertir_body(producto_id, precio))

    args = [(cot["id"], producto["id"]), (cot["id"], producto["id"])]
    resultados, errores = run_parallel(do_convertir, args)
    assert not any(errores), f"errores en threads: {errores}"

    statuses = [s for s, _ in resultados]
    bodies = [b for _, b in resultados]
    print(f"[convertir] statuses={statuses} bodies={bodies}")
    for body in bodies:
        if isinstance(body, dict) and "id" in body:
            cleaner.registrar("pedido", body["id"])
            for d in body.get("detalles", []):
                cleaner.registrar("detalle_pedido", d["id"])

    # Una → 201, la otra → 4xx (400/409)
    assert statuses.count(201) == 1, (
        f"se esperaba UNA conversión 201; statuses reales: {statuses}"
    )
    assert any(s in (400, 409) for s in statuses), (
        f"se esperaba la segunda conversión rechazada (400/409); statuses reales: {statuses}"
    )

    # EXACTAMENTE un pedido para esa cotización (vía API y vía BD)
    r_pedidos = client.get(
        "/api/v1/pedido/",
        params={"solo_mes_actual": "false", "buscar": cot["observaciones"], "limite": 1000},
        headers=ADMIN_HEADERS,
    )
    assert r_pedidos.status_code == 200, f"GET /api/v1/pedido/ → {r_pedidos.status_code}"
    pedidos_api = [p for p in r_pedidos.json() if p["cotizacion_id"] == cot["id"]]
    n_pedidos_api = len(pedidos_api)

    n_pedidos_db = db.execute(
        text("SELECT COUNT(*) FROM pedido WHERE cotizacion_id=:c"), {"c": cot["id"]}
    ).scalar()
    print(f"[convertir] pedidos creados: API={n_pedidos_api} BD={n_pedidos_db}")

    assert n_pedidos_api == 1, (
        f"INVARIANTE VIOLADA: {n_pedidos_api} pedidos para la cotización {cot['id']} (vía API)"
    )
    assert n_pedidos_db == 1, (
        f"INVARIANTE VIOLADA: {n_pedidos_db} pedidos para la cotización {cot['id']} (vía BD)"
    )

    # EXACTAMENTE una venta: la creada por la conversión exitosa
    pedido_id = pedidos_api[0]["id"]
    n_ventas_db = db.execute(
        text("SELECT COUNT(*) FROM venta WHERE pedido_id=:p"), {"p": pedido_id}
    ).scalar()
    print(f"[convertir] ventas para pedido {pedido_id}: {n_ventas_db}")
    assert n_ventas_db == 1, (
        f"INVARIANTE VIOLADA: {n_ventas_db} ventas para el pedido {pedido_id} (se esperaba 1)"
    )
    venta_id = db.execute(
        text("SELECT id FROM venta WHERE pedido_id=:p"), {"p": pedido_id}
    ).scalar()
    cleaner.registrar("venta", venta_id)
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    for d in det.get("detalles", []):
        cleaner.registrar("detalle_venta", d["id"])


# ===========================================================================
# TEST 3 — Dos salidas simultáneas no negativizan el stock
# ===========================================================================
def test_dos_salidas_simultaneas_no_negativizan_stock(client, db, cleaner):
    material = crear_material(client, cleaner)

    # Entrada de 10 (helper del conftest, registra en el cleaner)
    st, body = crear_movimiento(client, cleaner, material["id"], "ENTRADA", 10)
    assert st.status_code in (200, 201), f"ENTRADA → {st.status_code}: {body}"

    # Dos SALIDAS de 7 en paralelo
    def do_salida(material_id, cantidad):
        return _post(client, "/api/v1/inventario/movimiento", {
            "material_id": material_id,
            "ubicacion_id": 1,
            "tipo": "SALIDA",
            "cantidad": cantidad,
        })

    args = [(material["id"], 7), (material["id"], 7)]
    resultados, errores = run_parallel(do_salida, args)
    assert not any(errores), f"errores en threads: {errores}"

    statuses = [s for s, _ in resultados]
    bodies = [b for _, b in resultados]
    print(f"[salidas] statuses={statuses} bodies={bodies}")

    # Registrar ids generados por los hilos (limpieza manual)
    _registrar_resultados_ok(cleaner, resultados, tabla="movimiento_inventario")
    inv_row = db.execute(text(
        "SELECT id FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).fetchone()
    if inv_row:
        cleaner.registrar("inventario", inv_row[0])

    exitosos = [s for s in statuses if s in (200, 201)]
    assert len(exitosos) == 1, (
        f"se esperaba EXACTAMENTE una salida exitosa; statuses reales: {statuses}"
    )
    assert any(s in (400, 409) for s in statuses), (
        f"se esperaba la segunda salida rechazada (400/409); statuses reales: {statuses}"
    )

    stock = db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).scalar()
    stock = float(stock)
    print(f"[salidas] stock final={stock}")
    assert stock >= 0, f"INVARIANTE VIOLADA: stock negativo ({stock})"
    assert stock == pytest.approx(3.0), f"stock final esperado 3.0, se obtuvo {stock}"


# ===========================================================================
# TEST 4 — Consumos simultáneos de producción no exceden el stock
# ===========================================================================
def test_consumos_simultaneos_no_exceden_stock(client, db, cleaner):
    from conftest import crear_movimiento

    precio = 50000.0

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    material = crear_material(client, cleaner, costo_base=1000.0)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio)

    # Pedido (COTIZADO) → orden de producción → etapa real
    status, pedido = _post(client, f"/api/v1/pedido/convertir/{cot['id']}",
                           _convertir_body(producto["id"], precio))
    assert status == 201, f"convertir → {status}: {pedido}"
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    detalle_pedido_id = pedido["detalles"][0]["id"]

    # La conversión auto-genera una factura (venta + detalle_venta): registrarla
    # en el cleaner para que la limpieza no falle por FK (venta → pedido RESTRICT).
    r_ventas = client.get(
        "/api/v1/venta/", params={"buscar": cliente["nombre"], "limite": 1000},
        headers=ADMIN_HEADERS,
    )
    venta = next((v for v in r_ventas.json() if v["pedido_id"] == pedido["id"]), None)
    assert venta is not None, "La conversión debe auto-generar la factura (venta)"
    cleaner.registrar("venta", venta["id"])
    for d in client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json().get("detalles", []):
        cleaner.registrar("detalle_venta", d["id"])

    orden = crear_orden_desde_pedido(client, cleaner, detalle_pedido_id)
    st, etapa = _post(client, "/api/v1/produccion/etapa/", {
        "orden_produccion_id": orden["id"],
        "area_id": 1,
        "empleado_responsable_id": 1,
        "estado": "ASIGNADA",
        "observaciones": "etapa-concurrencia",
    })
    assert st == 201, f"crear etapa → {st}: {etapa}"
    cleaner.registrar("etapa_produccion", etapa["id"])
    # Máquina de estados: los consumos exigen la etapa EN_PROCESO
    r_ep = client.put(
        f"/api/v1/produccion/etapa/{etapa['id']}/estado",
        params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS,
    )
    assert r_ep.status_code == 200, f"etapa EN_PROCESO → {r_ep.status_code}: {r_ep.text}"

    # Stock de 10 para el material
    st, body = crear_movimiento(client, cleaner, material["id"], "ENTRADA", 10)
    assert st.status_code in (200, 201), f"ENTRADA → {st.status_code}: {body}"

    # Dos consumos de 7 en paralelo sobre la misma etapa
    def do_consumo(etapa_id, material_id, cantidad):
        return _post(client, "/api/v1/produccion/consumo/", {
            "etapa_produccion_id": etapa_id,
            "material_id": material_id,
            "cantidad": cantidad,
            "solicitante_empleado_id": 1,
            "fecha": datetime.utcnow().isoformat(),
            "observaciones": "consumo-concurrente",
        })

    args = [(etapa["id"], material["id"], 7), (etapa["id"], material["id"], 7)]
    resultados, errores = run_parallel(do_consumo, args)
    assert not any(errores), f"errores en threads: {errores}"

    statuses = [s for s, _ in resultados]
    bodies = [b for _, b in resultados]
    print(f"[consumos] statuses={statuses} bodies={bodies}")

    _registrar_resultados_ok(cleaner, resultados, tabla="consumo_material")

    # Movimientos de inventario generados por producción (referencia al consumo)
    consumo_ids = [
        b["id"] for (s, b) in resultados if s in (200, 201) and isinstance(b, dict)
    ]
    if consumo_ids:
        mvs = db.execute(text(
            "SELECT id FROM movimiento_inventario WHERE referencia_tipo='produccion' "
            "AND referencia_id IN :ids"
        ), {"ids": tuple(consumo_ids)}).fetchall()
        for (mid,) in mvs:
            cleaner.registrar("movimiento_inventario", mid)
    inv_row = db.execute(text(
        "SELECT id FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).fetchone()
    if inv_row:
        cleaner.registrar("inventario", inv_row[0])

    # Gasto automático por consumo
    cleaner.registrar_gastos_like(db, f"Consumo {material['nombre']}")

    exitosos = [s for s in statuses if s in (200, 201)]
    assert len(exitosos) == 1, (
        f"se esperaba EXACTAMENTE un consumo exitoso; statuses reales: {statuses}"
    )
    assert any(s in (400, 409) for s in statuses), (
        f"se esperaba el segundo consumo rechazado (400/409); statuses reales: {statuses}"
    )

    stock = float(db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).scalar())
    print(f"[consumos] stock final={stock} consumos_ok={len(consumo_ids)}")
    assert stock >= 0, f"INVARIANTE VIOLADA: stock negativo ({stock})"
    assert stock == pytest.approx(3.0), f"stock final esperado 3.0, se obtuvo {stock}"
    assert len(consumo_ids) == 1, f"se esperaba UN consumo, se crearon {len(consumo_ids)}"