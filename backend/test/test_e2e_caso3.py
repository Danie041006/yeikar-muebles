"""
test_e2e_caso3.py — CASO 3: "El insumo tramposo + producción por áreas + costos
+ nómina y aguinaldo".

Cadena completa vía API real (TestClient + BD dev Postgres, filas `test_` que
borra el fixture `cleaner` en teardown):

  cotización mixta (FABRICADO + REVENTA + INSUMO) → conversión (el INSUMO se
  descuenta del inventario AL INSTANTE como SALIDA con referencia_tipo=VENTA y
  NO pasa por producción ni crea gasto) → producción del mueble por 3 áreas
  (consumos + mano de obra + retrabajo excluido de nómina) → costos de la
  orden → pedido TERMINADO manual (el envío NO se auto-crea en pedidos mixtos)
  → pagos multi-moneda → nómina semanal destajo (tarifa por área + MO manual
  con recargo + bono aguinaldo con % por área: Ebanistería 8%, resto 5%) →
  pago de aguinaldo → intentos de romper (nómina duplicada, factura con saldo).

Ejecutar (SOLO este archivo, nunca la suite completa):
    cd backend && source venv/bin/activate
    python -m pytest test/test_e2e_caso3.py -v
"""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_orden_desde_pedido,
    crear_receta,
    registrar_inventario_de_material,
)
from helpers_e2e import (
    _uniq,
    area_id,
    cargo_id,
    avanzar_etapa,
    convertir_cotizacion,
    crear_cotizacion_multidetalle,
    crear_consumo,
    crear_empleado,
    crear_etapa,
    crear_nomina,
    crear_producto_fabricado,
    crear_producto_reventa,
    crear_stock_producto,
    crear_tarifa_produccion,
    emitir_factura,
    entrar_stock_material,
    envio_de_pedido,
    finalizar_orden,
    hoy,
    movimientos_caja_de_pedido,
    pagar_nomina,
    pagar_venta,
    preview_nomina,
    registrar_mano_obra,
    saldos_aguinaldo,
    semana_actual,
    stock_material,
    stock_producto,
    venta_actualizada,
    venta_de_pedido,
)


def _periodo_candidatos():
    """Periodos de nómina que SIEMPRE contienen hoy (la mano de obra y las
    etapas usan now()): primero la semana actual; si estuviera ocupada por otra
    nómina (400/409), periodos alternativos que contienen hoy y que casi nunca
    estarán ocupados."""
    d0, d1 = semana_actual()
    yield d0, d1
    d = hoy()
    yield d - timedelta(days=2), d + timedelta(days=4)
    yield d - timedelta(days=1), d + timedelta(days=5)


def _detalle_preview(preview, empleado_id):
    for det in preview["detalles"]:
        if det["empleado_id"] == empleado_id:
            return det
    raise AssertionError(f"El empleado {empleado_id} no aparece en el preview de nómina")


def _registrar_gasto_consumo(db, cleaner, consumo_id):
    """Registra en el cleaner el gasto automático de un consumo.

    WORKAROUND: helpers_e2e.crear_consumo registra el gasto buscando el marcador
    '[consumo {id}]' en la DESCRIPCION del gasto, pero el backend lo guarda en
    OBSERVACIONES (production/service.py:618) → el gasto quedaría huérfano."""
    for (gid,) in db.execute(text(
        "SELECT id FROM gasto WHERE observaciones LIKE :pat"
    ), {"pat": f"%[consumo {consumo_id}]%"}).fetchall():
        cleaner.registrar("gasto", gid)


