# -*- coding: utf-8 -*-
"""
test_e2e_caso4.py — CASO 4 "El mueble entregado y devuelto (cliente insatisfecho)".

Flujo E2E completo de un mueble FABRICADO con UN RETRABAJO:

  cliente + 1 producto fabricado con receta de madera → stock de material →
  cotización COP → pedido (venta PENDIENTE, sin adelanto) → producción con un
  RETRABAJO en Ebanistería (etapa original COMPLETADA + etapa recreada con
  es_retrabajo=True, también COMPLETADA; consumos + mano de obra solo en la
  original) → pedido TERMINADO + envío PREPARADO → cobro multi-moneda al 100%
  (USD/VES/COP) → factura fiscal EMITIDA → envío con chofer + guía + vista del
  chofer → EN_TRANSITO → ENTREGADO → DEVOLUCIÓN de la venta por el cliente
  insatisfecho (SALIDA de caja desde la cuenta del último pago, misma moneda).

Asserts de integridad: stock del material NO se repone (la devolución actual
solo reembolsa dinero en caja, no revierte inventario — HALLAZGO documentado),
la venta sigue PAGADA (la devolución no cambia su estado — HALLAZGO), la caja
recibe una SALIDA en la cuenta/moneda del último pago, el reembolso no puede
exceder lo cobrado, y en la NÓMINA semanal el retrabajo NO aparece (solo la
etapa original paga destajo).

Ejecutar:
  cd backend && source venv/bin/activate && python -m pytest test/test_e2e_caso4.py -v
"""
import pytest
from datetime import date
from sqlalchemy import text

from conftest import ADMIN_HEADERS, _uniq, crear_cliente, crear_material, crear_orden_desde_pedido, crear_receta
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
    crear_producto_fabricado,
    crear_usuario_chofer,
    convertir_cotizacion,
    emitir_factura,
    entrar_stock_material,
    envio_de_pedido,
    finalizar_orden,
    movimientos_caja_de_pedido,
    pagar_venta,
    preview_nomina,
    registrar_mano_obra,
    semana_actual,
    stock_material,
    venta_actualizada,
    venta_de_pedido,
)


