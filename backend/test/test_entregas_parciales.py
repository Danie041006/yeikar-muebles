# -*- coding: utf-8 -*-
"""test_entregas_parciales.py — El cliente se lleva lo que ya está terminado.

Caso real: un pedido de 5 muebles se entrega en tandas. El sistema no puede
exigir que TODO el pedido esté TERMINADO para registrar una entrega: cada
renglón/pieza se despacha cuando su orden de producción está FINALIZADA.

Cubre:
  1. Pendientes: una pieza lista y otra en producción.
  2. Entrega parcial mientras el pedido sigue en PRODUCCION.
  3. No entregar una pieza cuya orden no está FINALIZADA.
  4. No exceder la cantidad pendiente.
  5. Reserva: un despacho PREPARADO bloquea el mismo ítem.
  6. FALLIDO libera la reserva y permite reprogramar.
  7. Al terminar la última orden, el pedido pasa a TERMINADO y se crea el
     despacho de lo que falta.
  8. La última entrega cierra el pedido en ENTREGADO.
  9. No se puede cancelar un pedido con entregas.
 10. No se puede forzar ENTREGADO con ítems pendientes.

Ejecutar:
  cd backend && source venv/bin/activate && pytest test/test_entregas_parciales.py -v
"""
import pytest
from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente
from helpers_e2e import (
    area_id,
    avanzar_etapa,
    crear_cotizacion_multidetalle,
    crear_empleado,
    crear_etapa,
    convertir_cotizacion,
    finalizar_orden,
)


def _detalles_dos_muebles():
    return [
        {
            "producto_id": None,
            "material_id": None,
            "tipo_item": "FABRICADO",
            "cantidad": 1,
            "precio": 1000,
            "descripcion_especifica": "MUEBLE TEST ENTREGA A",
        },
        {
            "producto_id": None,
            "material_id": None,
            "tipo_item": "FABRICADO",
            "cantidad": 1,
            "precio": 2000,
            "descripcion_especifica": "MUEBLE TEST ENTREGA B",
        },
    ]


def _crear_pedido_dos_lineas(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    detalles = _detalles_dos_muebles()
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], detalles)
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], detalles)
    assert r.status_code == 201, r.text
    assert len(pedido["detalles"]) == 2

    ordenes = []
    for detalle in pedido["detalles"]:
        filas = db.execute(text(
            "SELECT id, estado FROM orden_produccion WHERE detalle_pedido_id = :d ORDER BY id"
        ), {"d": detalle["id"]}).fetchall()
        assert len(filas) == 1, filas
        orden_id = filas[0][0]
        cleaner.registrar("orden_produccion", orden_id)
        ordenes.append(orden_id)
    return pedido, ordenes


def _finalizar_completa(client, cleaner, db, orden_id):
    empleado = crear_empleado(client, cleaner)
    etapa = crear_etapa(
        client, cleaner, orden_id, area_id(db, "EBANISTERIA"), empleado["id"],
        estado="ASIGNADA",
    )
    avanzar_etapa(client, etapa["id"], "EN_PROCESO")
    avanzar_etapa(client, etapa["id"], "COMPLETADA")
    finalizar_orden(client, orden_id)


def _envios(db, pedido_id):
    return db.execute(text(
        "SELECT id, estado FROM envio WHERE pedido_id = :p ORDER BY id"
    ), {"p": pedido_id}).fetchall()