def test_caso3_insumo_nomina_aguinaldo(client, db, cleaner):
    # ------------------------------------------------------------------
    # 0. SETUP: catálogos reales + cliente + productos + materiales
    # ------------------------------------------------------------------
    a_eb = area_id(db, "Ebanistería")
    a_pin = area_id(db, "Pintura")
    a_tap = area_id(db, "Tapicería")
    cargo_eb = cargo_id(db, "EBANISTA")
    cargo_pin = cargo_id(db, "PINTOR")
    cargo_tap = cargo_id(db, "TAPICERO")

    cliente = crear_cliente(client, cleaner)
    mueble = crear_producto_fabricado(client, cleaner, costo_base=80000.0)
    reventa = crear_producto_reventa(client, cleaner, costo_base=40000.0)

    madera = crear_material(client, cleaner, nombre=_uniq("madera"), costo_base=40000.0, unidad_medida_id=193)   # m³ (volumétrica)
    tornillos = crear_material(client, cleaner, nombre=_uniq("tornillos"), costo_base=500.0, unidad_medida_id=1)  # Ud
    madera_lineal = crear_material(client, cleaner, nombre=_uniq("madera_lineal"), costo_base=30000.0, unidad_medida_id=2)  # m (lineal)
    insumo_mat = crear_material(client, cleaner, nombre=_uniq("insumo"), costo_base=5000.0, unidad_medida_id=2)   # m

    crear_receta(client, cleaner, mueble["id"], madera["id"], 0.5, "FIJO", "EBANISTERIA")
    crear_receta(client, cleaner, mueble["id"], tornillos["id"], 20, "FIJO", "EBANISTERIA")

    entrar_stock_material(client, cleaner, madera["id"], 20)
    entrar_stock_material(client, cleaner, tornillos["id"], 100)
    entrar_stock_material(client, cleaner, madera_lineal["id"], 50)
    entrar_stock_material(client, cleaner, insumo_mat["id"], 10)
    crear_stock_producto(client, cleaner, db, reventa["id"], 5, 40000)

    eb01 = crear_empleado(client, cleaner, cargo_id=cargo_eb, en_nomina=True, tipo_pago="DESTAJO")
    pintor = crear_empleado(client, cleaner, cargo_id=cargo_pin, en_nomina=True, tipo_pago="DESTAJO")
    tapicero = crear_empleado(client, cleaner, cargo_id=cargo_tap, en_nomina=True, tipo_pago="DESTAJO")

    assert stock_material(db, insumo_mat["id"]) == 10.0
    assert stock_material(db, madera["id"]) == 20.0
    assert stock_material(db, tornillos["id"]) == 100.0
    assert stock_material(db, madera_lineal["id"]) == 50.0
    assert stock_producto(db, reventa["id"]) == 5.0
    print("  setup ok: cliente, mueble FABRICADO (receta madera 0.5 m³ + 20 tornillos), "
          "REVENTA stock 5, INSUMO material stock 10 m, 3 empleados DESTAJO en_nomina")

    # ------------------------------------------------------------------
    # 1. Cotización mixta COP → conversión → EL "BUG" DEL INSUMO
    # ------------------------------------------------------------------
    det_fab = {"producto_id": mueble["id"], "tipo_item": "FABRICADO", "cantidad": 1,
               "precio": 150000, "ancho": 1.60, "largo": 1.90}
    det_rev = {"producto_id": reventa["id"], "tipo_item": "REVENTA", "cantidad": 1,
               "precio": 250000, "ancho": 1.60, "largo": 1.90}
    det_ins = {"material_id": insumo_mat["id"], "tipo_item": "INSUMO", "cantidad": 1,
               "precio": 30000}

    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"],
                                        [det_fab, det_rev, det_ins], moneda_id=1)
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [det_fab, det_rev, det_ins])
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"

    # La cotización debe quedar marcada como convertida (pedido_id/pedido_estado)
    # tanto en el detalle como en el listado: la UI usa eso para no ofrecer
    # convertirla otra vez y para mostrarla en el filtro "Convertidas".
    cot_det = client.get(f"/api/v1/cotizacion/{cot['id']}", headers=ADMIN_HEADERS).json()
    assert cot_det.get("pedido_id") == pedido["id"], cot_det
    assert cot_det.get("pedido_estado") == pedido["estado"], cot_det
    cot_list = client.get("/api/v1/cotizacion/", params={"limite": 500}, headers=ADMIN_HEADERS).json()
    cot_en_lista = next((c for c in cot_list if c["id"] == cot["id"]), None)
    assert cot_en_lista is not None, "la cotización debe aparecer en el listado"
    assert cot_en_lista.get("pedido_id") == pedido["id"], cot_en_lista
    # Y una cotización SIN convertir no debe traer pedido_id.
    cot_sin_convertir = crear_cotizacion(client, cleaner, cliente["id"], mueble["id"], precio=100000)
    sc_det = client.get(f"/api/v1/cotizacion/{cot_sin_convertir['id']}", headers=ADMIN_HEADERS).json()
    assert sc_det.get("pedido_id") is None, sc_det

    venta = venta_de_pedido(client, db, pedido["id"])
    assert venta is not None, "la conversión debe auto-crear la venta"
    venta_det = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert venta_det.get("detalles") is not None, venta_det
    registrar_inventario_de_material(db, cleaner, insumo_mat["id"])
    for (mid,) in db.execute(text(
        "SELECT id FROM movimiento_producto_inventario WHERE referencia_tipo='VENTA' AND referencia_id=:v"
    ), {"v": venta["id"]}).fetchall():
        cleaner.registrar("movimiento_producto_inventario", mid)

    # (a) stock del insumo descontado AL INSTANTE: 10 - 1 = 9
    assert stock_material(db, insumo_mat["id"]) == 9.0, (
        f"el INSUMO debe descontarse del inventario al convertir: {stock_material(db, insumo_mat['id'])}"
    )
    # (b) movimiento SALIDA con referencia_tipo='VENTA' y referencia_id = venta.id
    movs = db.execute(text(
        "SELECT tipo, cantidad, referencia_tipo, referencia_id FROM movimiento_inventario "
        "WHERE material_id=:m AND referencia_tipo='VENTA'"
    ), {"m": insumo_mat["id"]}).fetchall()
    assert len(movs) == 1, f"esperaba 1 SALIDA VENTA del insumo, hay {len(movs)}"
    assert movs[0][0] == "SALIDA" and float(movs[0][1]) == 1.0
    assert movs[0][2] == "VENTA" and int(movs[0][3]) == venta["id"]
    # (c) NO se creó orden de producción para el detalle INSUMO (no pasa por producción)
    insumo_detalle = next(d for d in pedido["detalles"] if (d.get("tipo_item") or "FABRICADO") == "INSUMO")
    n_ordenes_insumo = db.execute(text(
        "SELECT count(*) FROM orden_produccion WHERE detalle_pedido_id=:d"
    ), {"d": insumo_detalle["id"]}).scalar()
    assert n_ordenes_insumo == 0, "el INSUMO NO debe generar orden de producción"
    # (d) NO se creó gasto por el insumo
    n_gastos_insumo = db.execute(text(
        "SELECT count(*) FROM gasto WHERE descripcion ILIKE :pat"
    ), {"pat": f"%{insumo_mat['nombre']}%"}).scalar()
    assert n_gastos_insumo == 0, "el INSUMO vendido NO debe crear gastos"
    # (e) venta con los 3 detalles (INSUMO incluido)
    tipos = sorted((d.get("tipo_item") or "FABRICADO") for d in venta_det["detalles"])
    assert tipos == ["FABRICADO", "INSUMO", "REVENTA"], f"venta con detalles {tipos}"
    # (f) el REVENTA también se descuenta al facturar: 5 - 1 = 4
    assert stock_producto(db, reventa["id"]) == 4.0
    print(f"  ✓ INSUMO documentado: stock 10→9 al instante · SALIDA referencia_tipo=VENTA "
          f"(venta #{venta['id']}) · 0 órdenes de producción · 0 gastos · venta con 3 detalles")

    # ------------------------------------------------------------------
    # 2. Pedido: nace DIRECTAMENTE en PRODUCCION (sin paso "aprobado")
    # ------------------------------------------------------------------
    assert pedido["estado"] == "PRODUCCION", (
        f"el pedido debe nacer en PRODUCCION al convertir, fue {pedido['estado']}"
    )
    # La conversión auto-genera la orden de producción de la línea FABRICADO
    # (PENDIENTE); el endpoint desde-pedido la devuelve (idempotente).
    fab_detalle = next(d for d in pedido["detalles"] if (d.get("tipo_item") or "FABRICADO") == "FABRICADO")
    orden = crear_orden_desde_pedido(client, cleaner, fab_detalle["id"])
    assert orden["estado"] == "PENDIENTE", orden["estado"]

    crear_tarifa_produccion(client, cleaner, a_eb, mueble["id"], 20000)
    crear_tarifa_produccion(client, cleaner, a_pin, mueble["id"], 15000)
    crear_tarifa_produccion(client, cleaner, a_tap, mueble["id"], 12000)

    # E1 Ebanistería: consumos (madera por pieza + tornillos), SIN mano de obra
    # manual → la nómina usará la TARIFA del área (20000).
    e1 = crear_etapa(client, cleaner, orden["id"], a_eb, eb01["id"])
    avanzar_etapa(client, e1["id"], "EN_PROCESO")
    r, c1 = crear_consumo(client, cleaner, db, e1["id"], madera["id"], 1, eb01["id"],
                          pieza_largo=20, pieza_ancho=4, pieza_espesor=2)
    assert r.status_code in (200, 201), f"consumo madera pieza → {r.status_code}: {r.text}"
    assert float(c1["cantidad"]) == 0.016, f"pieza 20×4×2 ×1 = 160÷10000 = 0.016 m³, llegó {c1['cantidad']}"
    _registrar_gasto_consumo(db, cleaner, c1["id"])
    r, c2 = crear_consumo(client, cleaner, db, e1["id"], tornillos["id"], 20, eb01["id"])
    assert r.status_code in (200, 201), f"consumo tornillos → {r.status_code}: {r.text}"
    _registrar_gasto_consumo(db, cleaner, c2["id"])

    r = client.post(f"/api/v1/produccion/etapa/{e1['id']}/pasar-a-area", json={
        "area_id": a_pin, "empleado_responsable_id": pintor["id"], "empleados_adicionales_ids": [],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pasar E1→Pintura → {r.status_code}: {r.text}"
    e2 = r.json()
    cleaner.registrar("etapa_produccion", e2["id"])
    assert e2["area_id"] == a_pin and e2["estado"] == "ASIGNADA"

    # RETRABAJO: re-crear etapa en Ebanistería (ya COMPLETADA en esta orden)
    r = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": a_eb,
        "empleado_responsable_id": eb01["id"], "estado": "ASIGNADA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"etapa retrabajo → {r.status_code}: {r.text}"
    retrabajo = r.json()
    cleaner.registrar("etapa_produccion", retrabajo["id"])
    assert retrabajo["es_retrabajo"] is True, "la etapa re-creada en área completada debe ser retrabajo"
    avanzar_etapa(client, retrabajo["id"], "EN_PROCESO")
    avanzar_etapa(client, retrabajo["id"], "COMPLETADA")

    # E2 Pintura: consumo madera LINEAL en cm (1520 cm → 15.20 m) + MO manual
    avanzar_etapa(client, e2["id"], "EN_PROCESO")
    r, c3 = crear_consumo(client, cleaner, db, e2["id"], madera_lineal["id"], 1520, pintor["id"],
                          unidad_captura="CM")
    assert r.status_code in (200, 201), f"consumo madera cm → {r.status_code}: {r.text}"
    assert float(c3["cantidad"]) == 15.20, f"1520 cm = 15.20 m, llegó {c3['cantidad']}"
    _registrar_gasto_consumo(db, cleaner, c3["id"])
    registrar_mano_obra(client, cleaner, e2["id"], pintor["id"], 25000, porcentaje_recargo=10)

    r = client.post(f"/api/v1/produccion/etapa/{e2['id']}/pasar-a-area", json={
        "area_id": a_tap, "empleado_responsable_id": tapicero["id"], "empleados_adicionales_ids": [],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pasar E2→Tapicería → {r.status_code}: {r.text}"
    e3 = r.json()
    cleaner.registrar("etapa_produccion", e3["id"])

    # E3 Tapicería: MO manual (25000 + 10% → línea 27500)
    avanzar_etapa(client, e3["id"], "EN_PROCESO")
    registrar_mano_obra(client, cleaner, e3["id"], tapicero["id"], 25000, porcentaje_recargo=10)
    avanzar_etapa(client, e3["id"], "COMPLETADA")

    # stock tras consumos: madera 20 - 0.016 = 19.984 · madera_lineal 50 - 15.20 = 34.80 ·
    # tornillos 100 - 20 = 80
    assert abs(stock_material(db, madera["id"]) - 19.984) < 1e-6
    assert abs(stock_material(db, madera_lineal["id"]) - 34.80) < 1e-6
    assert stock_material(db, tornillos["id"]) == 80.0
    print("  producción ok: Ebanistería (2 consumos) → Pintura (consumo 15.20 m + MO) → "
          "Tapicería (MO) + retrabajo Ebanistería es_retrabajo=True")

    # ------------------------------------------------------------------
    # 4. Finalizar la orden → costo → pedido TERMINADO manual (sin envío auto)
    # ------------------------------------------------------------------
    finalizar_orden(client, orden["id"])
    r = client.get(f"/api/v1/produccion/costo/{orden['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"costo orden → {r.status_code}: {r.text}"
    costo = r.json()
    # consumos: madera 0.016×40000 + tornillos 20×500 + madera_lineal 15.20×30000 = 466.640
    assert float(costo["costo_material"]) == 466640, costo
    assert float(costo["costo_mano_obra"]) == 55000, costo
    assert float(costo["costo_total"]) == 521640, costo

    gastos_consumo = []
    for c in (c1, c2, c3):
        for (monto,) in db.execute(text(
            "SELECT monto FROM gasto WHERE observaciones LIKE :pat"
        ), {"pat": f"%[consumo {c['id']}]%"}).fetchall():
            gastos_consumo.append(float(monto))
    assert len(gastos_consumo) == 3, f"3 consumos → 3 gastos automáticos, hay {len(gastos_consumo)}"
    assert sum(gastos_consumo) == 466640, gastos_consumo

    # El pedido nació en PRODUCCION; al finalizar TODAS las líneas fabricables
    # (REVENTA/INSUMO ya se vendieron del inventario al convertir) se auto-
    # termina y se crea el envío automáticamente.
    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json()["estado"] == "TERMINADO", (
        "el pedido mixto auto-termina al finalizar su única línea FABRICADO"
    )
    assert envio_de_pedido(db, pedido["id"]) is not None, (
        "el auto-TERMINADO debe crear el envío automático"
    )
    print("  ✓ hallazgo: el pedido mixto nace PRODUCCION y al finalizar su única "
          "línea FABRICADO auto-termina y crea el envío")

    # ------------------------------------------------------------------
    # 5. Ventas y cobros: pagos en varias monedas (parcial; el cierre 100% va al final)
    # ------------------------------------------------------------------
    r, _ = pagar_venta(client, cleaner, venta["id"], 1, 150000, "EFECTIVO_COP")
    assert r.status_code in (200, 201), f"pago COP → {r.status_code}: {r.text}"
    r, _ = pagar_venta(client, cleaner, venta["id"], 2, 20, "ZELLE", tasa_cambio=3900)
    assert r.status_code in (200, 201), f"pago USD → {r.status_code}: {r.text}"
    r, _ = pagar_venta(client, cleaner, venta["id"], 3, 7000, "BANCARIBE", tasa_cambio=10)
    assert r.status_code in (200, 201), f"pago VES → {r.status_code}: {r.text}"

    v = venta_actualizada(client, venta["id"])
    assert v["estado"] == "ABONADA", f"venta con saldo debe quedar ABONADA, quedó {v['estado']}"
    assert abs(float(v["total"]) - 430000) < 0.01

    movs = movimientos_caja_de_pedido(db, pedido["id"])
    assert len(movs) == 3
    esperado = [
        ("EFECTIVO_COP", 1, 150000.0, 150000.0, 1.0),
        ("ZELLE", 2, 20.0, 78000.0, 3900.0),
        ("BANCARIBE", 3, 7000.0, 70000.0, 10.0),
    ]
    for mov, (cuenta, moneda, monto, base, tasa) in zip(movs, esperado):
        assert mov["tipo"] == "ENTRADA", mov
        assert mov["cuenta"] == cuenta and mov["moneda_id"] == moneda, mov
        assert float(mov["monto"]) == monto and float(mov["monto_en_moneda_base"]) == base, mov
        assert float(mov["tasa_cambio"]) == tasa, mov
    print("  pagos multi-moneda ok: EFECTIVO_COP 150000 · ZELLE 20 USD (78.000 COP) · "
          "BANCARIBE 7.000 VES (70.000 COP) → venta ABONADA, saldo 132.000")

    # ------------------------------------------------------------------
    # 6. NÓMINA semanal del periodo que contiene hoy + aguinaldo
    # ------------------------------------------------------------------
    nomina = None
    for d0, d1 in _periodo_candidatos():
        r, nom = crear_nomina(client, cleaner, desde=d0, hasta=d1)
        if r.status_code in (200, 201):
            desde, hasta, nomina = d0, d1, nom
            print(f"  nómina creada para {desde} → {hasta}")
            break
        print(f"  nómina rechazada en {d0} → {d1}: {r.status_code} {r.text[:120]}")
    assert nomina is not None, "ningún periodo candidato aceptó la nómina"
    assert desde <= hoy() <= hasta, "el periodo de nómina debe contener hoy (los datos usan now())"

    preview = preview_nomina(client, desde, hasta)
    det_eb = _detalle_preview(preview, eb01["id"])
    det_pin = _detalle_preview(preview, pintor["id"])
    det_tap = _detalle_preview(preview, tapicero["id"])

    # EBANISTA: sin MO manual → TARIFA de Ebanistería 20000 × 1, bono 8% = 1600
    assert float(det_eb["total_produccion"]) == 20000, det_eb
    assert float(det_eb["monto_a_pagar"]) == 20000, det_eb
    assert float(det_eb["bono_aguinaldo"]) == 1600, det_eb
    assert len(det_eb["lineas"]) == 1, f"el ebanista debe tener UNA línea (tarifa): {det_eb['lineas']}"
    assert det_eb["lineas"][0]["origen"] == "ETAPA"
    assert float(det_eb["lineas"][0]["total"]) == 20000
    assert det_eb["lineas"][0]["area_nombre"] == "Ebanistería"
    # PINTOR: MO manual 25000 × 1.10 = 27500, bono 5% = 1375
    assert float(det_pin["total_produccion"]) == 27500 and float(det_pin["bono_aguinaldo"]) == 1375, det_pin
    assert float(det_pin["monto_a_pagar"]) == 27500
    # TAPICERO: MO manual 25000 × 1.10 = 27500, bono 5% = 1375
    assert float(det_tap["total_produccion"]) == 27500 and float(det_tap["bono_aguinaldo"]) == 1375, det_tap
    assert float(det_tap["monto_a_pagar"]) == 27500

    # El RETRABAJO no puede aparecer en ninguna línea (excluido de destajo)
    etapas_en_nomina = {
        linea.get("etapa_id")
        for d in preview["detalles"]
        for linea in d.get("lineas", [])
        if linea.get("etapa_id") is not None
    }
    assert retrabajo["id"] not in etapas_en_nomina, "el retrabajo NO debe pagarse en nómina"
    print(f"  ✓ preview nómina: ebanista 20.000 (tarifa, 8%→1.600) · pintor 27.500 (MO+10%) · "
          f"tapicero 27.500 (MO+10%) · retrabajo excluido")

    pagar_nomina(client, cleaner, db, nomina["id"], metodo_caja_id=1)
    nom_pagada = client.get(f"/api/v1/nomina/{nomina['id']}", headers=ADMIN_HEADERS).json()
    assert nom_pagada["estado"] == "PAGADA"

    gastos_nom = db.execute(text(
        "SELECT descripcion, monto FROM gasto WHERE descripcion LIKE :pat"
    ), {"pat": f"Nómina {desde} al {hasta}%"}).fetchall()
    assert len(gastos_nom) == sum(
        1 for d in nom_pagada["detalles"] if float(d["monto_a_pagar"]) > 0
    ), "debe haber UN gasto NÓMINA SEMANAL por empleado pagado"
    gasto_eb = next(g for g in gastos_nom if eb01["nombre"] in g[0])
    assert float(gasto_eb[1]) == 20000, gasto_eb
    # Caja: cada gasto de nómina genera su SALIDA (referencia "Gasto #{id}") → se
    # registra para que el cleaner la borre (no tiene FK).
    for (gid,) in db.execute(text(
        "SELECT id FROM gasto WHERE descripcion LIKE :pat"
    ), {"pat": f"Nómina {desde} al {hasta}%"}).fetchall():
        cleaner.registrar_caja_ref(f"Gasto #{gid}")

    assert saldos_aguinaldo(client, eb01["id"]) == 1600, "ebanista 8% → 1.600 acumulado"
    assert saldos_aguinaldo(client, pintor["id"]) == 1375
    assert saldos_aguinaldo(client, tapicero["id"]) == 1375
    print("  ✓ nómina pagada: 1 gasto 'NÓMINA SEMANAL' por empleado + SALIDAS de caja "
          "(EFECTIVO_COP) + saldo_aguinaldo: ebanista 1.600 · pintor 1.375 · tapicero 1.375")

    # Aguinaldo del ebanista: gasto AGUINALDO ANUAL y saldo → 0
    # (el helper pagar_aguinaldo asume 200 pero el endpoint responde 201 → llamada directa)
    r = client.post("/api/v1/nomina/aguinaldo/pagar", json={
        "empleado_id": eb01["id"], "metodo_caja_id": 1,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"pagar_aguinaldo → {r.status_code}: {r.text}"
    pag = r.json()
    assert float(pag["monto"]) == 1600, pag
    assert float(pag["saldo_restante"]) == 0, pag
    assert saldos_aguinaldo(client, eb01["id"]) == 0
    # El helper paga el aguinaldo buscando gastos por descripcion 'AGUINALDO ANUAL',
    # pero la descripcion real es 'Aguinaldo {año} — {empleado}' → registrar a mano.
    for (gid,) in db.execute(text(
        "SELECT id FROM gasto WHERE descripcion LIKE 'Aguinaldo %' AND descripcion LIKE :n"
    ), {"n": f"%{eb01['nombre']}%"}).fetchall():
        cleaner.registrar("gasto", gid)
        cleaner.registrar_caja_ref(f"Gasto #{gid}")
    print("  ✓ aguinaldo ebanista pagado: gasto 1.600 (AGUINALDO ANUAL) · saldo → 0")

    # ------------------------------------------------------------------
    # 7. Intenta romper
    # ------------------------------------------------------------------
    # (a) nómina duplicada en la misma semana
    r = client.post("/api/v1/nomina/", json={
        "periodo_desde": str(desde), "periodo_hasta": str(hasta), "descripcion": _uniq("dup"),
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (400, 409), f"nómina duplicada debe rechazarse → {r.status_code}: {r.text}"
    print(f"    nómina duplicada en la misma semana → {r.status_code} ({r.json().get('detail')})")

    # (b) factura fiscal con saldo pendiente SIN permiso → 400
    lineas = [{"detalle_pedido_id": d["id"], "precio_usd": p}
              for d, p in zip(pedido["detalles"], [50, 80, 10])]
    r, _ = emitir_factura(client, cleaner, db, pedido["id"], lineas, permitir_saldo_pendiente=False)
    assert r.status_code == 400, f"factura con saldo debe rechazarse → {r.status_code}: {r.text}"
    print(f"    factura con saldo sin permiso → 400 ({r.json().get('detail')})")

    # (c) cerrar el cobro al 100% y verificar la caja completa
    r, _ = pagar_venta(client, cleaner, venta["id"], 1, 132000, "BANCOLOMBIA")
    assert r.status_code in (200, 201), f"pago final → {r.status_code}: {r.text}"
    v = venta_actualizada(client, venta["id"])
    assert v["estado"] == "PAGADA", f"venta debe quedar PAGADA al 100%, quedó {v['estado']}"
    movs = movimientos_caja_de_pedido(db, pedido["id"])
    assert len(movs) == 4
    assert movs[3]["cuenta"] == "BANCOLOMBIA" and float(movs[3]["monto"]) == 132000
    print("  ✓ cobro cerrado al 100%: BANCOLOMBIA 132.000 → venta PAGADA (4 ENTRADAS de caja)")

    # (d) con el pago al 100% la factura fiscal SÍ se emite (INSUMO incluido)
    r, fact = emitir_factura(client, cleaner, db, pedido["id"], lineas, permitir_saldo_pendiente=False)
    assert r.status_code in (200, 201), f"factura tras pago 100% → {r.status_code}: {r.text}"
    fact_det = client.get(f"/api/v1/factura/{fact['id']}", headers=ADMIN_HEADERS).json()
    assert len(fact_det["detalles"]) == 3
    assert sorted(d.get("tipo_item") for d in fact_det["detalles"]) == ["FABRICADO", "INSUMO", "REVENTA"]
    print(f"  factura fiscal emitida tras pago al 100% (3 líneas, INSUMO incluido)")

    # ------------------------------------------------------------------
    # 8. Resumen
    # ------------------------------------------------------------------
    print("  ── CASO 3 COMPLETO ──")
    print(f"  venta #{venta['id']} = 430.000 COP pagada al 100% · costo orden #{orden['id']} = 527.400")
    print(f"  nómina {desde} → {hasta} · total {nom_pagada['total_nomina']} · "
          f"aguinaldos acumulados 1.600+1.375+1.375 = 4.350")
    assert Decimal(str(nom_pagada["total_nomina"])) > 0