# -*- coding: utf-8 -*-
"""
test_e2e_caso1.py — CASO 1 "Cliente fiel, tres muebles a medida".

Flujo E2E completo de un pedido de 3 muebles FABRICADOS:

  cliente + 3 productos con receta (madera m³ + madera lineal) → stock de
  materiales → cotización COP → pedido (venta PENDIENTE) → producción por
  áreas (consumos con captura flexible: pieza L×A×E y cm→m, solicitante
  distinto en cada consumo + mano de obra) → pedido TERMINADO + envío
  PREPARADO → pagos multi-moneda (COP/USD/VES) hasta el 100% → factura
  fiscal EMITIDA (IVA 16% + IGTF 3%) → asignación de chofer + guía →
  vista del chofer → EN_TRANSITO → ENTREGADO.

Asserts de integridad final: stock exacto (50 m³ / 200 m menos consumos),
kardex con referencia de producción, gasto automático por consumo, caja por
método de pago y montos que suman el total de la venta.

Ejecutar:
  cd backend && source venv/bin/activate && python -m pytest test/test_e2e_caso1.py -v
"""
import pytest
from sqlalchemy import text

from conftest import ADMIN_HEADERS, _uniq, crear_cliente, crear_orden_desde_pedido, crear_receta
from helpers_e2e import (
    area_id,
    cargo_id,
    asignar_chofer,
    avanzar_envio,
    avanzar_etapa,
    crear_cotizacion_multidetalle,
    crear_consumo,
    crear_empleado,
    crear_etapa,
    crear_material,
    crear_producto_fabricado,
    crear_usuario_chofer,
    convertir_cotizacion,
    emitir_factura,
    entrar_stock_material,
    envio_de_pedido,
    finalizar_orden,
    movimientos_caja_de_pedido,
    pagar_venta,
    registrar_mano_obra,
    saldo_cuenta,
    stock_material,
    venta_actualizada,
    venta_de_pedido,
)