def _pendientes(client, pedido_id):
    r = client.get(f"/api/v1/envio/pendientes/{pedido_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _crear_envio(client, pedido_id, estado, items):
    return client.post("/api/v1/envio/", json={
        "pedido_id": pedido_id,
        "estado": estado,
        "detalles": items,
    }, headers=ADMIN_HEADERS)


def test_entrega_parcial_de_cantidad_en_un_renglon(client, db, cleaner):
    """Un renglón con cantidad 2 se entrega en dos tandas."""
    cliente = crear_cliente(client, cleaner)
    detalles = [
        {
            "producto_id": None,
            "material_id": None,
            "tipo_item": "FABRICADO",
            "cantidad": 2,
            "precio": 1000,
            "descripcion_especifica": "MUEBLE TEST CANTIDAD 2",
        },
        {
            "producto_id": None,
            "material_id": None,
            "tipo_item": "FABRICADO",
            "cantidad": 1,
            "precio": 2000,
            "descripcion_especifica": "MUEBLE TEST CANTIDAD 1",
        },
    ]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], detalles)
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], detalles)
    assert r.status_code == 201, r.text
    det_a, det_b = pedido["detalles"]

    ordenes = []
    for det in (det_a, det_b):
        fila = db.execute(text(
            "SELECT id FROM orden_produccion WHERE detalle_pedido_id = :d ORDER BY id"
        ), {"d": det["id"]}).fetchone()
        assert fila, det
        cleaner.registrar("orden_produccion", fila[0])
        ordenes.append(fila[0])
    orden_a, orden_b = ordenes

    _finalizar_completa(client, cleaner, db, orden_a)
    pend = _pendientes(client, pedido["id"])
    item_a = next(i for i in pend["items"] if i["orden_produccion_id"] == orden_a)
    assert item_a["cantidad_total"] == 2.0
    assert item_a["cantidad_lista"] == 2.0

    # Primera unidad del renglón de cantidad 2.
    r = _crear_envio(client, pedido["id"], "ENTREGADO", [{
        "detalle_pedido_id": det_a["id"],
        "orden_produccion_id": orden_a,
        "cantidad": 1,
    }])
    assert r.status_code == 201, r.text
    cleaner.registrar("envio", r.json()["id"])

    pend = _pendientes(client, pedido["id"])
    item_a = next(i for i in pend["items"] if i["orden_produccion_id"] == orden_a)
    assert item_a["cantidad_entregada"] == 1.0
    assert item_a["cantidad_pendiente"] == 1.0
    assert item_a["cantidad_lista"] == 1.0

    # Segunda unidad del mismo renglón.
    r = _crear_envio(client, pedido["id"], "ENTREGADO", [{
        "detalle_pedido_id": det_a["id"],
        "orden_produccion_id": orden_a,
        "cantidad": 1,
    }])
    assert r.status_code == 201, r.text
    cleaner.registrar("envio", r.json()["id"])

    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    resumen = r.json()["entrega_resumen"]
    assert resumen["total"] == 3.0, resumen
    assert resumen["entregado"] == 2.0, resumen
    assert resumen["pendiente"] == 1.0, resumen

    # Al terminar el otro renglón, el cierre es automático.
    _finalizar_completa(client, cleaner, db, orden_b)
    envios = _envios(db, pedido["id"])
    envio_auto = envios[-1][0]
    cleaner.registrar("envio", envio_auto)
    assert envios[-1][1] == "PREPARADO", envios
    assert client.put(
        f"/api/v1/envio/{envio_auto}/estado",
        params={"estado": "EN_TRANSITO"}, headers=ADMIN_HEADERS,
    ).status_code == 200
    assert client.put(
        f"/api/v1/envio/{envio_auto}/estado",
        params={"estado": "ENTREGADO"}, headers=ADMIN_HEADERS,
    ).status_code == 200
    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ENTREGADO", r.json()["estado"]


