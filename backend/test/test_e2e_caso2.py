# -*- coding: utf-8 -*-
"""
test_e2e_caso2.py — Caso 2 "Mixto con reventa: un abono y el otro no; factura al 100% vs con saldo".

TEST A (test_caso2a_dos_muebles_abono_inicial_factura_al_100):
    Cliente + 2 muebles FABRICADOS (receta de madera en m³ + stock) → cotización
    COP con abono inicial (~30%) → producción completa por áreas (etapas en
    Ebanistería + Pintura, consumos con solicitante, mano de obra) → finalizar
    → pedido TERMINADO vía automática (todas las líneas FABRICADO) → envío
    auto-creado → pagos multi-moneda (USD ZELLE, VES BANCARIBE, COP) hasta 100%
    → factura al 100% (permitir=False) → 201. Asserts de caja por pago.

TEST B (test_caso2b_dos_reventas_sin_abono_factura_con_saldo):
    Cliente + 2 productos REVENTA con stock (5 uds c/u) → cotización COP con 2
    renglones REVENTA → convertir SIN abono (stock descontado AL INSTANTE).
    Intento de ruptura: factura con saldo sin autorizar → 400 "100%"; factura
    con autorización del admin → 201 EMITIDA antes del pago completo;
    sobrepago → 400; método de pago con moneda incoherente (ZELLE + COP) → 400.
    Pagos multi-moneda hasta 100% → PAGADA. Como REVENTA no produce: NINGUNA
    orden de producción ni envío (SELECT en BD). Asserts de caja.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_e2e_caso2.py -v
"""
import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_material,
    crear_orden_desde_pedido,
    crear_receta,
)
from helpers_e2e import (
    area_id,
    cargo_id,
    crear_cliente,
    crear_consumo,
    crear_cotizacion_multidetalle,
    crear_empleado,
    crear_etapa,
    crear_producto_fabricado,
    crear_producto_reventa,
    crear_stock_producto,
    avanzar_etapa,
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
    stock_producto,
    venta_actualizada,
)


# ---------------------------------------------------------------------------
# Helpers locales (no tocan conftest.py / helpers_e2e.py)
# ---------------------------------------------------------------------------

def _producir_mueble(client, cleaner, db, detalle_id, material_id, area_1, area_2,
                     emp1_id, emp2_id, cantidad_material):
    """Crea la orden del detalle, dos etapas (área_1, área_2), consume material
    en cada una (con solicitante), registra mano de obra y finaliza la orden."""
    orden = crear_orden_desde_pedido(client, cleaner, detalle_id)
    etapa1 = crear_etapa(client, cleaner, orden["id"], area_1, emp1_id, estado="ASIGNADA")
    etapa2 = crear_etapa(client, cleaner, orden["id"], area_2, emp2_id, estado="ASIGNADA")
    for etapa, emp_resp in ((etapa1, emp1_id), (etapa2, emp2_id)):
        avanzar_etapa(client, etapa["id"], "EN_PROCESO")
        r, cons = crear_consumo(client, cleaner, db, etapa["id"], material_id,
                                cantidad=cantidad_material, solicitante_id=emp_resp)
        assert r.status_code == 201, f"consumo → {r.status_code}: {r.text}"
        assert cons["solicitante_empleado_id"] == emp_resp
        registrar_mano_obra(client, cleaner, etapa["id"], emp_resp, monto=45000.0,
                            observaciones=_uniq("c2a_mo"))
        avanzar_etapa(client, etapa["id"], "COMPLETADA")
    finalizar_orden(client, orden["id"])
    return orden


def _detalle_ids(pedido):
    return [d["id"] for d in pedido["detalles"]]


def _delta_saldo(client, codigo, moneda_id, antes):
    """Cuánto subió la cuenta (código, moneda) desde `antes` hasta ahora."""
    return saldo_cuenta(client, codigo, moneda_id) - antes


