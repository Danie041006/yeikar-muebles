# -*- coding: utf-8 -*-
"""
test_production_risks.py — Riesgos del flujo de producción y costeo.

Riesgos auditados (hallazgos C1–C6 del análisis de código):

  C1. Escalado muerto: un producto CON receta (producto_material) toma el branch
      temprano de `calcular_costo_producto` y NUNCA aplica tipo_escala
      (LINEAL/AREA/POR_RANGO/ESPACIADO) — la cantidad_calculada queda igual a
      cantidad_base sin importar las dimensiones nuevas.
  C2. Finalizar sin etapas: una orden sin NINGUNA etapa se puede finalizar.
  C3. Pedido TERMINADO con líneas sin producir: si solo una línea del pedido
      tiene orden de producción, finalizarla marca el pedido completo TERMINADO
      y dispara el envío automático aunque las demás líneas no se produzcan.
  C4. Costo pisado: finalizar re-calculando el costo con ganancia 0% y gastos 0,
      pisando el costo ya calculado manualmente por el supervisor.
  C5. Consumo sin validar etapa: crear_consumo_material no valida que la etapa
      exista ni su estado (acepta consumo en etapa PAUSADA/COMPLETADA).
  C6. Stock sin reversa: eliminar_consumo_material borra el consumo pero NO
      repone el stock (ni el gasto), dejando el inventario permanentemente
      descontado.

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_production_risks.py -v
"""
from decimal import Decimal
from datetime import datetime

import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_movimiento,
    crear_orden_desde_pedido,
    crear_producto,
    crear_receta,
    registrar_inventario_de_material,
    registrar_venta_de_pedido,
)