def test_auto_envio_no_se_pierde_con_un_despacho_activo(client, db, cleaner):
    """Si ya hay un despacho preparado, al terminar el resto se crea otro."""
    pedido, ordenes = _crear_pedido_dos_lineas(client, cleaner, db)
    detalle_a, detalle_b = pedido["detalles"]
    orden_a, orden_b = ordenes

    _finalizar_completa(client, cleaner, db, orden_a)
    r = _crear_envio(client, pedido["id"], "PREPARADO", [{
        "detalle_pedido_id": detalle_a["id"],
        "orden_produccion_id": orden_a,
        "cantidad": 1,
    }])
    assert r.status_code == 201, r.text
    envio_a = r.json()["id"]
    cleaner.registrar("envio", envio_a)

    _finalizar_completa(client, cleaner, db, orden_b)
    envios = _envios(db, pedido["id"])
    assert len(envios) == 2, envios
    assert envios[0][1] == "PREPARADO" and envios[1][1] == "PREPARADO", envios
    envio_b = envios[1][0]
    cleaner.registrar("envio", envio_b)

    r = client.get(f"/api/v1/envio/{envio_b}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert [d["orden_produccion_id"] for d in r.json()["detalles"]] == [orden_b]


def test_entrega_por_pieza_de_un_juego(client, db, cleaner):
    """Un renglón-juego se entrega pieza por pieza (no espera el juego completo)."""
    cliente = crear_cliente(client, cleaner)
    piezas = [
        {"nombre": "SOFA TEST", "cantidad": 1},
        {"nombre": "SILLA TEST", "cantidad": 2},
    ]
    detalle = {
        "producto_id": None,
        "material_id": None,
        "tipo_item": "FABRICADO",
        "cantidad": 1,
        "precio": 5000,
        "descripcion_especifica": "JUEGO TEST ENTREGA POR PIEZA",
        "piezas": piezas,
    }
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle])
    # La conversión copia las piezas de la cotización.
    detalle_conversion = {k: v for k, v in detalle.items() if k != "piezas"}
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [detalle_conversion])
    assert r.status_code == 201, r.text
    det = pedido["detalles"][0]
    filas = db.execute(text(
        "SELECT id, pieza_nombre, cantidad FROM orden_produccion"
        " WHERE detalle_pedido_id = :d ORDER BY id"
    ), {"d": det["id"]}).fetchall()
    assert len(filas) == 2, filas
    por_nombre = {f[1]: f for f in filas}
    assert float(por_nombre["SOFA TEST"][2]) == 1.0
    assert float(por_nombre["SILLA TEST"][2]) == 2.0
    for fila in filas:
        cleaner.registrar("orden_produccion", fila[0])

    orden_sofa = por_nombre["SOFA TEST"][0]
    _finalizar_completa(client, cleaner, db, orden_sofa)

    pend = _pendientes(client, pedido["id"])
    item_sofa = next(i for i in pend["items"] if i["pieza_nombre"] == "SOFA TEST")
    assert item_sofa["cantidad_lista"] == 1.0
    assert "SOFA TEST" in item_sofa["descripcion"]
    item_silla = next(i for i in pend["items"] if i["pieza_nombre"] == "SILLA TEST")
    assert item_silla["cantidad_lista"] == 0.0

    r = _crear_envio(client, pedido["id"], "ENTREGADO", [{
        "detalle_pedido_id": det["id"],
        "orden_produccion_id": orden_sofa,
        "cantidad": 1,
    }])
    assert r.status_code == 201, r.text
    cleaner.registrar("envio", r.json()["id"])
    assert "SOFA TEST" in r.json()["detalles"][0]["descripcion"]

    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    resumen = r.json()["entrega_resumen"]
    # La unidad de entrega son las PIEZAS del juego: 1 sofá + 2 sillas.
    assert resumen["total"] == 3.0, resumen
    assert resumen["entregado"] == 1.0, resumen
    assert resumen["pendiente"] == 2.0, resumen
    assert resumen["estado"] == "PARCIAL", resumen