# ---------------------------------------------------------------------------
# CASO 4
# ---------------------------------------------------------------------------
def test_caso4_mueble_devuelto_retrabajo_nomina(client, cleaner, db):
    """Mueble entregado y devuelto: producción con retrabajo, cobro mixto,
    factura, envío entregado, devolución con SALIDA de caja y nómina que
    excluye el retrabajo."""

    # ── 1. Datos base: cliente + mueble fabricado con receta de madera ──────
    cliente = crear_cliente(client, cleaner, nombre=_uniq("cliente_devuelto"))
    producto = crear_producto_fabricado(client, cleaner, costo_base=80000.0)
    madera = crear_material(client, cleaner, nombre=_uniq("madera"),
                            costo_base=1500.0, unidad_medida_id=2)  # m lineal
    crear_receta(client, cleaner, producto["id"], madera["id"], cantidad_base=2.0,
                 tipo_escala="FIJO", seccion="EBANISTERIA")
    entrar_stock_material(client, cleaner, madera["id"], 100)  # 100 m

    ebanista1 = crear_empleado(client, cleaner, nombre=_uniq("ebanista1"),
                               cargo_id=cargo_id(db, "EBANISTA"),
                               en_nomina=True, tipo_pago="DESTAJO")
    ebanista2 = crear_empleado(client, cleaner, nombre=_uniq("ebanista2"),
                               cargo_id=cargo_id(db, "EBANISTA"),
                               en_nomina=True, tipo_pago="DESTAJO")
    chofer = crear_empleado(client, cleaner, nombre=_uniq("chofer"),
                            cargo_id=cargo_id(db, "CHOFER"))

    # ── 2. Cotización COP → pedido (sin adelanto, venta PENDIENTE) ───────────
    precio = 3_000_000.0
    detalles_cot = [
        {"producto_id": producto["id"], "tipo_item": "FABRICADO", "cantidad": 1,
         "precio": precio, "ancho": 1.60, "largo": 1.90}
    ]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], detalles_cot,
                                        moneda_id=1, tasa_cambio=1.0)
    assert float(cot["total_estimado"]) == pytest.approx(precio)

    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], detalles_cot)
    assert r.status_code == 201, f"convertir_cotizacion → {r.status_code}: {r.text}"
    venta = venta_de_pedido(client, db, pedido["id"])
    assert venta is not None, "La conversión debe auto-crear la venta"
    assert venta["estado"] == "PENDIENTE", venta["estado"]
    assert float(venta["total"]) == pytest.approx(precio)
    venta_id = venta["id"]

    # ── 3. Producción con UN RETRABAJO (Ebanistería re-abierta) ──────────────
    orden = crear_orden_desde_pedido(client, cleaner, pedido["detalles"][0]["id"])
    assert orden["estado"] == "PENDIENTE"

    # Etapa ORIGINAL en Ebanistería: consumo + mano de obra → COMPLETADA.
    et_orig = crear_etapa(client, cleaner, orden["id"], area_id(db, "Ebanistería"),
                          ebanista1["id"])
    avanzar_etapa(client, et_orig["id"], "EN_PROCESO")
    r, cons_orig = crear_consumo(client, cleaner, db, et_orig["id"], madera["id"], 3.0,
                                 ebanista1["id"], seccion="EBANISTERIA")
    assert cons_orig is not None, f"consumo etapa original → {r.status_code}: {r.text}"
    registrar_mano_obra(client, cleaner, et_orig["id"], ebanista1["id"], 30000.0)
    avanzar_etapa(client, et_orig["id"], "COMPLETADA")

    # RETRABAJO: etapa recreada en el mismo área (ya COMPLETADA) de la orden.
    et_re = crear_etapa(client, cleaner, orden["id"], area_id(db, "Ebanistería"),
                        ebanista2["id"])
    assert et_re["es_retrabajo"] is True, \
        f"La etapa recreada debe marcarse como retrabajo: {et_re}"
    # Re-chequeo por la respuesta GET de la etapa (contrato del caso).
    g = client.get(f"/api/v1/produccion/etapa/{et_re['id']}", headers=ADMIN_HEADERS)
    assert g.status_code == 200 and g.json()["es_retrabajo"] is True, g.text
    avanzar_etapa(client, et_re["id"], "EN_PROCESO")
    r, cons_re = crear_consumo(client, cleaner, db, et_re["id"], madera["id"], 1.5,
                               ebanista2["id"], seccion="EBANISTERIA")
    assert cons_re is not None, f"consumo retrabajo → {r.status_code}: {r.text}"
    # El retrabajo NO registra mano de obra: no debe pagarse destajo dos veces.
    avanzar_etapa(client, et_re["id"], "COMPLETADA")

    # Finalizar → pedido TERMINADO + envío PREPARADO automático.
    finalizar_orden(client, orden["id"])
    estado_pedido = db.execute(text("SELECT estado FROM pedido WHERE id=:p"),
                               {"p": pedido["id"]}).scalar()
    assert estado_pedido == "TERMINADO", f"Pedido debe quedar TERMINADO: {estado_pedido}"
    envio = envio_de_pedido(db, pedido["id"])
    assert envio is not None and envio["estado"] == "PREPARADO", envio
    cleaner.registrar("envio", envio["id"])
    envio_id = envio["id"]

    # ── 4. Cobro al 100% con mezcla de monedas + factura EMITIDA ─────────────
    # 100 USD @ 3900 → 390000 COP; 1000 VES @ 10 → 10000 COP; resto COP.
    r, p_usd = pagar_venta(client, cleaner, venta_id, 2, 100.0, "ZELLE", tasa_cambio=3900.0)
    assert r.status_code == 201, f"pago USD → {r.status_code}: {r.text}"
    assert float(p_usd["monto_en_moneda_base"]) == pytest.approx(390000.0)
    r, p_ves = pagar_venta(client, cleaner, venta_id, 3, 1000.0, "BANCARIBE", tasa_cambio=10.0)
    assert r.status_code == 201, f"pago VES → {r.status_code}: {r.text}"
    assert float(p_ves["monto_en_moneda_base"]) == pytest.approx(10000.0)
    r, p_cop = pagar_venta(client, cleaner, venta_id, 1, 2_600_000.0, "EFECTIVO_COP")
    assert r.status_code == 201, f"pago COP → {r.status_code}: {r.text}"
    venta_final = venta_actualizada(client, venta_id)
    assert venta_final["estado"] == "PAGADA", venta_final["estado"]
    assert float(venta_final["saldo_pendiente"]) == pytest.approx(0.0, abs=0.01)

    r, factura = emitir_factura(client, cleaner, db, pedido["id"],
                                [{"detalle_pedido_id": pedido["detalles"][0]["id"],
                                  "precio_usd": round(precio / 3900.0, 2)}],
                                tasa_usd_ves=50.0, permitir_saldo_pendiente=False)
    assert r.status_code == 201, f"emitir_factura → {r.status_code}: {r.text}"
    assert factura["estado"] == "EMITIDA"

    # ── 5. Envío: chofer + guía + vista del chofer + ENTREGADO ───────────────
    asignar_chofer(client, envio_id, chofer["id"])
    r = client.put(f"/api/v1/envio/{envio_id}", json={"guia_despacho": "G-CASO4-0001"},
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200 and r.json()["guia_despacho"] == "G-CASO4-0001", r.text
    n_asig = db.execute(text(
        "SELECT COUNT(*) FROM envio_asignacion WHERE envio_id = :e AND empleado_id = :c"
    ), {"e": envio_id, "c": chofer["id"]}).scalar()
    assert n_asig >= 1, "Debe quedar un registro en envio_asignacion del chofer"

    chofer_headers = crear_usuario_chofer(db, cleaner, chofer["id"])
    r = client.get("/api/v1/envio/mis-asignaciones", params={"estado": "PREPARADO"},
                   headers=chofer_headers)
    assert r.status_code == 200, f"mis-asignaciones → {r.status_code}: {r.text}"
    assert any(e["id"] == envio_id for e in r.json()), \
        f"El envío debe aparecer en las asignaciones del chofer: {r.json()}"

    avanzar_envio(client, envio_id, "EN_TRANSITO")
    avanzar_envio(client, envio_id, "ENTREGADO")
    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200 and r.json()["estado"] == "ENTREGADO", r.json()

    # ── 6. DEVOLUCIÓN de la venta (cliente insatisfecho) ─────────────────────
    stock_antes = stock_material(db, madera["id"])
    n_pagos_antes = db.execute(text("SELECT COUNT(*) FROM pago WHERE venta_id=:v"),
                               {"v": venta_id}).scalar()

    # 6a. El reembolso sale de la cuenta del ÚLTIMO pago (EFECTIVO_COP, COP).
    dev_payload = {
        "venta_id": venta_id,
        "fecha": str(date.today()),
        "cantidad": 1,
        "motivo": "Cliente insatisfecho con el acabado",
        "monto_devuelto": 1_500_000,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
    }
    r = client.post("/api/v1/reports/devoluciones", json=dev_payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"devolucion → {r.status_code}: {r.text}"
    dev = r.json()
    cleaner.registrar("devolucion_venta", dev["id"])
    cleaner.registrar_caja_ref(f"Devolución venta #{venta_id}")
    assert float(dev["monto_en_moneda_base"]) == pytest.approx(1_500_000.0), dev

    # 6b. SALIDA de caja desde la cuenta del último pago, misma moneda.
    rows = db.execute(text(
        """SELECT mc.tipo, mc.monto, mc.moneda_id, mc.tasa_cambio,
                  mc.monto_en_moneda_base, mca.codigo AS cuenta
           FROM movimiento_caja mc
           JOIN metodo_caja mca ON mca.id = mc.metodo_caja_id
           WHERE mc.referencia = :ref"""
    ), {"ref": f"Devolución venta #{venta_id}"}).fetchall()
    assert len(rows) == 1, f"Debe existir 1 SALIDA de devolución, hay {len(rows)}"
    salida = dict(rows[0]._mapping)
    assert salida["tipo"] == "SALIDA", salida
    assert salida["cuenta"] == "EFECTIVO_COP", salida
    assert salida["moneda_id"] == 1, salida
    assert float(salida["monto"]) == pytest.approx(1_500_000.0), salida
    assert float(salida["monto_en_moneda_base"]) == pytest.approx(1_500_000.0), salida

    # 6c. La venta sigue PAGADA (la devolución NO la cancela ni cambia su estado).
    v_post = venta_actualizada(client, venta_id)
    assert v_post["estado"] == "PAGADA", v_post["estado"]

    # 6d. No se crea ningún pago/egreso extra en la venta (solo la SALIDA).
    n_pagos_post = db.execute(text("SELECT COUNT(*) FROM pago WHERE venta_id=:v"),
                              {"v": venta_id}).scalar()
    assert n_pagos_post == n_pagos_antes, "La devolución no debe crear pagos"

    # 6e. La devolución NO repone stock del material (solo reembolsa dinero).
    assert stock_material(db, madera["id"]) == pytest.approx(stock_antes, abs=0.001), \
        "La devolución actual no revierte inventario (documentar hallazgo)"

    # 6f. Guardia: no se puede devolver más de lo cobrado (o reembolsar N veces).
    r2 = client.post("/api/v1/reports/devoluciones", json={
        **dev_payload, "monto_devuelto": 1_600_000,
    }, headers=ADMIN_HEADERS)
    assert r2.status_code == 400, f"Reembolso excesivo debe ser 400: {r2.status_code}: {r2.text}"
    n_dev = db.execute(text("SELECT COUNT(*) FROM devolucion_venta WHERE venta_id=:v"),
                       {"v": venta_id}).scalar()
    assert n_dev == 1, "El reembolso rechazado no debe quedar registrado"

    # ── 7. Nómina semanal: el retrabajo NO aparece (solo la etapa original) ──
    draft = preview_nomina(client, *semana_actual())
    det_ebanista1 = next((d for d in draft["detalles"] if d["empleado_id"] == ebanista1["id"]), None)
    det_ebanista2 = next((d for d in draft["detalles"] if d["empleado_id"] == ebanista2["id"]), None)
    assert det_ebanista1 is not None, "El ebanista de la etapa original debe estar en nómina"
    assert det_ebanista2 is not None, "El ebanista del retrabajo debe estar en nómina"
    lineas1 = det_ebanista1["lineas"]
    lineas2 = det_ebanista2["lineas"]
    assert len(lineas1) == 1, f"La etapa original debe generar 1 línea, hay {len(lineas1)}: {lineas1}"
    assert lineas1[0]["etapa_id"] == et_orig["id"], lineas1
    assert lineas2 == [], f"El retrabajo no debe pagar destajo, pero hay líneas: {lineas2}"
    ids_en_nomina = {l["etapa_id"] for d in draft["detalles"] for l in d["lineas"]}
    assert et_re["id"] not in ids_en_nomina, \
        f"La etapa de retrabajo {et_re['id']} no debe estar en la nómina: {ids_en_nomina}"
    assert et_orig["id"] in ids_en_nomina

    # ── 8. Resumen ───────────────────────────────────────────────────────────
    movs = movimientos_caja_de_pedido(db, pedido["id"])
    print("[CASO 4] venta PAGADA %.2f COP | factura %s | envio %s | pedido %s"
          % (venta_final["total_pagado"], factura["estado"],
             "ENTREGADO", "ENTREGADO"))
    print("[CASO 4] retrabajo etapa #%d es_retrabajo=True | stock madera %.2f m (sin reponer)"
          % (et_re["id"], stock_material(db, madera["id"])))
    print("[CASO 4] devolución SALIDA %.2f %s en %s | venta sigue %s | %d mov caja"
          % (float(salida["monto"]), "COP", salida["cuenta"], v_post["estado"], len(movs)))
    print("[CASO 4] nómina: etapa original #%d en líneas (1) | retrabajo #%d excluido (%d líneas)"
          % (et_orig["id"], et_re["id"], len(lineas2)))