# ---------------------------------------------------------------------------
# C1 — Escalado por tipo_escala NUNCA aplica para productos con receta
# ---------------------------------------------------------------------------
def test_c1_escalado_lineal_ignorado_con_receta(client, cleaner, db):
    """Producto con receta LINEAL: largo 2x debe duplicar la cantidad. Si
    cantidad_calculada == cantidad_base → el escalado está muerto."""
    producto = crear_producto(client, cleaner)  # ancho_base 1.60, largo_base 1.90
    material = crear_material(client, cleaner, costo_base=5000.0)

    crear_receta(client, cleaner, producto["id"], material["id"],
                 cantidad_base=2.0, tipo_escala="LINEAL", seccion="EBANISTERIA")

    # Largo doble (3.80 vs 1.90) → LINEAL debe dar 4.0
    r = client.get(
        f"/api/v1/producto/{producto['id']}/calcular-precio",
        params={"ancho": 1.60, "largo": 3.80},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"calcular-precio → {r.status_code}: {r.text}"
    materiales = r.json().get("materiales", [])

    assert materiales, f"Se esperaba la receta en la respuesta: {r.json()}"
    for m in materiales:
        if m["material_id"] == material["id"]:
            cant_calculada = m["cantidad_calculada"]
            assert cant_calculada == pytest.approx(4.0), (
                f"Riesgo C1 (escalado muerto): material LINEAL con largo 2x "
                f"debería calcular 4.0, pero cantidad_calculada = {cant_calculada}"
            )


def test_c1_escalado_por_rango_ignorado_con_receta(client, cleaner, db):
    """POR_RANGO con rangos [0-2]=1, >2=5: largo 3.0 debe dar 5.0."""
    producto = crear_producto(client, cleaner)
    material = crear_material(client, cleaner, costo_base=5000.0)

    crear_receta(client, cleaner, producto["id"], material["id"],
                 cantidad_base=1.0, tipo_escala="POR_RANGO", seccion="EBANISTERIA")

    # Guardar los rangos directamente en BD (el helper no los expone)
    pm_id = db.execute(text(
        "SELECT id FROM producto_material WHERE producto_id=:p AND material_id=:m"
    ), {"p": producto["id"], "m": material["id"]}).scalar()
    db.execute(text(
        "UPDATE producto_material SET rangos=:r WHERE id=:i"
    ), {"r": '[{"max": 2.0, "cantidad": 1.0}, {"max": 99.0, "cantidad": 5.0}]',
        "i": pm_id})
    db.commit()

    r = client.get(
        f"/api/v1/producto/{producto['id']}/calcular-precio",
        params={"ancho": 1.60, "largo": 3.0},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"calcular-precio → {r.status_code}: {r.text}"
    for m in r.json().get("materiales", []):
        if m["material_id"] == material["id"]:
            assert m["cantidad_calculada"] == pytest.approx(5.0), (
                f"Riesgo C1: POR_RANGO largo 3.0 debe dar 5.0, dio "
                f"{m['cantidad_calculada']}"
            )


# ---------------------------------------------------------------------------
# C2 — Finalizar orden sin ninguna etapa
# ---------------------------------------------------------------------------
def test_c2_no_debe_finalizar_orden_sin_etapas(client, cleaner, db):
    """Una orden sin etapas no debería poder FINALIZARSE: sería producción
    terminada sin haber producido nada."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    detalle_id = pedido["detalles"][0]["id"]

    orden = crear_orden_desde_pedido(client, cleaner, detalle_id)
    assert orden["estado"] == "PENDIENTE"

    r = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado", params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    assert r.status_code in (400, 422), (
        f"Riesgo C2: finalizar orden SIN etapas debería ser rechazado (400/422), "
        f"fue {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# C3 — Pedido TERMINADO con líneas sin producir
# ---------------------------------------------------------------------------
def test_c3_pedido_terminado_con_lineas_sin_producir(client, cleaner, db):
    """Pedido de 2 líneas, solo 1 con orden de producción: finalizar esa orden
    NO debe marcar todo el pedido TERMINADO ni crear envío."""
    cliente = crear_cliente(client, cleaner)
    producto1 = crear_producto(client, cleaner)
    producto2 = crear_producto(client, cleaner)
    # La cotización debe incluir AMBOS productos: el pedido copia exactamente
    # los renglones cotizados (la conversión lo valida desde la fase de fixes).
    r_cot = client.post("/api/v1/cotizacion/", json={
        "cliente_id": cliente["id"],
        "fecha": str(datetime.today().date()),
        "estado": "BORRADOR",
        "total_estimado": 200000,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": _uniq("cot2"),
        "detalles": [
            {"producto_id": producto1["id"], "cantidad": 1, "precio": 100000, "ancho": 1.60, "largo": 1.90},
            {"producto_id": producto2["id"], "cantidad": 1, "precio": 100000, "ancho": 1.60, "largo": 1.90},
        ],
    }, headers=ADMIN_HEADERS)
    assert r_cot.status_code == 201, f"cotizacion 2 líneas → {r_cot.status_code}: {r_cot.text}"
    cot = r_cot.json()
    cleaner.registrar("cotizacion", cot["id"])

    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [
            {"producto_id": producto1["id"], "cantidad": 1, "precio": 100000,
             "costo_unitario": 1000, "porcentaje_ganancia": 40},
            {"producto_id": producto2["id"], "cantidad": 1, "precio": 100000,
             "costo_unitario": 1000, "porcentaje_ganancia": 40},
        ], "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    assert len(pedido["detalles"]) == 2, f"Se esperaban 2 líneas: {pedido['detalles']}"

    detalle1 = pedido["detalles"][0]["id"]
    detalle2 = pedido["detalles"][1]["id"]

    # Solo la línea 1 tiene orden de producción
    orden = crear_orden_desde_pedido(client, cleaner, detalle1)
    n_ordenes_linea2 = db.execute(text(
        "SELECT COUNT(*) FROM orden_produccion WHERE detalle_pedido_id=:d"
    ), {"d": detalle2}).scalar()
    assert n_ordenes_linea2 == 0, "Precondición: la línea 2 no debe tener orden"

    # Finalizar la única orden
    r = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado", params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 400), f"finalizar → {r.status_code}: {r.text}"

    if r.status_code == 200:
        pedido_db = db.execute(text(
            "SELECT estado FROM pedido WHERE id=:p"
        ), {"p": pedido["id"]}).scalar()
        n_envios = db.execute(text(
            "SELECT COUNT(*) FROM envio WHERE pedido_id=:p"
        ), {"p": pedido["id"]}).scalar()
        assert pedido_db != "TERMINADO", (
            f"Riesgo C3: pedido TERMINADO con una línea sin orden de producción"
        )
        assert n_envios == 0, (
            f"Riesgo C3: envío automático creado con líneas sin producir"
        )


# ---------------------------------------------------------------------------
# C4 — Finalizar pisa el costo ya calculado (ganancia/gastos → 0)
# ---------------------------------------------------------------------------
def test_c4_finalizar_no_pisa_costo_calculado(client, cleaner, db):
    """El supervisor calcula el costo con 40% ganancia; finalizar la orden no
    debe reescribirlo con 0%."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    detalle_id = pedido["detalles"][0]["id"]

    orden = crear_orden_desde_pedido(client, cleaner, detalle_id)

    # Etapa + consumo para que el costo tenga base material
    st, etapa = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA",
        "observaciones": "c4"},
        headers=ADMIN_HEADERS), None
    etapa_id = None
    if st.status_code == 201:
        etapa_id = st.json()["id"]
        cleaner.registrar("etapa_produccion", st.json()["id"])

    material = crear_material(client, cleaner, costo_base=2000.0)
    st_mov, _ = crear_movimiento(client, cleaner, material["id"], "ENTRADA", 100)
    assert st_mov.status_code in (200, 201), f"ENTRADA → {st_mov.status_code}"
    if etapa_id is not None:
        r_cons = client.post("/api/v1/produccion/consumo/", json={
            "etapa_produccion_id": etapa_id, "material_id": material["id"],
            "cantidad": 10, "fecha": "2026-08-05T00:00:00",
            "observaciones": "c4-consumo"},
            headers=ADMIN_HEADERS)
        if r_cons.status_code == 201:
            cleaner.registrar("consumo_material", r_cons.json()["id"])
            cleaner.registrar_gastos_like(db, f"Consumo {material['nombre']}")

    # Calcular costo con 40% de ganancia
    r_cost = client.post(f"/api/v1/produccion/costo/calcular/{orden['id']}",
                         json={"ganancia_porcentaje": 40.0, "costo_gastos": 0.0},
                         headers=ADMIN_HEADERS)
    assert r_cost.status_code == 200, f"calcular costo → {r_cost.status_code}: {r_cost.text}"
    ganancia_antes = r_cost.json().get("ganancia_porcentaje")
    assert ganancia_antes == pytest.approx(40.0), f"Precondición: ganancia 40, fue {ganancia_antes}"

    # Finalizar
    r = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado", params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    if r.status_code != 200:
        pytest.skip(f"finalizar rechazado ({r.status_code}) — inválido para C4")

    costo_final = client.get(f"/api/v1/produccion/costo/{orden['id']}",
                             headers=ADMIN_HEADERS)
    assert costo_final.status_code == 200, f"GET costo → {costo_final.status_code}"
    ganancia_despues = costo_final.json().get("ganancia_porcentaje")
    assert ganancia_despues == pytest.approx(40.0), (
        f"Riesgo C4: finalizar pisó el costo — ganancia 40% → {ganancia_despues}%"
    )
    registrar_inventario_de_material(db, cleaner, material["id"])


