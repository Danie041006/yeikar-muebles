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
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto1["id"], precio=100000)

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

    material = crear_material(client, cleaner, costo_base=2000.0)
    st_mov, _ = crear_movimiento(client, cleaner, material["id"], "ENTRADA", 100)
    assert st_mov.status_code in (200, 201), f"ENTRADA → {st_mov.status_code}"
    stock_antes = float(db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=1"
    ), {"m": material["id"]}).scalar())

    r_cons = client.post("/api/v1/produccion/consumo/", json={
        "etapa_produccion_id": etapa_id, "material_id": material["id"],
        "cantidad": 10, "fecha": "2026-08-05T00:00:00", "observaciones": "c6"},
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

    # Paso 1: crear compra RECIBIDA — debe ser 201 (bug real: 500 ResponseValidationError)
    r_compra = client.post("/api/v1/compras/", json={
        "proveedor_id": proveedor_id, "moneda_id": 1,
        "fecha": "2026-08-05", "estado": "RECIBIDA", "tipo_pago": "CONTADO",
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