# ---------------------------------------------------------------------------
# Helpers locales (no tocan conftest.py ni helpers_e2e.py)
# ---------------------------------------------------------------------------
def _pasar_a_area(client, cleaner, etapa_id, area_destino_id, empleado_id):
    """Completa la etapa actual y crea la siguiente en el área destino."""
    r = client.post(
        f"/api/v1/produccion/etapa/{etapa_id}/pasar-a-area",
        json={
            "area_id": area_destino_id,
            "empleado_responsable_id": empleado_id,
            "empleados_adicionales_ids": [],
        },
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, f"pasar-a-area → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("etapa_produccion", body["id"])
    return body


def _consumir(client, cleaner, db, etapa_id, material_id, cantidad, solicitante_id,
              unidad_captura=None, pieza=None, esperado=None):
    """Consumo con captura flexible. `pieza` = (largo, ancho, espesor) activa la
    fórmula de la casa; `unidad_captura` = 'M'|'CM' para materiales lineales."""
    kwargs = {}
    if unidad_captura:
        kwargs["unidad_captura"] = unidad_captura
    if pieza:
        kwargs.update(pieza_largo=pieza[0], pieza_ancho=pieza[1], pieza_espesor=pieza[2])
    r, body = crear_consumo(
        client, cleaner, db, etapa_id, material_id, cantidad, solicitante_id, **kwargs
    )
    assert body is not None, f"crear_consumo → {r.status_code}: {r.text}"
    assert body["solicitante_empleado_id"] == solicitante_id, \
        f"El solicitante debe quedar registrado: {body}"
    if esperado is not None:
        assert float(body["cantidad"]) == pytest.approx(esperado, abs=0.001), \
            f"Consumo esperaba {esperado}, devolvió {body['cantidad']}: {body}"
    return body


def _producir_orden_completa(client, cleaner, db, orden, ruta, mo_montos, mat_m3, mat_m):
    """Recorre una ruta de (area, responsable) por `pasar-a-area` con un
    consumo + mano de obra en cada área. Devuelve la lista de consumos."""
    consumos = []
    etapa = None
    for i, (area_nombre, responsable) in enumerate(ruta):
        if etapa is None:
            etapa = crear_etapa(client, cleaner, orden["id"],
                                area_id(db, area_nombre), responsable["id"])
        avanzar_etapa(client, etapa["id"], "EN_PROCESO")
        if i == 0:
            # Captura flexible por PIEZA: 20×4×2 × 2 piezas ÷ 10000 → 0.032 m³.
            cons = _consumir(client, cleaner, db, etapa["id"], mat_m3["id"], 2,
                             responsable["id"], pieza=(20, 4, 2), esperado=0.032)
        elif i == 1:
            # Captura lineal en CM: 1520 cm → 15.20 m.
            cons = _consumir(client, cleaner, db, etapa["id"], mat_m["id"], 1520,
                             responsable["id"], unidad_captura="CM", esperado=15.20)
        else:
            cons = _consumir(client, cleaner, db, etapa["id"], mat_m["id"], 3,
                             responsable["id"], esperado=3.0)
        consumos.append(cons)
        registrar_mano_obra(client, cleaner, etapa["id"], responsable["id"], mo_montos[i])
        if i < len(ruta) - 1:
            etapa = _pasar_a_area(client, cleaner, etapa["id"],
                                  area_id(db, ruta[i + 1][0]), ruta[i + 1][1]["id"])
        else:
            avanzar_etapa(client, etapa["id"], "COMPLETADA")
    return consumos


# ---------------------------------------------------------------------------
# CASO 1
# ---------------------------------------------------------------------------
def test_caso1_tres_muebles_cierre_completo(client, cleaner, db):
    """Cliente fiel: 3 muebles a medida, producción por áreas, cobro mixto
    COP/USD/VES, factura fiscal y entrega con chofer. Cierre completo."""
    # ── 1. Datos base: cliente + 3 productos fabricados con receta ─────────
    cliente = crear_cliente(client, cleaner, nombre=_uniq("cliente_fiel"))
    precios = [150000.0, 120000.0, 90000.0]
    productos = [crear_producto_fabricado(client, cleaner, costo_base=p) for p in precios]

    mat_m3 = crear_material(client, cleaner, nombre=_uniq("madera_m3"),
                            costo_base=2000.0, unidad_medida_id=193)  # m³
    mat_m = crear_material(client, cleaner, nombre=_uniq("madera_m"),
                           costo_base=1500.0, unidad_medida_id=2)  # m lineal

    for p in productos:
        crear_receta(client, cleaner, p["id"], mat_m3["id"], cantidad_base=0.5,
                     tipo_escala="FIJO", seccion="EBANISTERIA")
        crear_receta(client, cleaner, p["id"], mat_m["id"], cantidad_base=2.0,
                     tipo_escala="FIJO", seccion="PINTURA")

    entrar_stock_material(client, cleaner, mat_m3["id"], 50)    # 50 m³
    entrar_stock_material(client, cleaner, mat_m["id"], 200)    # 200 m

    # Empleados: 1 chofer + 6 operarios (un solicitante distinto por consumo).
    ebanista1 = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "EBANISTA"))
    ebanista2 = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "EBANISTA"))
    pintor1 = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "PINTOR"))
    pintor2 = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "PINTOR"))
    tapicero1 = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "TAPICERO"))
    preparador1 = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "PREPARADOR"))
    chofer = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "CHOFER"))

    # ── 2. Cotización COP → pedido (venta PENDIENTE) ────────────────────────
    detalles_cot = [
        {"producto_id": p["id"], "tipo_item": "FABRICADO", "cantidad": 1,
         "precio": precio, "ancho": 1.60, "largo": 1.90}
        for p, precio in zip(productos, precios)
    ]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], detalles_cot,
                                        moneda_id=1, tasa_cambio=1.0)
    assert float(cot["total_estimado"]) == pytest.approx(360000.0)

    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], detalles_cot)
    assert r.status_code == 201, f"convertir_cotizacion → {r.status_code}: {r.text}"
    assert len(pedido["detalles"]) == 3

    venta = venta_de_pedido(client, db, pedido["id"])
    assert venta is not None, "La conversión debe auto-crear la venta"
    assert venta["estado"] == "PENDIENTE", venta["estado"]
    assert venta["moneda_id"] == 1 and float(venta["tasa_cambio"]) == pytest.approx(1.0)
    assert float(venta["total"]) == pytest.approx(360000.0)
    venta_id = venta["id"]

    # ── 3. Producción por áreas (3 órdenes, consumos + mano de obra) ────────
    ordenes = [crear_orden_desde_pedido(client, cleaner, d["id"])
               for d in pedido["detalles"]]
    for o in ordenes:
        assert o["estado"] == "PENDIENTE"

    # Orden 1: recorrido completo 3 áreas (Ebanistería → Pintura → Tapicería).
    consumos_o1 = _producir_orden_completa(
        client, cleaner, db, ordenes[0],
        [("Ebanistería", ebanista1), ("Pintura", pintor1), ("Tapicería", tapicero1)],
        [25000.0, 20000.0, 18000.0],
        mat_m3, mat_m,
    )
    # Orden 2: 2 áreas (Ebanistería → Pintura) con consumos directos.
    consumos_o2 = []
    e = crear_etapa(client, cleaner, ordenes[1]["id"], area_id(db, "Ebanistería"),
                    ebanista2["id"])
    avanzar_etapa(client, e["id"], "EN_PROCESO")
    consumos_o2.append(_consumir(client, cleaner, db, e["id"], mat_m3["id"], 0.5,
                                 ebanista2["id"], esperado=0.5))
    registrar_mano_obra(client, cleaner, e["id"], ebanista2["id"], 30000.0)
    avanzar_etapa(client, e["id"], "COMPLETADA")
    e = crear_etapa(client, cleaner, ordenes[1]["id"], area_id(db, "Pintura"),
                    preparador1["id"])
    avanzar_etapa(client, e["id"], "EN_PROCESO")
    consumos_o2.append(_consumir(client, cleaner, db, e["id"], mat_m["id"], 2,
                                 preparador1["id"], esperado=2.0))
    registrar_mano_obra(client, cleaner, e["id"], preparador1["id"], 22000.0)
    avanzar_etapa(client, e["id"], "COMPLETADA")
    # Orden 3: 1 área (Ebanistería).
    consumos_o3 = []
    e = crear_etapa(client, cleaner, ordenes[2]["id"], area_id(db, "Ebanistería"),
                    pintor2["id"])
    avanzar_etapa(client, e["id"], "EN_PROCESO")
    consumos_o3.append(_consumir(client, cleaner, db, e["id"], mat_m3["id"], 0.18,
                                 pintor2["id"], esperado=0.18))
    registrar_mano_obra(client, cleaner, e["id"], pintor2["id"], 25000.0)
    avanzar_etapa(client, e["id"], "COMPLETADA")

    todos_consumos = consumos_o1 + consumos_o2 + consumos_o3
    assert len(todos_consumos) == 6, "Deben quedar 6 consumos registrados"
    solicitantes = {c["solicitante_empleado_id"] for c in todos_consumos}
    assert len(solicitantes) == 6, "Cada consumo debe tener un solicitante distinto"

    # Finalizar las 3 órdenes → la última dispara pedido TERMINADO + envío.
    for o in ordenes:
        finalizar_orden(client, o["id"])
    estado_pedido = db.execute(text("SELECT estado FROM pedido WHERE id=:p"),
                               {"p": pedido["id"]}).scalar()
    assert estado_pedido == "TERMINADO", f"Pedido debe quedar TERMINADO, fue {estado_pedido}"

    envio = envio_de_pedido(db, pedido["id"])
    assert envio is not None, "Debe crearse el envío automático"
    assert envio["estado"] == "PREPARADO", envio["estado"]
    cleaner.registrar("envio", envio["id"])
    envio_id = envio["id"]

    # ── 4. Cobro multi-moneda hasta el 100% exacto (360000 COP) ─────────────
    # Baselines de caja ANTES de los pagos (las cuentas reales pueden tener
    # saldos históricos; se asevera el DELTA de cada cuenta por moneda).
    base_efectivo_cop = saldo_cuenta(client, "EFECTIVO_COP", 1)
    base_zelle = saldo_cuenta(client, "ZELLE", 2)
    base_bancaribe = saldo_cuenta(client, "BANCARIBE", 3)
    # Guardia: factura fiscal ANTES del pago completo → 400.
    lineas_factura = [
        {"detalle_pedido_id": d["id"], "precio_usd": pu}
        for d, pu in zip(pedido["detalles"], [100.0, 80.0, 60.0])
    ]
    r, _ = emitir_factura(client, cleaner, db, pedido["id"], lineas_factura,
                          tasa_usd_ves=50.0, permitir_saldo_pendiente=False)
    assert r.status_code == 400, f"Facturar sin pago completo debe ser 400, fue {r.status_code}"
    assert "100%" in r.text, r.text

    # Abono inicial ~39% en COP.
    r, pago1 = pagar_venta(client, cleaner, venta_id, 1, 140000.0, "EFECTIVO_COP")
    assert r.status_code == 201, f"abono COP → {r.status_code}: {r.text}"
    assert float(pago1["monto_en_moneda_base"]) == pytest.approx(140000.0)
    assert venta_actualizada(client, venta_id)["estado"] == "ABONADA"

    # ZELLE: 30 USD @ 3900 → 117000 COP (base limpia al millar).
    r, pago2 = pagar_venta(client, cleaner, venta_id, 2, 30.0, "ZELLE", tasa_cambio=3900.0)
    assert r.status_code == 201, f"pago ZELLE → {r.status_code}: {r.text}"
    assert float(pago2["monto_en_moneda_base"]) == pytest.approx(117000.0)

    # BANCARIBE: 1000 VES @ 10 → 10000 COP (base limpia al millar).
    r, pago3 = pagar_venta(client, cleaner, venta_id, 3, 1000.0, "BANCARIBE", tasa_cambio=10.0)
    assert r.status_code == 201, f"pago BANCARIBE → {r.status_code}: {r.text}"
    assert float(pago3["monto_en_moneda_base"]) == pytest.approx(10000.0)

    # Resto en COP: 360000 - 140000 - 117000 - 10000 = 93000 → PAGADA.
    r, pago4 = pagar_venta(client, cleaner, venta_id, 1, 93000.0, "EFECTIVO_COP")
    assert r.status_code == 201, f"pago final COP → {r.status_code}: {r.text}"

    venta_final = venta_actualizada(client, venta_id)
    assert venta_final["estado"] == "PAGADA", venta_final["estado"]
    assert float(venta_final["total_pagado"]) == pytest.approx(360000.0)
    assert float(venta_final["saldo_pendiente"]) == pytest.approx(0.0, abs=0.01)

    # Caja: un movimiento ENTRADA por pago, en la cuenta/moneda correctas.
    movs = movimientos_caja_de_pedido(db, pedido["id"])
    assert [m["cuenta"] for m in movs] == ["EFECTIVO_COP", "ZELLE", "BANCARIBE", "EFECTIVO_COP"], movs
    assert [m["moneda_id"] for m in movs] == [1, 2, 3, 1], movs
    assert [m["tipo"] for m in movs] == ["ENTRADA"] * 4, movs
    for m, base, moneda, cuenta in zip(
        movs, [140000.0, 117000.0, 10000.0, 93000.0], [1, 2, 3, 1],
        ["EFECTIVO_COP", "ZELLE", "BANCARIBE", "EFECTIVO_COP"],
    ):
        assert m["monto_en_moneda_base"] == pytest.approx(base), m
        assert float(m["monto"]) * float(m["tasa_cambio"]) == pytest.approx(base, abs=1.0), m
    suma_base = sum(m["monto_en_moneda_base"] for m in movs)
    assert suma_base == pytest.approx(360000.0), "Los movimientos deben sumar el total"
    assert saldo_cuenta(client, "EFECTIVO_COP", 1) - base_efectivo_cop == pytest.approx(233000.0)
    assert saldo_cuenta(client, "ZELLE", 2) - base_zelle == pytest.approx(30.0)
    assert saldo_cuenta(client, "BANCARIBE", 3) - base_bancaribe == pytest.approx(1000.0)

    # ── 5. Factura fiscal al 100% pagado ────────────────────────────────────
    r, factura = emitir_factura(client, cleaner, db, pedido["id"], lineas_factura,
                                tasa_usd_ves=50.0, permitir_saldo_pendiente=False)
    assert r.status_code == 201, f"emitir_factura → {r.status_code}: {r.text}"
    assert factura["estado"] == "EMITIDA"
    # 240 USD × 50 = 12000 Bs; IVA 16% = 1920; IGTF 3% de (12000+1920) = 417.6.
    assert float(factura["total_usd"]) == pytest.approx(240.0)
    assert float(factura["base_imponible_bs"]) == pytest.approx(12000.0)
    assert float(factura["iva_bs"]) == pytest.approx(1920.0)
    assert float(factura["igtf_bs"]) == pytest.approx(417.6)
    assert float(factura["total_bs"]) == pytest.approx(14337.6)

    # ── 6. Envío: chofer, guía, vista del chofer, tránsito y entrega ────────
    asignar_chofer(client, envio_id, chofer["id"])
    r = client.put(f"/api/v1/envio/{envio_id}",
                   json={"guia_despacho": "G-CASO1-0001"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"guia_despacho → {r.status_code}: {r.text}"
    assert r.json()["guia_despacho"] == "G-CASO1-0001", r.json()

    chofer_headers = crear_usuario_chofer(db, cleaner, chofer["id"])
    r = client.get("/api/v1/envio/mis-asignaciones", params={"estado": "PREPARADO"},
                   headers=chofer_headers)
    assert r.status_code == 200, f"mis-asignaciones → {r.status_code}: {r.text}"
    asignaciones = r.json()
    assert any(e["id"] == envio_id for e in asignaciones), \
        f"El envío {envio_id} debe aparecer en las asignaciones del chofer: {asignaciones}"

    avanzar_envio(client, envio_id, "EN_TRANSITO")
    avanzar_envio(client, envio_id, "ENTREGADO")
    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json()["estado"] == "ENTREGADO", r.json()["estado"]

    # ── 7. Integridad final ─────────────────────────────────────────────────
    # Stock descontado exactamente: 50 - 0.712 m³ y 200 - 20.20 m.
    # (0.032 pieza + 0.5 + 0.18 m³; el resto es material lineal en m.)
    assert stock_material(db, mat_m3["id"]) == pytest.approx(50.0 - 0.712, abs=0.001)
    assert stock_material(db, mat_m["id"]) == pytest.approx(200.0 - 20.20, abs=0.001)

    # Kardex: cada consumo generó una SALIDA con referencia de producción.
    for material_id, consumido, n in [(mat_m3["id"], 0.712, 3), (mat_m["id"], 20.20, 3)]:
        rows = db.execute(text(
            "SELECT cantidad FROM movimiento_inventario "
            "WHERE material_id=:m AND referencia_tipo='produccion' AND tipo='SALIDA'"
        ), {"m": material_id}).fetchall()
        assert len(rows) == n, f"Kardex producción material {material_id}: {len(rows)} SALIDAS"
        assert sum(float(r[0]) for r in rows) == pytest.approx(consumido, abs=0.001)

    # Gasto automático por cada consumo (marcador [consumo {id}]).
    for cons in todos_consumos:
        n_gastos = db.execute(text(
            "SELECT COUNT(*) FROM gasto WHERE observaciones LIKE :pat"
        ), {"pat": f"%[consumo {cons['id']}]%"}).scalar()
        assert n_gastos == 1, f"Consumo {cons['id']} debe tener 1 gasto automático, hay {n_gastos}"

    envio_final = envio_de_pedido(db, pedido["id"])
    assert envio_final["estado"] == "ENTREGADO", envio_final["estado"]

    print("[CASO 1] venta pagada: %.2f | factura: %.2f Bs (EMITIDA) | envio: %s | pedido: %s"
          % (venta_final["total_pagado"], factura["total_bs"], envio_final["estado"],
             r.json()["estado"]))
    print("[CASO 1] stock m3: %.2f (esperado %.2f) | stock m: %.2f (esperado %.2f)"
          % (stock_material(db, mat_m3["id"]), 50.0 - 0.712,
             stock_material(db, mat_m["id"]), 200.0 - 20.20))
    print("[CASO 1] caja: %d movimientos | suma moneda base: %.2f | consumos: %d"
          % (len(movs), suma_base, len(todos_consumos)))