def _venta_detalle(client, db, pedido_id):
    """GET /venta/{id} (VentaDetalleResponse: total_pagado, saldo_pendiente, pagos)."""
    row = db.execute(text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}).fetchone()
    assert row is not None, "La conversión debe auto-crear la venta"
    r = client.get(f"/api/v1/venta/{row[0]}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET /venta/{row[0]} → {r.status_code}: {r.text}"
    return r.json()


def _registrar_inventario_producto(db, cleaner, producto_id):
    """Registra TODOS los movimientos e inventario del producto de reventa
    (ENTRADA manual + SALIDA generada por la conversión/venta), para que el
    teardown pueda borrar el producto sin violar la FK movimiento → producto."""
    for (mid,) in db.execute(text(
        "SELECT id FROM movimiento_producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchall():
        cleaner.registrar("movimiento_producto_inventario", mid)
    for (iid,) in db.execute(text(
        "SELECT id FROM producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchall():
        cleaner.registrar("producto_inventario", iid)


# ---------------------------------------------------------------------------
# TEST A — 2 muebles FABRICADOS con abono inicial → producción → 100% → factura
# ---------------------------------------------------------------------------
def test_caso2a_dos_muebles_abono_inicial_factura_al_100(client, cleaner, db):
    # 1. Cliente + 2 productos FABRICADOS con receta de madera (m³) y stock.
    cliente = crear_cliente(client, cleaner, nombre=_uniq("c2a_cli"))
    mueble1 = crear_producto_fabricado(client, cleaner, nombre=_uniq("c2a_mueble1"), costo_base=80000.0)
    mueble2 = crear_producto_fabricado(client, cleaner, nombre=_uniq("c2a_mueble2"), costo_base=75000.0)
    madera = crear_material(client, cleaner, nombre=_uniq("c2a_madera"),
                            costo_base=1200000.0, unidad_medida_id=193)  # m³
    for p in (mueble1, mueble2):
        crear_receta(client, cleaner, p["id"], madera["id"], cantidad_base=0.05,
                     tipo_escala="FIJO", seccion="EBANISTERIA")
    entrar_stock_material(client, cleaner, madera["id"], cantidad=2.0)
    db.expire_all()
    assert stock_material(db, madera["id"]) == pytest.approx(2.0)

    # 2. Cotización COP con 2 detalles FABRICADO → convertir con ABONO INICIAL (~30%).
    precio1, precio2 = 200000.0, 200000.0
    detalles_cot = [
        {"producto_id": mueble1["id"], "tipo_item": "FABRICADO", "cantidad": 1,
         "precio": precio1, "ancho": 1.60, "largo": 1.90},
        {"producto_id": mueble2["id"], "tipo_item": "FABRICADO", "cantidad": 1,
         "precio": precio2, "ancho": 1.60, "largo": 1.90},
    ]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], detalles_cot,
                                        moneda_id=1, tasa_cambio=1.0)
    total = precio1 + precio2  # 400000 COP
    adelanto = 120000.0        # ~30%
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], detalles_cot,
                                     adelanto=adelanto, moneda_adelanto_id=1,
                                     metodo_pago="EFECTIVO_COP")
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    venta = _venta_detalle(client, db, pedido["id"])
    assert venta["estado"] == "ABONADA", f"Con abono parcial → ABONADA, fue {venta['estado']}"
    assert venta["total_pagado"] == pytest.approx(adelanto)
    assert venta["saldo_pendiente"] == pytest.approx(total - adelanto)

    # 3. Producción completa de ambos muebles (2 áreas por orden).
    ebanisteria = area_id(db, "Ebanistería")
    pintura = area_id(db, "Pintura")
    emp1 = crear_empleado(client, cleaner, nombre=_uniq("c2a_emp1"),
                          cargo_id=cargo_id(db, "EBANISTA"))
    emp2 = crear_empleado(client, cleaner, nombre=_uniq("c2a_emp2"),
                          cargo_id=cargo_id(db, "EBANISTA"))
    for detalle_id in _detalle_ids(pedido):
        _producir_mueble(client, cleaner, db, detalle_id, madera["id"],
                         ebanisteria, pintura, emp1["id"], emp2["id"], 0.05)

    # Auto-TERMINADO: todas las líneas del pedido son FABRICADO y tienen su
    # orden FINALIZADA → el pedido pasa a TERMINADO y se crea el envío.
    rp = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert rp.status_code == 200
    assert rp.json()["estado"] == "TERMINADO", f"estado={rp.json()['estado']}"
    envio = envio_de_pedido(db, pedido["id"])
    assert envio is not None, "La vía automática debe crear el envío"
    assert envio["estado"] == "PREPARADO"

    # 4. Pagos restantes en varias monedas hasta el 100%.
    #    120000 COP ya pagados. Faltan 280000: 50 USD (ZELLE @3900)=195000,
    #    5000 VES (BANCARIBE @10)=50000, 35000 COP.
    caja_antes = {
        "EFECTIVO_COP": saldo_cuenta(client, "EFECTIVO_COP", 1),
        "ZELLE": saldo_cuenta(client, "ZELLE", 2),
        "BANCARIBE": saldo_cuenta(client, "BANCARIBE", 3),
    }
    for moneda_id, monto, metodo, tasa in (
        (2, 50.0, "ZELLE", 3900.0),
        (3, 5000.0, "BANCARIBE", 10.0),
        (1, 35000.0, "EFECTIVO_COP", None),
    ):
        rpago, _ = pagar_venta(client, cleaner, venta["id"], moneda_id, monto,
                               metodo, tasa_cambio=tasa)
        assert rpago.status_code in (200, 201), f"pago {metodo} → {rpago.status_code}: {rpago.text}"
    venta_pagada = venta_actualizada(client, venta["id"])
    assert venta_pagada["estado"] == "PAGADA", f"estado={venta_pagada['estado']}"
    assert venta_pagada["saldo_pendiente"] == pytest.approx(0.0, abs=0.01)

    # 5. Factura al 100% (permitir=False) → 201 EMITIDA con impuestos correctos.
    det_ids = _detalle_ids(pedido)
    rf, factura = emitir_factura(
        client, cleaner, db, pedido["id"],
        [{"detalle_pedido_id": det_ids[0], "precio_usd": 50.0},
         {"detalle_pedido_id": det_ids[1], "precio_usd": 50.0}],
        tasa_usd_ves=50.0, permitir_saldo_pendiente=False)
    assert rf.status_code == 201, f"factura al 100% → {rf.status_code}: {rf.text}"
    assert factura["estado"] == "EMITIDA"
    assert factura["total_usd"] == pytest.approx(100.0)
    assert factura["base_imponible_bs"] == pytest.approx(5000.0)
    assert factura["iva_bs"] == pytest.approx(800.0)
    assert factura["igtf_bs"] == pytest.approx(174.0)
    assert factura["total_bs"] == pytest.approx(5974.0)

    # Caja: cuenta y moneda por pago (adelanto, USD, VES, COP).
    movs = movimientos_caja_de_pedido(db, pedido["id"])
    esperado = [
        ("EFECTIVO_COP", 1, 120000.0),  # adelanto
        ("ZELLE", 2, 50.0),             # USD
        ("BANCARIBE", 3, 5000.0),       # VES
        ("EFECTIVO_COP", 1, 35000.0),   # cierre
    ]
    assert len(movs) == len(esperado), f"movs={movs}"
    for (cuenta, moneda_id, monto), m in zip(esperado, movs):
        assert m["cuenta"] == cuenta, m
        assert m["moneda_id"] == moneda_id, m
        assert m["monto"] == pytest.approx(monto), m
        assert m["tipo"] == "ENTRADA", m
    # Saldos de cuenta: cada pago abonó su moneda en su cuenta (delta).
    assert _delta_saldo(client, "EFECTIVO_COP", 1, caja_antes["EFECTIVO_COP"]) == pytest.approx(35000.0)
    assert _delta_saldo(client, "ZELLE", 2, caja_antes["ZELLE"]) == pytest.approx(50.0)
    assert _delta_saldo(client, "BANCARIBE", 3, caja_antes["BANCARIBE"]) == pytest.approx(5000.0)

    print(f"\n  [Caso2A] pedido #{pedido['id']} TERMINADO + envío #{envio['id']} "
          f"· venta #{venta['id']} PAGADA (4 pagos) · factura #{factura['id']} "
          f"total_bs={factura['total_bs']}")


# ---------------------------------------------------------------------------
# TEST B — 2 reventas sin abono → stock al instante → rupturas → 100% → sin envío
# ---------------------------------------------------------------------------
def test_caso2b_dos_reventas_sin_abono_factura_con_saldo(client, cleaner, db):
    # 1. Cliente + 2 productos REVENTA con stock (ENTRADA 5 uds, costo 40000).
    cliente = crear_cliente(client, cleaner, nombre=_uniq("c2b_cli"))
    rev1 = crear_producto_reventa(client, cleaner, nombre=_uniq("c2b_rev1"), costo_base=40000.0)
    rev2 = crear_producto_reventa(client, cleaner, nombre=_uniq("c2b_rev2"), costo_base=40000.0)
    for p in (rev1, rev2):
        crear_stock_producto(client, cleaner, db, p["id"], cantidad=5, costo_unitario=40000.0)
    db.expire_all()
    assert stock_producto(db, rev1["id"]) == pytest.approx(5.0)
    assert stock_producto(db, rev2["id"]) == pytest.approx(5.0)

    # 2. Cotización COP con 2 detalles REVENTA → convertir SIN abono.
    precio1, precio2 = 250000.0, 200000.0
    total = precio1 + precio2  # 450000 COP
    detalles_cot = [
        {"producto_id": rev1["id"], "tipo_item": "REVENTA", "cantidad": 1, "precio": precio1},
        {"producto_id": rev2["id"], "tipo_item": "REVENTA", "cantidad": 1, "precio": precio2},
    ]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], detalles_cot,
                                        moneda_id=1, tasa_cambio=1.0)
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], detalles_cot)
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    # El teardown debe borrar también la SALIDA generada por la venta.
    for p in (rev1, rev2):
        _registrar_inventario_producto(db, cleaner, p["id"])
    venta = _venta_detalle(client, db, pedido["id"])
    assert venta["estado"] == "PENDIENTE"
    assert venta["total"] == pytest.approx(total)
    assert venta["total_pagado"] == 0.0

    # Stock de reventa descontado AL INSTANTE en la conversión: 5 - 1 = 4 c/u.
    db.expire_all()
    assert stock_producto(db, rev1["id"]) == pytest.approx(4.0), "reventa 1 sin descuento inmediato"
    assert stock_producto(db, rev2["id"]) == pytest.approx(4.0), "reventa 2 sin descuento inmediato"

    det_ids = _detalle_ids(pedido)
    lineas = [{"detalle_pedido_id": det_ids[0], "precio_usd": 100.0},
              {"detalle_pedido_id": det_ids[1], "precio_usd": 50.0}]

    # 3a. Factura con saldo pendiente y permitir=False → 400 con mensaje "100%".
    rf, _ = emitir_factura(client, cleaner, db, pedido["id"], lineas,
                           tasa_usd_ves=50.0, permitir_saldo_pendiente=False)
    assert rf.status_code == 400, f"factura con saldo sin permiso → {rf.status_code}: {rf.text}"
    assert "100%" in str(rf.text), f"El error debe mencionar el 100%, fue: {rf.text}"

    # 3b. Emitir con permitir=True (admin) → 201 EMITIDA ANTES del pago completo.
    rf, factura = emitir_factura(client, cleaner, db, pedido["id"], lineas,
                                 tasa_usd_ves=50.0, permitir_saldo_pendiente=True)
    assert rf.status_code == 201, f"factura con saldo autorizada → {rf.status_code}: {rf.text}"
    assert factura["estado"] == "EMITIDA"
    assert "saldo pendiente" in (factura.get("observaciones") or "").lower()
    assert factura["total_usd"] == pytest.approx(150.0)
    assert factura["base_imponible_bs"] == pytest.approx(7500.0)
    assert factura["iva_bs"] == pytest.approx(1200.0)
    assert factura["igtf_bs"] == pytest.approx(261.0)
    assert factura["total_bs"] == pytest.approx(8961.0)

    # 3c. Pago que excede el saldo → 400.
    rpago, _ = pagar_venta(client, cleaner, venta["id"], 1, 500000.0, "EFECTIVO_COP")
    assert rpago.status_code == 400, f"sobrepago → {rpago.status_code}: {rpago.text}"
    assert "excede" in rpago.text.lower()

    # 3d. Pago con metodo_pago de moneda incorrecta (ZELLE con moneda COP) → 400.
    rpago, _ = pagar_venta(client, cleaner, venta["id"], 1, 100000.0, "ZELLE")
    assert rpago.status_code == 400, f"ZELLE+COP → {rpago.status_code}: {rpago.text}"

    # 4. Pagos en varias monedas hasta el 100% (el primero puede ser USD).
    #    50 USD (ZELLE @3900)=195000, 10000 VES (BANCARIBE @10)=100000, 155000 COP.
    caja_antes = {
        "ZELLE": saldo_cuenta(client, "ZELLE", 2),
        "BANCARIBE": saldo_cuenta(client, "BANCARIBE", 3),
        "EFECTIVO_COP": saldo_cuenta(client, "EFECTIVO_COP", 1),
    }
    for moneda_id, monto, metodo, tasa in (
        (2, 50.0, "ZELLE", 3900.0),
        (3, 10000.0, "BANCARIBE", 10.0),
        (1, 155000.0, "EFECTIVO_COP", None),
    ):
        rpago, _ = pagar_venta(client, cleaner, venta["id"], moneda_id, monto,
                               metodo, tasa_cambio=tasa)
        assert rpago.status_code in (200, 201), f"pago {metodo} → {rpago.status_code}: {rpago.text}"
    venta_pagada = venta_actualizada(client, venta["id"])
    assert venta_pagada["estado"] == "PAGADA", f"estado={venta_pagada['estado']}"
    assert venta_pagada["saldo_pendiente"] == pytest.approx(0.0, abs=0.01)

    # 5. REVENTA no produce: NO debe haber orden de producción ni envío.
    n_ordenes = db.execute(text(
        """SELECT COUNT(*) FROM orden_produccion op
           JOIN detalle_pedido dp ON dp.id = op.detalle_pedido_id
           WHERE dp.pedido_id = :p"""
    ), {"p": pedido["id"]}).scalar()
    assert n_ordenes == 0, f"REVENTA generó {n_ordenes} órdenes de producción"
    n_envios = db.execute(text(
        "SELECT COUNT(*) FROM envio WHERE pedido_id = :p"
    ), {"p": pedido["id"]}).scalar()
    assert n_envios == 0, f"REVENTA generó envío: {n_envios}"
    assert envio_de_pedido(db, pedido["id"]) is None

    # 6. Caja: cuenta y moneda por pago (USD, VES, COP).
    movs = movimientos_caja_de_pedido(db, pedido["id"])
    esperado = [
        ("ZELLE", 2, 50.0),
        ("BANCARIBE", 3, 10000.0),
        ("EFECTIVO_COP", 1, 155000.0),
    ]
    assert len(movs) == len(esperado), f"movs={movs}"
    for (cuenta, moneda_id, monto), m in zip(esperado, movs):
        assert m["cuenta"] == cuenta, m
        assert m["moneda_id"] == moneda_id, m
        assert m["monto"] == pytest.approx(monto), m
        assert m["tipo"] == "ENTRADA", m
    assert _delta_saldo(client, "ZELLE", 2, caja_antes["ZELLE"]) == pytest.approx(50.0)
    assert _delta_saldo(client, "BANCARIBE", 3, caja_antes["BANCARIBE"]) == pytest.approx(10000.0)
    assert _delta_saldo(client, "EFECTIVO_COP", 1, caja_antes["EFECTIVO_COP"]) == pytest.approx(155000.0)

    print(f"\n  [Caso2B] pedido #{pedido['id']} (2 reventas) · venta #{venta['id']} PAGADA "
          f"(3 pagos) · factura con saldo #{factura['id']} total_bs={factura['total_bs']} "
          f"· 0 órdenes / 0 envíos · stock reventa 5→4")