def test_entrega_parcial_flujo_completo(client, db, cleaner):
    pedido, ordenes = _crear_pedido_dos_lineas(client, cleaner, db)
    detalle_a, detalle_b = pedido["detalles"]
    orden_a, orden_b = ordenes

    # 1. Al principio no hay nada listo: ambas órdenes PENDIENTE.
    pend = _pendientes(client, pedido["id"])
    assert pend["estado"] == "PRODUCCION"
    assert {i["cantidad_lista"] for i in pend["items"]} == {0.0}

    # 2. Se termina SOLO la primera orden.
    _finalizar_completa(client, cleaner, db, orden_a)
    pend = _pendientes(client, pedido["id"])
    por_orden = {i["orden_produccion_id"]: i for i in pend["items"] if i["orden_produccion_id"]}
    assert por_orden[orden_a]["cantidad_lista"] == 1.0
    assert por_orden[orden_a]["estado_produccion"] == "FINALIZADA"
    assert por_orden[orden_b]["cantidad_lista"] == 0.0
    assert por_orden[orden_b]["estado_produccion"] == "PENDIENTE"

    # 3. No se puede entregar la pieza que sigue en producción.
    r = _crear_envio(client, pedido["id"], "ENTREGADO", [{
        "detalle_pedido_id": detalle_b["id"],
        "orden_produccion_id": orden_b,
        "cantidad": 1,
    }])
    assert r.status_code == 400, r.text
    assert "no está FINALIZADA" in r.text

    # 4. Se entrega la primera pieza, sin esperar la segunda.
    r = _crear_envio(client, pedido["id"], "ENTREGADO", [{
        "detalle_pedido_id": detalle_a["id"],
        "orden_produccion_id": orden_a,
        "cantidad": 1,
    }])
    assert r.status_code == 201, r.text
    assert r.json()["detalles"][0]["cantidad"] == 1.0
    assert r.json()["detalles"][0]["descripcion"]
    cleaner.registrar("envio", r.json()["id"])

    # El pedido sigue en producción, pero ya muestra 1/2 entregado.
    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    resumen = r.json()["entrega_resumen"]
    assert resumen["total"] == 2.0, resumen
    assert resumen["entregado"] == 1.0, resumen
    assert resumen["pendiente"] == 1.0, resumen
    assert resumen["estado"] == "PARCIAL", resumen
    assert r.json()["estado"] == "PRODUCCION"

    # Con una entrega física ya hecha no se puede cancelar el pedido (dejaría
    # mercancía en la calle sin documento).
    r = client.put(
        f"/api/v1/pedido/{pedido['id']}",
        json={"estado": "CANCELADO"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, r.text
    assert "entregas" in r.text

    # No se puede forzar el cierre total todavía: el estado aún es PRODUCCION
    # y la máquina de estados lo rechaza (ni siquiera llega a la validación de
    # entregas). La validación específica se prueba abajo, ya en TERMINADO.

    # 5. Exceder la cantidad disponible también se rechaza.
    r = _crear_envio(client, pedido["id"], "PREPARADO", [{
        "detalle_pedido_id": detalle_a["id"],
        "orden_produccion_id": orden_a,
        "cantidad": 2,
    }])
    assert r.status_code == 400, r.text

    # 6. Se termina la segunda orden: el pedido pasa a TERMINADO y se crea
    # automáticamente el despacho de lo que falta (solo la pieza B).
    _finalizar_completa(client, cleaner, db, orden_b)
    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "TERMINADO", r.json()["estado"]

    # Ya en TERMINADO, forzar ENTREGADO con una pieza pendiente se rechaza.
    r = client.put(
        f"/api/v1/pedido/{pedido['id']}",
        json={"estado": "ENTREGADO"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, r.text
    assert "sin entregar" in r.text

    envios = _envios(db, pedido["id"])
    assert [e[1] for e in envios] == ["ENTREGADO", "PREPARADO"], envios
    envio_auto = envios[1][0]
    cleaner.registrar("envio", envio_auto)

    # La ficha histórica muestra el último despacho (y la auditoría enlaza todos).
    r = client.get(f"/api/v1/historial/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["envio"]["id"] == envio_auto

    # Al abrir un despacho concreto, la ficha muestra ESE, no el último.
    envio_primero = envios[0][0]
    r = client.get(f"/api/v1/historial/envio/{envio_primero}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["envio"]["id"] == envio_primero

    # La guía automática solo lleva la pieza pendiente.
    r = client.get(f"/api/v1/envio/{envio_auto}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert [d["orden_produccion_id"] for d in r.json()["detalles"]] == [orden_b]

    # 7. Se entrega el resto: el pedido cierra en ENTREGADO.
    assert client.put(
        f"/api/v1/envio/{envio_auto}/estado",
        params={"estado": "EN_TRANSITO"}, headers=ADMIN_HEADERS,
    ).status_code == 200
    r = client.put(
        f"/api/v1/envio/{envio_auto}/estado",
        params={"estado": "ENTREGADO"}, headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ENTREGADO", r.json()["estado"]
    assert r.json()["entrega_resumen"]["estado"] == "COMPLETO"
    assert r.json()["entrega_resumen"]["pendiente"] == 0.0

    # 8. Ya entregado no se puede cancelar (estado terminal).
    r = client.put(
        f"/api/v1/pedido/{pedido['id']}",
        json={"estado": "CANCELADO"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, r.text
    assert "terminal" in r.text

    # 9. El listado de despachos del pedido trae los dos, con su detalle.
    r = client.get(
        "/api/v1/envio/", params={"pedido_id": pedido["id"]}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2
    assert all(envio["detalles"] for envio in r.json())


def test_reserva_y_fallido_liberan_el_item(client, db, cleaner):
    pedido, ordenes = _crear_pedido_dos_lineas(client, cleaner, db)
    detalle_a = pedido["detalles"][0]
    orden_a = ordenes[0]
    _finalizar_completa(client, cleaner, db, orden_a)

    # Un despacho PREPARADO reserva la pieza: otro no puede tomarla.
    r = _crear_envio(client, pedido["id"], "PREPARADO", [{
        "detalle_pedido_id": detalle_a["id"],
        "orden_produccion_id": orden_a,
        "cantidad": 1,
    }])
    assert r.status_code == 201, r.text
    envio_id = r.json()["id"]
    cleaner.registrar("envio", envio_id)

    r = _crear_envio(client, pedido["id"], "PREPARADO", [{
        "detalle_pedido_id": detalle_a["id"],
        "orden_produccion_id": orden_a,
        "cantidad": 1,
    }])
    assert r.status_code == 400, r.text

    # Si el despacho falla, la pieza vuelve a estar disponible.
    assert client.put(
        f"/api/v1/envio/{envio_id}/estado",
        params={"estado": "EN_TRANSITO"}, headers=ADMIN_HEADERS,
    ).status_code == 200
    assert client.put(
        f"/api/v1/envio/{envio_id}/estado",
        params={"estado": "FALLIDO"}, headers=ADMIN_HEADERS,
    ).status_code == 200

    r = _crear_envio(client, pedido["id"], "PREPARADO", [{
        "detalle_pedido_id": detalle_a["id"],
        "orden_produccion_id": orden_a,
        "cantidad": 1,
    }])
    assert r.status_code == 201, r.text
    cleaner.registrar("envio", r.json()["id"])


def test_pedido_sin_produccion_puede_entregarse(client, db, cleaner):
    """Un pedido que no fabrica nada (reventa) se despacha sin orden."""
    from helpers_e2e import crear_producto_reventa, crear_stock_producto

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto_reventa(client, cleaner)
    crear_stock_producto(client, cleaner, db, producto["id"], 2, 50000)
    detalle = {
        "producto_id": producto["id"],
        "material_id": None,
        "tipo_item": "REVENTA",
        "cantidad": 1,
        "precio": 90000,
    }
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [detalle])
    assert r.status_code == 201, r.text
    det = pedido["detalles"][0]

    r = _crear_envio(client, pedido["id"], "ENTREGADO", [{
        "detalle_pedido_id": det["id"],
        "cantidad": 1,
    }])
    assert r.status_code == 201, r.text
    cleaner.registrar("envio", r.json()["id"])
    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ENTREGADO", r.json()["estado"]
    assert r.json()["entrega_resumen"]["estado"] == "COMPLETO"