# ---------------------------------------------------------------------------
# C5 — Consumo sobre etapa inexistente / en estado no productivo
# ---------------------------------------------------------------------------
def test_c5_consumo_etapa_inexistente(client, cleaner, db):
    """Consumo con etapa_produccion_id inexistente debe ser 400/404, no 500."""
    material = crear_material(client, cleaner, costo_base=2000.0)
    st_mov, _ = crear_movimiento(client, cleaner, material["id"], "ENTRADA", 100)
    assert st_mov.status_code in (200, 201), f"ENTRADA → {st_mov.status_code}"

    r = client.post("/api/v1/produccion/consumo/", json={
        "etapa_produccion_id": 99999999, "material_id": material["id"],
        "cantidad": 5, "fecha": "2026-08-05T00:00:00", "observaciones": "c5"},
        headers=ADMIN_HEADERS)
    assert r.status_code in (400, 404, 422), (
        f"Riesgo C5: consumo con etapa inexistente debería ser 400/404/422, "
        f"fue {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# C6 — Eliminar consumo NO repone stock (ni revierte el gasto)
# ---------------------------------------------------------------------------
def test_c6_eliminar_consumo_revierte_stock(client, cleaner, db):
    """Al eliminar un consumo, el stock debe reponerse (movimiento inverso)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    detalle_id = pedido["detalles"][0]["id"]

    orden = crear_orden_desde_pedido(client, cleaner, detalle_id)
    r_etapa = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA",
        "observaciones": "c6"},
        headers=ADMIN_HEADERS)
    assert r_etapa.status_code == 201, f"etapa → {r_etapa.status_code}: {r_etapa.text}"
    etapa_id = r_etapa.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)
    # Máquina de estados: los consumos exigen la etapa EN_PROCESO
    r_ep = client.put(
        f"/api/v1/produccion/etapa/{etapa_id}/estado",
        params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS,
    )
    assert r_ep.status_code == 200, f"etapa EN_PROCESO → {r_ep.status_code}: {r_ep.text}"

    material = crear_material(client, cleaner, costo_base=2000.0)
    st_mov, _ = crear_movimiento(client, cleaner, material["id"], "ENTRADA", 100)
    assert st_mov.status_code in (200, 201), f"ENTRADA → {st_mov.status_code}"
    stock_antes = float(db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).scalar())

    r_cons = client.post("/api/v1/produccion/consumo/", json={
        "etapa_produccion_id": etapa_id, "material_id": material["id"],
        "cantidad": 10, "fecha": "2026-08-05T00:00:00", "observaciones": "c6",
        "solicitante_empleado_id": 1},
        headers=ADMIN_HEADERS)
    assert r_cons.status_code == 201, f"consumo → {r_cons.status_code}: {r_cons.text}"
    consumo_id = r_cons.json()["id"]
    cleaner.registrar("consumo_material", consumo_id)
    cleaner.registrar_gastos_like(db, f"Consumo {material['nombre']}")

    stock_con_consumo = float(db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).scalar())
    assert stock_con_consumo == pytest.approx(stock_antes - 10)

    # Eliminar el consumo → el stock DEBE reponerse
    r_del = client.delete(f"/api/v1/produccion/consumo/{consumo_id}",
                          headers=ADMIN_HEADERS)
    assert r_del.status_code in (200, 204), f"DELETE consumo → {r_del.status_code}: {r_del.text}"

    stock_final = float(db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).scalar())
    assert stock_final == pytest.approx(stock_antes), (
        f"Riesgo C6: eliminar consumo no repuso stock — esperado {stock_antes}, "
        f"quedó {stock_final}"
    )
    registrar_inventario_de_material(db, cleaner, material["id"])


# ---------------------------------------------------------------------------
# C7 — pasar-a-area a un área con etapa activa (doble consumo / doble pago)
# ---------------------------------------------------------------------------
def test_c7_pasar_a_area_con_etapa_activa_rechazado(client, cleaner, db):
    """Dos etapas activas de la misma área en la misma orden permitían doble
    consumo de material y doble pago destajo. pasar-a-area debe rechazarlo."""
    areas = [r[0] for r in db.execute(text("SELECT id FROM area ORDER BY id LIMIT 3"))]
    assert len(areas) >= 2, f"Se necesitan al menos 2 áreas: {areas}"
    area1, area2 = areas[0], areas[1]

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])

    r1 = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": area1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c7-a"},
        headers=ADMIN_HEADERS)
    assert r1.status_code == 201, f"etapa área1 → {r1.status_code}: {r1.text}"
    etapa1 = r1.json()
    cleaner.registrar("etapa_produccion", etapa1["id"])

    r2 = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": area2,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c7-b"},
        headers=ADMIN_HEADERS)
    assert r2.status_code == 201, f"etapa área2 → {r2.status_code}: {r2.text}"
    etapa2 = r2.json()
    cleaner.registrar("etapa_produccion", etapa2["id"])

    # Pasar etapa1 → área2 donde YA hay una etapa activa → 400
    r = client.post(f"/api/v1/produccion/etapa/{etapa1['id']}/pasar-a-area", json={
        "area_id": area2, "empleado_responsable_id": 1,
        "empleados_adicionales_ids": []}, headers=ADMIN_HEADERS)
    assert r.status_code == 400, (
        f"Riesgo C7: pasar-a-area a un área con etapa activa debería ser 400, "
        f"fue {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# C8 — fecha_fin de pasar-a-area en hora LOCAL (nómina del período)
# ---------------------------------------------------------------------------
def test_c8_pasar_a_area_fecha_fin_hora_local(client, cleaner, db):
    """pasar-a-area usaba datetime.utcnow(): en Colombia (UTC−5) una etapa
    completada de noche quedaba fuera del período de nómina destajo."""
    from datetime import datetime, timedelta
    areas = [r[0] for r in db.execute(text("SELECT id FROM area ORDER BY id LIMIT 3"))]
    assert len(areas) >= 2, f"Se necesitan al menos 2 áreas: {areas}"
    area1, area2 = areas[0], areas[1]

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])

    r1 = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": area1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c8"},
        headers=ADMIN_HEADERS)
    assert r1.status_code == 201, f"etapa → {r1.status_code}: {r1.text}"
    etapa1 = r1.json()
    cleaner.registrar("etapa_produccion", etapa1["id"])
    r_ep = client.put(
        f"/api/v1/produccion/etapa/{etapa1['id']}/estado",
        params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS,
    )
    assert r_ep.status_code == 200, f"EN_PROCESO → {r_ep.status_code}: {r_ep.text}"

    antes = datetime.now()
    r = client.post(f"/api/v1/produccion/etapa/{etapa1['id']}/pasar-a-area", json={
        "area_id": area2, "empleado_responsable_id": 1,
        "empleados_adicionales_ids": []}, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pasar-a-area → {r.status_code}: {r.text}"
    nueva = r.json()
    cleaner.registrar("etapa_produccion", nueva["id"])
    despues = datetime.now()

    r_ver = client.get(f"/api/v1/produccion/etapa/{etapa1['id']}", headers=ADMIN_HEADERS)
    assert r_ver.status_code == 200, f"ver etapa → {r_ver.status_code}: {r_ver.text}"
    fecha_fin = datetime.fromisoformat(r_ver.json()["fecha_fin"])
    assert antes - timedelta(minutes=5) <= fecha_fin <= despues + timedelta(minutes=5), (
        f"Riesgo C8: fecha_fin {fecha_fin} no está en hora local (debería ser "
        f"≈ {antes.isoformat()} — utcnow() la correría 5h hacia adelante)"
    )


# ---------------------------------------------------------------------------
# C9 — Mano de obra en etapa no productiva → 400 (no 500)
# ---------------------------------------------------------------------------
def test_c9_mano_obra_etapa_no_en_proceso_es_400(client, cleaner, db):
    """registrar_mano_obra en etapa ASIGNADA devolvía 500 (ValueError sin
    capturar). Debe ser 400."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])

    r_etapa = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c9"},
        headers=ADMIN_HEADERS)
    assert r_etapa.status_code == 201, f"etapa → {r_etapa.status_code}: {r_etapa.text}"
    etapa_id = r_etapa.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)

    r = client.post("/api/v1/produccion/mano-obra/", json={
        "etapa_produccion_id": etapa_id, "empleado_id": 1,
        "monto": 50000, "porcentaje_recargo": 0.0},
        headers=ADMIN_HEADERS)
    assert r.status_code == 400, (
        f"Riesgo C9: mano de obra en etapa ASIGNADA debe ser 400, "
        f"fue {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# C10 — PUTs genéricos NO cambian estado (bypass de la máquina de estados)
# ---------------------------------------------------------------------------
def test_c10_put_generico_no_acepta_estado(client, cleaner, db):
    """actualizar_orden/actualizar_etapa aceptaban `estado` libre y saltaban la
    máquina de estados (FINALIZADA sin costos, sin sync del pedido)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])

    r_etapa = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c10"},
        headers=ADMIN_HEADERS)
    assert r_etapa.status_code == 201, f"etapa → {r_etapa.status_code}: {r_etapa.text}"
    etapa_id = r_etapa.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)

    r_ord = client.put(f"/api/v1/produccion/orden/{orden['id']}",
                       json={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    # Pydantic ignora campos extra: la petición responde 200 pero el estado NO
    # cambia (el bypass quedó cerrado al quitar `estado` del schema de update).
    assert r_ord.status_code == 200, f"PUT /orden/ → {r_ord.status_code}: {r_ord.text}"
    estado_orden = db.execute(text(
        "SELECT estado FROM orden_produccion WHERE id=:o"
    ), {"o": orden["id"]}).scalar()
    # Crear la primera etapa ya la puso EN_PRODUCCION; el PUT no debe cambiarla.
    assert estado_orden == "EN_PRODUCCION", (
        f"Riesgo C10: PUT /orden/ cambió el estado a {estado_orden} sin pasar "
        f"por la máquina de estados ni calcular costos"
    )
    r_etp = client.put(f"/api/v1/produccion/etapa/{etapa_id}",
                       json={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS)
    assert r_etp.status_code == 200, f"PUT /etapa/ → {r_etp.status_code}: {r_etp.text}"
    estado_etapa = db.execute(text(
        "SELECT estado FROM etapa_produccion WHERE id=:e"
    ), {"e": etapa_id}).scalar()
    assert estado_etapa == "ASIGNADA", (
        f"Riesgo C10: PUT /etapa/ cambió el estado a {estado_etapa} sin validar "
        f"la transición"
    )


# ---------------------------------------------------------------------------
# C11 — Eliminar consumo revierte el gasto automático (marcador exacto)
# ---------------------------------------------------------------------------
def test_c11_eliminar_consumo_revierte_gasto(client, cleaner, db):
    """El gasto auto-generado por un consumo debe borrarse al eliminar el
    consumo (antes el match por float podía fallar dejando gastos fantasma)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])

    r_etapa = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c11"},
        headers=ADMIN_HEADERS)
    assert r_etapa.status_code == 201, f"etapa → {r_etapa.status_code}: {r_etapa.text}"
    etapa_id = r_etapa.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)
    r_ep = client.put(f"/api/v1/produccion/etapa/{etapa_id}/estado",
                      params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r_ep.status_code == 200, f"EN_PROCESO → {r_ep.status_code}: {r_ep.text}"

    material = crear_material(client, cleaner, costo_base=2000.0)
    st_mov, _ = crear_movimiento(client, cleaner, material["id"], "ENTRADA", 100)
    assert st_mov.status_code in (200, 201), f"ENTRADA → {st_mov.status_code}"

    r_cons = client.post("/api/v1/produccion/consumo/", json={
        "etapa_produccion_id": etapa_id, "material_id": material["id"],
        "cantidad": 10, "fecha": "2026-08-05T00:00:00", "observaciones": "c11",
        "solicitante_empleado_id": 1},
        headers=ADMIN_HEADERS)
    assert r_cons.status_code == 201, f"consumo → {r_cons.status_code}: {r_cons.text}"
    consumo_id = r_cons.json()["id"]
    cleaner.registrar("consumo_material", consumo_id)

    n_gastos = db.execute(text(
        "SELECT COUNT(*) FROM gasto WHERE observaciones LIKE :pat"
    ), {"pat": f"%[consumo {consumo_id}]%"}).scalar()
    assert n_gastos == 1, f"Precondición: 1 gasto con marcador, hay {n_gastos}"

    r_del = client.delete(f"/api/v1/produccion/consumo/{consumo_id}",
                          headers=ADMIN_HEADERS)
    assert r_del.status_code in (200, 204), f"DELETE consumo → {r_del.status_code}: {r_del.text}"

    n_gastos_final = db.execute(text(
        "SELECT COUNT(*) FROM gasto WHERE observaciones LIKE :pat"
    ), {"pat": f"%[consumo {consumo_id}]%"}).scalar()
    assert n_gastos_final == 0, (
        f"Riesgo C11: eliminar consumo dejó el gasto automático en el P&L "
        f"({n_gastos_final} gastos con marcador)"
    )
    registrar_inventario_de_material(db, cleaner, material["id"])


# ---------------------------------------------------------------------------
# C12 — Retrabajo: etapa recreada en área completada NO paga destajo
# ---------------------------------------------------------------------------
def test_c12_retrabajo_marcado_y_fuera_de_nomina(client, cleaner, db):
    """Re-crear una etapa en un área ya COMPLETADA de la misma orden marca
    es_retrabajo=True (la nómina destajo las filtra)."""
    areas = [r[0] for r in db.execute(text("SELECT id FROM area ORDER BY id LIMIT 3"))]
    assert len(areas) >= 2, f"Se necesitan al menos 2 áreas: {areas}"
    area1, area2 = areas[0], areas[1]

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])

    r1 = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": area1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c12"},
        headers=ADMIN_HEADERS)
    assert r1.status_code == 201, f"etapa1 → {r1.status_code}: {r1.text}"
    etapa1 = r1.json()
    cleaner.registrar("etapa_produccion", etapa1["id"])
    assert etapa1.get("es_retrabajo") is False, "Primera etapa no puede ser retrabajo"

    # Completar área 1 (la máquina exige pasar por EN_PROCESO)
    r_ep1 = client.put(f"/api/v1/produccion/etapa/{etapa1['id']}/estado",
                       params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r_ep1.status_code == 200, f"EN_PROCESO → {r_ep1.status_code}: {r_ep1.text}"
    r_c = client.put(f"/api/v1/produccion/etapa/{etapa1['id']}/estado",
                     params={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS)
    assert r_c.status_code == 200, f"COMPLETADA → {r_c.status_code}: {r_c.text}"

    # Re-crear etapa en área 1 (ya completada) → retrabajo
    r2 = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": area1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c12-retrabajo"},
        headers=ADMIN_HEADERS)
    assert r2.status_code == 201, f"etapa retrabajo → {r2.status_code}: {r2.text}"
    etapa_ret = r2.json()
    cleaner.registrar("etapa_produccion", etapa_ret["id"])
    assert etapa_ret.get("es_retrabajo") is True, (
        f"Riesgo C12: etapa recreada en área completada debe ser es_retrabajo=True, "
        f"fue {etapa_ret.get('es_retrabajo')}"
    )

    # pasar-a-area también debe marcarla: pasar la etapa activa de área 1 a área 2,
    # completarla y volver a pasar → la segunda etapa en área 2 es retrabajo.
    r_ep = client.put(f"/api/v1/produccion/etapa/{etapa_ret['id']}/estado",
                      params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r_ep.status_code == 200, f"EN_PROCESO retrabajo → {r_ep.status_code}: {r_ep.text}"
    r_p1 = client.post(f"/api/v1/produccion/etapa/{etapa_ret['id']}/pasar-a-area", json={
        "area_id": area2, "empleado_responsable_id": 1,
        "empleados_adicionales_ids": []}, headers=ADMIN_HEADERS)
    assert r_p1.status_code == 201, f"pasar→área2 → {r_p1.status_code}: {r_p1.text}"
    etapa2 = r_p1.json()
    cleaner.registrar("etapa_produccion", etapa2["id"])
    assert etapa2.get("es_retrabajo") is False, "Primera vez en área 2 no es retrabajo"

    # Completar área 2 (la etapa nueva nace ASIGNADA; hay que pasarla por EN_PROCESO)
    r_ep2 = client.put(f"/api/v1/produccion/etapa/{etapa2['id']}/estado",
                       params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r_ep2.status_code == 200, f"EN_PROCESO área2 → {r_ep2.status_code}: {r_ep2.text}"
    r_c2 = client.put(f"/api/v1/produccion/etapa/{etapa2['id']}/estado",
                      params={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS)
    assert r_c2.status_code == 200, f"COMPLETADA área2 → {r_c2.status_code}: {r_c2.text}"

    # Nueva etapa en área 2 (ya completada) → retrabajo
    r3 = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": area2,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c12-retrabajo2"},
        headers=ADMIN_HEADERS)
    assert r3.status_code == 201, f"etapa2 retrabajo → {r3.status_code}: {r3.text}"
    etapa2_ret = r3.json()
    cleaner.registrar("etapa_produccion", etapa2_ret["id"])
    assert etapa2_ret.get("es_retrabajo") is True, (
        f"Riesgo C12: etapa recreada en área 2 completada debe ser retrabajo"
    )


# ---------------------------------------------------------------------------
# C13 — No se puede eliminar una orden con etapas (stock/gastos huérfanos)
# ---------------------------------------------------------------------------
def test_c13_eliminar_orden_con_etapas_rechazado(client, cleaner, db):
    """DELETE /orden/ borraba en cascada etapas+consumos dejando stock y gastos
    huérfanos. Debe rechazarse cuando la orden tiene etapas."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])

    r_etapa = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c13"},
        headers=ADMIN_HEADERS)
    assert r_etapa.status_code == 201, f"etapa → {r_etapa.status_code}: {r_etapa.text}"
    cleaner.registrar("etapa_produccion", r_etapa.json()["id"])

    r = client.delete(f"/api/v1/produccion/orden/{orden['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 400, (
        f"Riesgo C13: eliminar orden con etapas debe ser 400, "
        f"fue {r.status_code}: {r.text}"
    )
    sigue_existiendo = db.execute(text(
        "SELECT COUNT(*) FROM orden_produccion WHERE id=:o"
    ), {"o": orden["id"]}).scalar()
    assert sigue_existiendo == 1, "La orden no debe eliminarse"


# ---------------------------------------------------------------------------
# C14 — Finalizar orden con costo fallido → 400 (nunca cerrada sin costos)
# ---------------------------------------------------------------------------
def test_c14_finalizar_no_cierra_si_costo_falla(client, cleaner, db, monkeypatch):
    """Si calcular_y_guardar_costo falla, la orden NO se finaliza (antes el
    error se imprimía y la orden quedaba cerrada sin costos)."""
    def _costo_explota(*args, **kwargs):
        raise ValueError("fallo simulado del cálculo de costos")

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])

    r_etapa = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c14"},
        headers=ADMIN_HEADERS)
    assert r_etapa.status_code == 201, f"etapa → {r_etapa.status_code}: {r_etapa.text}"
    etapa_id = r_etapa.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)
    r_ep = client.put(f"/api/v1/produccion/etapa/{etapa_id}/estado",
                      params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r_ep.status_code == 200, f"EN_PROCESO → {r_ep.status_code}: {r_ep.text}"
    r_c = client.put(f"/api/v1/produccion/etapa/{etapa_id}/estado",
                     params={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS)
    assert r_c.status_code == 200, f"COMPLETADA → {r_c.status_code}: {r_c.text}"

    monkeypatch.setattr(
        "app.modules.production.service.calcular_y_guardar_costo", _costo_explota
    )
    r = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado",
                   params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 400, (
        f"Riesgo C14: finalizar con costo fallido debe ser 400, "
        f"fue {r.status_code}: {r.text}"
    )
    estado = db.execute(text(
        "SELECT estado FROM orden_produccion WHERE id=:o"
    ), {"o": orden["id"]}).scalar()
    assert estado == "EN_PRODUCCION", (
        f"Riesgo C14: la orden no debe quedar FINALIZADA sin costos, estado={estado}"
    )
# ---------------------------------------------------------------------------
# C15 — Referencia receta del kanban ESCALADA a las dimensiones del pedido
# ---------------------------------------------------------------------------
def test_c15_referencia_receta_escalada_por_area(client, cleaner, db):
    """La receta de referencia de una etapa mostraba cantidad_base sin escalar
    (un material LINEAL con largo 2x se veía igual). Ahora usa el motor de
    escalado y expone la sección del área de la etapa."""
    areas = [r[0] for r in db.execute(text("SELECT id FROM area ORDER BY id LIMIT 3"))]
    area1 = areas[0]

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)  # ancho_base 1.60, largo_base 1.90
    material = crear_material(client, cleaner, costo_base=5000.0)
    crear_receta(client, cleaner, producto["id"], material["id"],
                 cantidad_base=2.0, tipo_escala="LINEAL", seccion="EBANISTERIA")

    # Cotización con detalle de largo DOBLE (3.80 vs base 1.90)
    r_cot = client.post("/api/v1/cotizacion/", json={
        "cliente_id": cliente["id"],
        "fecha": str(datetime.today().date()),
        "estado": "BORRADOR",
        "total_estimado": 100000,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": _uniq("cot15"),
        "detalles": [
            {"producto_id": producto["id"], "cantidad": 1, "precio": 100000,
             "ancho": 1.60, "largo": 3.80},
        ],
    }, headers=ADMIN_HEADERS)
    assert r_cot.status_code == 201, f"cotización → {r_cot.status_code}: {r_cot.text}"
    cot = r_cot.json()
    cleaner.registrar("cotizacion", cot["id"])

    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1,
                            "precio": 100000, "costo_unitario": 1000, "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])

    r_etapa = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": area1,
        "empleado_responsable_id": 1, "estado": "ASIGNADA", "observaciones": "c15"},
        headers=ADMIN_HEADERS)
    assert r_etapa.status_code == 201, f"etapa → {r_etapa.status_code}: {r_etapa.text}"
    etapa_id = r_etapa.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)

    r = client.get(f"/api/v1/produccion/etapa/{etapa_id}/referencia-receta",
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"referencia-receta → {r.status_code}: {r.text}"
    data = r.json()

    assert data.get("seccion_actual"), f"Debe exponer la sección del área: {data}"
    assert data["dimensiones"]["largo"] == pytest.approx(3.80), data["dimensiones"]
    materiales = [m for m in data["materiales"] if m["material_id"] == material["id"]]
    assert materiales, f"El material debe estar en la receta: {data['materiales']}"
    assert materiales[0]["cantidad_esperada"] == pytest.approx(4.0), (
        f"Riesgo C15: LINEAL con largo 2x debe esperar 4.0, fue "
        f"{materiales[0]['cantidad_esperada']} (base {materiales[0]['cantidad_base']})"
    )


# ---------------------------------------------------------------------------
# M1 — Reversa de stock al cancelar compra RECIBIDA (no existe DELETE)
# ---------------------------------------------------------------------------
def test_m1_cancelar_compra_recibida_no_revierte_stock(client, cleaner, db):
    """Crear compra RECIBIDA → stock entra; poner estado CANCELADA → debe revertir.
    Bug real: response_model CompraResponse.detalle (singular) vs modelo detalles
    hace que crear compra devuelva 500. Se documenta ambos: creación y reversa."""
    proveedor = client.post("/api/v1/proveedor/", json={
        "nombre": "test_prov_risks", "telefono": "555-2222"},
        headers=ADMIN_HEADERS)
    assert proveedor.status_code == 201
    proveedor_id = proveedor.json()["id"]
    cleaner.registrar("proveedor", proveedor_id)

    material = crear_material(client, cleaner, costo_base=2000.0)
    # La compra CONTADO exige método de caja (la plata sale de una cuenta).
    metodo_caja_id = db.execute(text("SELECT id FROM metodo_caja LIMIT 1")).scalar()

    # Paso 1: crear compra RECIBIDA — debe ser 201 (bug real: 500 ResponseValidationError)
    r_compra = client.post("/api/v1/compras/", json={
        "proveedor_id": proveedor_id, "moneda_id": 1,
        "fecha": "2026-08-05", "estado": "RECIBIDA", "tipo_pago": "CONTADO",
        "metodo_caja_id": metodo_caja_id,
        "detalle": [{"material_id": material["id"], "cantidad": 50,
                     "costo_unitario": 2000.0}],
        "observaciones": "test_m1"},
        headers=ADMIN_HEADERS)
    # Si la app arregla el response model, esto pasa a 201
    assert r_compra.status_code == 201, (
        f"Riesgo M1 (response model): crear compra RECIBIDA → 201, "
        f"fue {r_compra.status_code}: {r_compra.text}"
    )
    compra_id = r_compra.json()["id"]
    cleaner.registrar("compra", compra_id)

    stock_comprada = float(db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).scalar())
    assert stock_comprada == pytest.approx(50), f"Stock tras compra: {stock_comprada}"
    # Paso 2: poner estado CANCELADA — debe revertir el stock a 0
    r_upd = client.put(f"/api/v1/compras/{compra_id}/estado",
                       params={"estado": "CANCELADA"}, headers=ADMIN_HEADERS)
    assert r_upd.status_code == 200, f"CANCELADA → {r_upd.status_code}: {r_upd.text}"

    stock_final = float(db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).scalar())
    assert stock_final == pytest.approx(0), (
        f"Riesgo M1 (reversa): CANCELADA no revirtió stock — quedó {stock_final}"
    )
    registrar_inventario_de_material(db, cleaner, material["id"])
