"""
test_e2e_estructura_desde_produccion.py
=======================================
Estructura de costes GENERADA DESDE LA PRODUCCIÓN (la joya del esquema):

Cuando un producto NO tiene estructura de costes, al finalizar su orden de
producción el sistema la genera con lo que REALMENTE se usó en el taller:

  - consumos normales → ElementoSeccion (cantidad POR UNIDAD, precio congelado)
  - componente (NOCHERO) → sección "EBANISTERÍA (NOCHEROS)"
  - mano de obra por área → CostoProduccionSeccion
  - consumos EXCEDENTES (daño) y de RETRABAJO → NO entran a la estructura
    (pero sí al costo real de la orden)
  - idempotente: una segunda orden no pisa la estructura ya generada

Ejecutar:  pytest test/test_e2e_estructura_desde_produccion.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_material,
    registrar_inventario_de_material,
)
from helpers_e2e import (
    area_id,
    cargos,
    convertir_cotizacion,
    crear_cotizacion_multidetalle,
    crear_empleado,
    crear_etapa,
    crear_producto_fabricado,
    entrar_stock_material,
    finalizar_orden,
)


def _avanzar(client, etapa_id, estado):
    r = client.put(f"/api/v1/produccion/etapa/{etapa_id}/estado",
                   params={"estado": estado}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _consumo(client, cleaner, db, etapa_id, material_id, cantidad, solicitante_id,
             seccion=None, componente=None, es_excedente=False, motivo=None):
    payload = {
        "etapa_produccion_id": etapa_id,
        "material_id": material_id,
        "cantidad": cantidad,
        "fecha": "2026-08-31T12:00:00",
        "solicitante_empleado_id": solicitante_id,
        "observaciones": "e2e estructura",
    }
    if seccion:
        payload["seccion"] = seccion
    if componente:
        payload["componente"] = componente
    if es_excedente:
        payload["es_excedente"] = True
        payload["motivo_exceso"] = motivo or "DAÑO"
    r = client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    body = r.json()
    cleaner.registrar("consumo_material", body["id"])
    registrar_inventario_de_material(db, cleaner, material_id)
    for (gid,) in db.execute(text(
        "SELECT id FROM gasto WHERE observaciones LIKE :pat"
    ), {"pat": f"%[consumo {body['id']}]%"}).fetchall():
        cleaner.registrar("gasto", gid)
    return body


def _mo(client, cleaner, etapa_id, empleado_id, monto):
    r = client.post("/api/v1/produccion/mano-obra/", json={
        "etapa_produccion_id": etapa_id,
        "empleado_id": empleado_id,
        "monto": monto,
        "porcentaje_recargo": 0.0,
        "listo_nomina": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    body = r.json()
    cleaner.registrar("mano_obra", body["id"])
    return body


def _estructura_producto(client, producto_id):
    r = client.get(f"/api/v1/producto/{producto_id}/receta-estructurada", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _costo_orden(client, db, orden_id):
    r = client.get(f"/api/v1/produccion/costo/{orden_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def test_estructura_generada_desde_produccion(client, cleaner, db):
    # ── Escenario: cama con nocheros, 2 unidades, sin estructura ──
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto_fabricado(client, cleaner, nombre=None)
    # El "estimado" del Excel: el producto trae su costo base histórico.
    r = client.put(f"/api/v1/producto/{producto['id']}", json={
        "precio_costo_base": 120000.0,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    madera = crear_material(client, cleaner, unidad_medida_id=2, costo_base=10000.0)
    tornillos = crear_material(client, cleaner, unidad_medida_id=1, costo_base=500.0)
    pintura = crear_material(client, cleaner, unidad_medida_id=1, costo_base=20000.0)
    for mat, cant in ((madera, 50), (tornillos, 200), (pintura, 20)):
        entrar_stock_material(client, cleaner, mat["id"], cant)

    emp = crear_empleado(client, cleaner, cargo_id=cargos(db)["ebanista"], en_nomina=True)

    # Cotización + pedido con cantidad 2 (una orden cubre las 2 unidades).
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        {"producto_id": producto["id"], "tipo_item": "FABRICADO", "cantidad": 2, "precio": 400000},
    ])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [
        {"producto_id": producto["id"], "tipo_item": "FABRICADO", "cantidad": 2, "precio": 400000},
    ])
    assert r.status_code == 201, r.text
    detalle_id = pedido["detalles"][0]["id"]

    r = client.post(f"/api/v1/produccion/orden/desde-pedido/{detalle_id}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    orden = r.json()
    cleaner.registrar("orden_produccion", orden["id"])

    eban = area_id(db, "Ebanistería")
    pint = area_id(db, "Pintura")

    # ── Producción: Ebanistería → Pintura + un RETRABAJO en Ebanistería ──
    etapa_eb = crear_etapa(client, cleaner, orden["id"], eban, emp["id"])
    _avanzar(client, etapa_eb["id"], "EN_PROCESO")
    _consumo(client, cleaner, db, etapa_eb["id"], madera["id"], 8, emp["id"],
             seccion="EBANISTERIA", componente="NOCHERO")      # nochero
    _consumo(client, cleaner, db, etapa_eb["id"], tornillos["id"], 20, emp["id"],
             seccion="EBANISTERIA")                            # cama
    _consumo(client, cleaner, db, etapa_eb["id"], madera["id"], 3, emp["id"],
             seccion="EBANISTERIA", componente="NOCHERO",
             es_excedente=True, motivo="DAÑO")                 # EXTRA: excluido
    _mo(client, cleaner, etapa_eb["id"], emp["id"], 10000)
    _avanzar(client, etapa_eb["id"], "COMPLETADA")

    # Retrabajo en Ebanistería (área ya completada) → es_retrabajo=True.
    etapa_re = crear_etapa(client, cleaner, orden["id"], eban, emp["id"])
    assert etapa_re["es_retrabajo"] is True, "La etapa re-creada debe ser retrabajo"
    _avanzar(client, etapa_re["id"], "EN_PROCESO")
    _consumo(client, cleaner, db, etapa_re["id"], madera["id"], 2, emp["id"],
             seccion="EBANISTERIA", componente="NOCHERO")      # retrabajo: excluido
    _avanzar(client, etapa_re["id"], "COMPLETADA")

    etapa_pi = crear_etapa(client, cleaner, orden["id"], pint, emp["id"])
    _avanzar(client, etapa_pi["id"], "EN_PROCESO")
    _consumo(client, cleaner, db, etapa_pi["id"], pintura["id"], 4, emp["id"],
             seccion="PINTURA")
    _mo(client, cleaner, etapa_pi["id"], emp["id"], 8000)
    _avanzar(client, etapa_pi["id"], "COMPLETADA")

    # ── Costos EN VIVO antes de finalizar (desglose por sección, estilo Excel) ──
    r = client.get(f"/api/v1/produccion/orden/{orden['id']}/costos-en-vivo", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    vivo = r.json()
    sec_vivo = {s["nombre"]: s for s in vivo["secciones"]}
    # Agrupación: componente NOCHERO → "EBANISTERÍA (NOCHEROS)".
    sec_nv = sec_vivo.get("EBANISTERÍA (NOCHEROS)")
    assert sec_nv is not None, list(sec_vivo)
    # Insumos de nochero: 8 normal + 3 EXCEDENTE + 2 RETRABAJO = 13 m (todo visible).
    madera_vivo = [i for i in sec_nv["insumos"] if i["nombre"] == madera["nombre"]]
    assert sum(i["cantidad"] for i in madera_vivo) == 13.0
    assert sum(i["total"] for i in madera_vivo) == 13 * 10000
    assert any(i["es_excedente"] for i in madera_vivo)
    assert any(i["es_retrabajo"] for i in madera_vivo)
    # La MO cae en la sección BASE del área (EBANISTERÍA), no en la de NOCHEROS.
    assert sec_nv["produccion"] == []
    sec_eb_vivo = sec_vivo.get("EBANISTERÍA")
    assert sec_eb_vivo is not None
    # Producción con el recargo del 8% (mismo criterio que la estructura).
    assert any(p["base"] == 10000.0 and p["porcentaje"] == 8.0 for p in sec_eb_vivo["produccion"])
    assert any(p["base"] == 8000.0 and p["porcentaje"] == 8.0 for p in sec_vivo["PINTURA"]["produccion"])
    # Coherencia interna: gastos = subtotal × pct_gastos.
    for s in vivo["secciones"]:
        esperado_gastos = round(s["subtotal"] * s["pct_gastos"] / 100, 2)
        assert s["gastos"] == esperado_gastos, s
    assert vivo["totales"]["materiales"] == 220000.0  # 13m+10t+4p a sus precios... 130000+10000+80000
    assert vivo["totales"]["mano_obra"] == (10000 + 8000) * 1.08  # 19440 con el 8%
    assert vivo["estimado"] == 120000.0 * 2  # costo base histórico × 2 unidades

    # ── Finalizar → estructura generada ──
    r = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado",
                   params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json().get("estructura_generada") is True, "Debe generar la estructura"

    # Costos en vivo tras finalizar: el estimado congelado y el costo real flat.
    r = client.get(f"/api/v1/produccion/orden/{orden['id']}/costos-en-vivo", headers=ADMIN_HEADERS)
    vivo_fin = r.json()
    assert vivo_fin["costo_estimado"] == 120000.0 * 2, "El estimado se congela al finalizar"
    costo_flat = _costo_orden(client, db, orden["id"])
    assert vivo_fin["costo_real_total"] == costo_flat["costo_total"]

    estructura = _estructura_producto(client, producto["id"])
    secciones = {s["nombre"]: s for s in estructura}
    print("[E2E estructura] secciones:", list(secciones.keys()))

    # 1. Componente NOCHERO → sección propia con la regla de gastos del 5%.
    sec_nochero = secciones.get("EBANISTERÍA (NOCHEROS)")
    assert sec_nochero is not None, f"Falta sección NOCHEROS: {list(secciones)}"
    assert sec_nochero["politica"]["pct_gastos_seccion"] == 5.0
    elems_nochero = {e["nombre_insumo_original"]: e for e in sec_nochero["elementos"]}
    assert madera["nombre"] in elems_nochero
    # 8 m ÷ 2 unidades = 4 m por unidad (el consumo EXTRA y el RETRABAJO NO entran).
    assert elems_nochero[madera["nombre"]]["cantidad"] == 4.0
    assert elems_nochero[madera["nombre"]]["estado_resolucion"] == "MAPEADO"
    assert elems_nochero[madera["nombre"]]["material_id_normalizado"] == madera["id"]
    assert elems_nochero[madera["nombre"]]["precio_unitario"] == 10000.0

    # 2. Sección EBANISTERÍA: la cama (tornillos) + su mano de obra.
    sec_eb = secciones.get("EBANISTERÍA")
    assert sec_eb is not None
    elems_eb = {e["nombre_insumo_original"]: e for e in sec_eb["elementos"]}
    assert tornillos["nombre"] in elems_eb
    assert elems_eb[tornillos["nombre"]]["cantidad"] == 10.0  # 20 ÷ 2
    # MO de ebanistería: 10000 ÷ 2 = 5000 por unidad, con el recargo de
    # producción del 8% (formato Excel "FABRICACION X *8%" → aporte 5400).
    costos_eb = {c["nombre"]: c for c in sec_eb["costos_produccion"]}
    cp_eb = [c for c in sec_eb["costos_produccion"] if c["costo_base"] == 5000.0]
    assert cp_eb, costos_eb
    assert cp_eb[0]["porcentaje"] == 8.0

    # 3. Sección PINTURA: pintura + MO 8000 ÷ 2 = 4000 (también con 8%).
    sec_pi = secciones.get("PINTURA")
    assert sec_pi is not None
    elems_pi = {e["nombre_insumo_original"]: e for e in sec_pi["elementos"]}
    assert pintura["nombre"] in elems_pi
    assert elems_pi[pintura["nombre"]]["cantidad"] == 2.0  # 4 ÷ 2
    cp_pi = [c for c in sec_pi["costos_produccion"] if c["costo_base"] == 4000.0]
    assert cp_pi, sec_pi["costos_produccion"]
    assert cp_pi[0]["porcentaje"] == 8.0

    # 4. El consumo EXTRA (3 m) y el RETRABAJO (2 m) NO están en la estructura:
    #    la madera total en estructura = 8 m (solo el normal).
    total_madera_estructura = sum(
        e["cantidad"] for s in estructura for e in s["elementos"]
        if e["nombre_insumo_original"] == madera["nombre"]
    )
    assert total_madera_estructura == 4.0  # por unidad

    # 5. Coherencia con el costo REAL de la orden: la estructura lleva la MO
    #    CON su recargo (base × 1.08); la orden real, el monto registrado.
    costo = _costo_orden(client, db, orden["id"])
    insumos_estructura = sum(
        e["cantidad"] * (e["precio_unitario"] or 0) for s in estructura for e in s["elementos"]
    )
    mo_estructura_base = sum(c["costo_base"] for s in estructura for c in s["costos_produccion"])
    mo_estructura = sum(
        c["costo_base"] * (1 + (c["porcentaje"] or 0) / 100)
        for s in estructura for c in s["costos_produccion"]
    )
    assert insumos_estructura == 4 * 10000 + 10 * 500 + 2 * 20000  # 85000
    assert mo_estructura_base == 5000 + 4000  # 9000
    assert mo_estructura == (5000 + 4000) * 1.08  # 9720 con el recargo del 8%
    esperado = (insumos_estructura + mo_estructura_base) * 2 + (3 * 10000) + (2 * 10000)
    assert float(costo["costo_material"]) + float(costo["costo_mano_obra"]) == esperado

    # 5b. Comparativa estimado vs real: el estimado se congeló del costo base
    #     histórico del producto (120000) × las 2 unidades del detalle.
    assert costo["costo_estimado"] == 120000.0 * 2

    # 6. El motor de costeo ahora usa la estructura generada.
    r = client.get(f"/api/v1/producto/{producto['id']}/calcular-precio",
                   params={"ancho": 1.60, "largo": 1.90}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    precio = r.json()
    assert precio.get("fuente_precio") == "estructura_de_costos", precio.get("fuente_precio")

    # 6b. El costo del taller se pasó al producto: precio_costo_base actualizado
    #     con la estructura (insumos + producción × 1.08 + gastos por sección)
    #     y precio_venta_base recalculado.
    r = client.get(f"/api/v1/producto/{producto['id']}", headers=ADMIN_HEADERS)
    prod = r.json()
    assert prod["precio_costo_base"] is not None and prod["precio_costo_base"] > 0
    assert prod["precio_costo_base"] == precio["resumen_costos"]["costo_produccion"]
    assert prod["precio_venta_base"] is not None and prod["precio_venta_base"] > 0

    # 7. Idempotencia: una segunda orden NO pisa la estructura.
    #    (simulamos otra producción del mismo producto con otro pedido)
    r = client.post(f"/api/v1/produccion/orden/desde-pedido/{detalle_id}", headers=ADMIN_HEADERS)
    orden2 = r.json()
    # Re-abrir la misma orden no sirve (ya FINALIZADA): creamos otra orden de
    # stock del mismo producto para probar que no regenera.
    r = client.post("/api/v1/produccion/orden/", json={
        "estado": "PENDIENTE",
        "es_stock": True,
        "producto_id": producto["id"],
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    orden_stock = r.json()
    cleaner.registrar("orden_produccion", orden_stock["id"])
    etapa_s = crear_etapa(client, cleaner, orden_stock["id"], eban, emp["id"])
    _avanzar(client, etapa_s["id"], "EN_PROCESO")
    _consumo(client, cleaner, db, etapa_s["id"], madera["id"], 10, emp["id"], seccion="EBANISTERIA")
    _avanzar(client, etapa_s["id"], "COMPLETADA")
    r = client.put(f"/api/v1/produccion/orden/{orden_stock['id']}/estado",
                   params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json().get("estructura_generada") is False, "No debe pisar la estructura existente"

    # 7b. El estimado de la segunda orden se congela del precio_costo_base
    #     ya actualizado del producto (1 unidad de stock).
    costo2 = _costo_orden(client, db, orden_stock["id"])
    assert costo2["costo_estimado"] == prod["precio_costo_base"]

    estructura2 = _estructura_producto(client, producto["id"])
    assert len(estructura2) == len(estructura), "La estructura no debe cambiar"
    print("[E2E estructura] orden costo real:", esperado,
          "| estructura por unidad:", insumos_estructura + mo_estructura)