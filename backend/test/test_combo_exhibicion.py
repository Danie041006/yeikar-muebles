# -*- coding: utf-8 -*-
"""
test_combo_exhibicion.py — Composición comercial con piezas de exhibición.

Caso real: la clienta quiere la mesa de un comedor del showroom y las sillas de
OTRO comedor. Se cotiza UN renglón con el nombre del combo, cada pieza lleva su
producto y su precio, y al convertir:

  - el conjunto se DESPIECE (sale del showroom),
  - las piezas llevadas se congelan con su costo real,
  - los sobrantes vuelven como piezas sueltas vendibles,
  - las piezas de exhibición sin retrabajo no generan orden de producción y se
    pueden entregar de inmediato,
  - la factura NO vuelve a descontar el stock,
  - la rentabilidad suma el costo real de las piezas.

Ejecutar: pytest test/test_combo_exhibicion.py -v
"""
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text

from conftest import ADMIN_HEADERS
from helpers_e2e import (
    area_id,
    avanzar_etapa,
    cargo_id,
    convertir_cotizacion,
    crear_cotizacion_multidetalle,
    crear_empleado,
    crear_etapa,
    envio_de_pedido,
    finalizar_orden,
    registrar_mano_obra,
)


def _uniq(prefijo: str) -> str:
    return f"test_{prefijo}_{uuid.uuid4().hex[:8]}"


def _producto(client, cleaner, nombre=None, costo=None, precio=None, **extra) -> dict:
    payload = {
        "nombre": nombre or _uniq("pieza"),
        "tipo_producto_id": 2,
        "moneda_id": 1,
        "activo": True,
        "precio_costo_base": costo,
        "precio_venta_base": precio,
    }
    payload.update(extra)
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear producto → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("producto", body["id"])
    return body


def _componer(client, conjunto_id, piezas) -> dict:
    r = client.put(
        f"/api/v1/producto/{conjunto_id}/piezas",
        json={"piezas": piezas},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"componer → {r.status_code}: {r.text}"
    return r.json()


def _ubicacion_exhibicion(db) -> int:
    row = db.execute(text("SELECT id FROM ubicacion WHERE nombre = 'EXHIBICIÓN'")).fetchone()
    assert row is not None, "falta la ubicación EXHIBICIÓN en la BD"
    return int(row[0])


def _entrar_showroom(client, cleaner, db, producto_id, cantidad, costo) -> None:
    ubi = _ubicacion_exhibicion(db)
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": producto_id,
        "ubicacion_id": ubi,
        "tipo": "ENTRADA",
        "cantidad": cantidad,
        "costo_unitario": costo,
        "observaciones": "Pieza de exhibición ya fabricada (test combo)",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"stock showroom → {r.status_code}: {r.text}"
    cleaner.registrar("movimiento_producto_inventario", r.json()["id"])
    for (mid,) in db.execute(text(
        "SELECT id FROM movimiento_producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchall():
        cleaner.registrar("movimiento_producto_inventario", mid)
    for (iid,) in db.execute(text(
        "SELECT id FROM producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchall():
        cleaner.registrar("producto_inventario", iid)


def _stock_y_costo(db, producto_id):
    row = db.execute(text(
        "SELECT COALESCE(SUM(cantidad), 0), MAX(costo_promedio) "
        "FROM producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchone()
    return float(row[0]), (float(row[1]) if row[1] is not None else None)


def _detalle_combo(piezas, cantidad=1, precio=0.0):
    return {
        "producto_id": None,
        "material_id": None,
        "tipo_item": "FABRICADO",
        "cantidad": cantidad,
        "precio": precio,
        "ancho": 1.6,
        "largo": 1.9,
        "descripcion_especifica": "COMBO DE EXHIBICIÓN (test)",
        "piezas": piezas,
    }


def _para_conversion(cot_detalle: dict) -> dict:
    """Copia del renglón para convertir, con el precio ya calculado por el backend."""
    return {
        "producto_id": None,
        "material_id": None,
        "tipo_item": "FABRICADO",
        "cantidad": cot_detalle["cantidad"],
        "precio": float(cot_detalle["precio"]),
        "ancho": 1.6,
        "largo": 1.9,
        "descripcion_especifica": cot_detalle["descripcion_especifica"],
    }


def test_combo_exhibicion_despieza_sobrantes_entrega_y_rentabilidad(client, db, cleaner):
    mesa = _producto(client, cleaner, nombre=_uniq("mesa"), costo=700.0, precio=900.0)
    silla = _producto(client, cleaner, nombre=_uniq("silla"), costo=75.0, precio=100.0)
    conjunto = _producto(client, cleaner, nombre=_uniq("comedor"), costo=1000.0, precio=1300.0)
    _componer(client, conjunto["id"], [
        {"pieza_producto_id": mesa["id"], "cantidad": 1, "orden": 0},
        {"pieza_producto_id": silla["id"], "cantidad": 4, "orden": 1},
    ])
    _entrar_showroom(client, cleaner, db, conjunto["id"], 1, 1000.0)

    cliente = client.post(
        "/api/v1/cliente/",
        json={"nombre": _uniq("cliente"), "telefono": "555-0000"},
        headers=ADMIN_HEADERS,
    ).json()
    cleaner.registrar("cliente", cliente["id"])

    # El renglón se envía con precio 0: el backend DEBE recalcularlo desde las
    # piezas (900 + 2×100 = 1.100) y cuadrar el total de la cotización.
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        _detalle_combo([
            {
                "nombre": "Mesa del comedor",
                "cantidad": 1,
                "producto_id": mesa["id"],
                "precio": 900.0,
                "origen": "EXHIBICION",
                "conjunto_origen_id": conjunto["id"],
            },
            {
                "nombre": "Sillas del comedor",
                "cantidad": 2,
                "producto_id": silla["id"],
                "precio": 100.0,
                "origen": "EXHIBICION",
                "conjunto_origen_id": conjunto["id"],
            },
        ])
    ])
    det_cot = cot["detalles"][0]
    assert abs(float(det_cot["precio"]) - 1100.0) < 0.01
    assert abs(float(cot["total_estimado"]) - 1100.0) < 0.01
    assert abs(float(det_cot["costo_total"]) - 850.0) < 0.01
    # El listado también expone la composición (sin la foto) sin romper.
    listado = client.get(
        "/api/v1/cotizacion/", params={"limite": 1000}, headers=ADMIN_HEADERS
    )
    assert listado.status_code == 200, listado.text
    fila_lista = next(q for q in listado.json() if q["id"] == cot["id"])
    pieza_lista = fila_lista["detalles"][0]["piezas"][0]
    assert pieza_lista["producto_id"] == mesa["id"]
    assert pieza_lista["origen"] == "EXHIBICION"
    assert pieza_lista["conjunto_origen_id"] == conjunto["id"]

    r, pedido = convertir_cotizacion(
        client, cleaner, cot["id"], [_para_conversion(det_cot)]
    )
    assert r.status_code == 201, r.text
    # Todo es exhibición ya fabricada: no hay nada que producir.
    assert pedido["estado"] == "APROBADO", pedido["estado"]
    detalle = pedido["detalles"][0]
    assert [p["nombre"] for p in detalle["piezas"]] == [
        "Mesa del comedor", "Sillas del comedor",
    ]

    # El conjunto salió del showroom y las 2 sillas sobrantes volvieron como
    # piezas sueltas con su parte prorrateada del valor (75 c/u).
    stock_conjunto, _ = _stock_y_costo(db, conjunto["id"])
    stock_sillas, costo_silla = _stock_y_costo(db, silla["id"])
    assert stock_conjunto == 0.0
    assert abs(stock_sillas - 2.0) < 0.01
    assert abs((costo_silla or 0) - 75.0) < 0.01
    # El sobrante queda vendible como pieza de exhibición (stock) sin tocar
    # su costo ni su precio de catálogo.
    ficha_silla = client.get(
        f"/api/v1/producto/{silla['id']}", headers=ADMIN_HEADERS
    ).json()
    assert ficha_silla["es_exhibicion"] is True
    assert abs(float(ficha_silla["precio_venta_base"]) - 100.0) < 0.01
    assert abs(float(ficha_silla["precio_costo_base"]) - 75.0) < 0.01

    # Costos reales congelados en las piezas del pedido.
    piezas = db.execute(text(
        "SELECT nombre, producto_id, origen, conjunto_origen_id, costo_unitario "
        "FROM detalle_pedido_pieza WHERE detalle_pedido_id = :d ORDER BY orden"
    ), {"d": detalle["id"]}).fetchall()
    por_nombre = {fila[0]: fila for fila in piezas}
    assert abs(float(por_nombre["Mesa del comedor"][4]) - 700.0) < 0.01
    assert abs(float(por_nombre["Sillas del comedor"][4]) - 75.0) < 0.01

    # El listado de pedidos también serializa la composición y el costo real.
    lista_pedidos = client.get(
        "/api/v1/pedido/", params={"limite": 1000}, headers=ADMIN_HEADERS
    )
    assert lista_pedidos.status_code == 200, lista_pedidos.text
    fila_pedido = next(p for p in lista_pedidos.json() if p["id"] == pedido["id"])
    pieza_lista = fila_pedido["detalles"][0]["piezas"][0]
    assert pieza_lista["producto_id"] == mesa["id"]
    assert pieza_lista["origen"] == "EXHIBICION"
    assert abs(float(pieza_lista["costo_unitario"]) - 700.0) < 0.01

    # Ninguna pieza de exhibición sin retrabajo genera orden.
    n_ordenes = db.execute(text(
        "SELECT COUNT(*) FROM orden_produccion WHERE detalle_pedido_id = :d"
    ), {"d": detalle["id"]}).scalar()
    assert n_ordenes == 0

    # La factura ya se creó: no debe haber descontado otra vez el showroom.
    assert stock_conjunto == 0.0
    assert abs(stock_sillas - 2.0) < 0.01

    # Rentabilidad: 700 + 2×75 = 850 de costo real; 1.100 cobrado.
    rent = client.get(
        f"/api/v1/pedido/{pedido['id']}/rentabilidad", headers=ADMIN_HEADERS
    )
    assert rent.status_code == 200, rent.text
    cuerpo = rent.json()
    assert abs(float(cuerpo["costo_real_produccion"]) - 850.0) < 0.01
    assert abs(float(cuerpo["margen_real"]) - 250.0) < 0.01
    assert any(p["pieza_nombre"] == "Mesa del comedor" for p in cuerpo["por_pieza"])

    # Entrega parcial: las dos piezas ya están listas aunque no haya órdenes.
    pend = client.get(
        f"/api/v1/envio/pendientes/{pedido['id']}", headers=ADMIN_HEADERS
    )
    assert pend.status_code == 200, pend.text
    items = pend.json()["items"]
    assert len(items) == 2
    assert all(float(i["cantidad_lista"]) == float(i["cantidad_total"]) for i in items)
    assert all(i["detalle_pieza_id"] is not None for i in items)
    assert all(i["orden_produccion_id"] is None for i in items)
    # La clave (renglón, pieza) no se repite: antes dos piezas sin orden
    # colapsaban en el mismo ítem.
    assert len({(i["detalle_pedido_id"], i["detalle_pieza_id"]) for i in items}) == 2

    envio = client.post("/api/v1/envio/", json={
        "pedido_id": pedido["id"],
        "estado": "ENTREGADO",
        "detalles": [
            {
                "detalle_pedido_id": i["detalle_pedido_id"],
                "detalle_pieza_id": i["detalle_pieza_id"],
                "cantidad": i["cantidad_total"],
            }
            for i in items
        ],
    }, headers=ADMIN_HEADERS)
    assert envio.status_code in (200, 201), envio.text
    cleaner.registrar("envio", envio.json()["id"])
    pedido_final = client.get(
        f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS
    ).json()
    assert pedido_final["estado"] == "ENTREGADO"


def test_combo_mixto_fabricado_mas_exhibicion_produce_solo_lo_nuevo(client, db, cleaner):
    """Mesa del showroom + sillas NUEVAS: solo las sillas entran al taller."""
    mesa = _producto(client, cleaner, nombre=_uniq("mesa"), costo=700.0, precio=900.0)
    silla_vieja = _producto(client, cleaner, nombre=_uniq("silla_vieja"), costo=75.0, precio=100.0)
    silla_nueva = _producto(client, cleaner, nombre=_uniq("silla_nueva"), costo=80.0, precio=120.0)
    conjunto = _producto(client, cleaner, nombre=_uniq("comedor"), costo=1000.0, precio=1300.0)
    _componer(client, conjunto["id"], [
        {"pieza_producto_id": mesa["id"], "cantidad": 1, "orden": 0},
        {"pieza_producto_id": silla_vieja["id"], "cantidad": 4, "orden": 1},
    ])
    _entrar_showroom(client, cleaner, db, conjunto["id"], 1, 1000.0)

    cliente = client.post(
        "/api/v1/cliente/",
        json={"nombre": _uniq("cliente"), "telefono": "555-0000"},
        headers=ADMIN_HEADERS,
    ).json()
    cleaner.registrar("cliente", cliente["id"])

    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        _detalle_combo([
            {
                "nombre": "Mesa del comedor",
                "cantidad": 1,
                "producto_id": mesa["id"],
                "precio": 900.0,
                "origen": "EXHIBICION",
                "conjunto_origen_id": conjunto["id"],
            },
            {
                "nombre": "Sillas nuevas",
                "cantidad": 4,
                "producto_id": silla_nueva["id"],
                "precio": 120.0,
                "origen": "FABRICADO",
            },
        ])
    ])
    det_cot = cot["detalles"][0]
    assert abs(float(det_cot["precio"]) - 1380.0) < 0.01  # 900 + 4×120

    r, pedido = convertir_cotizacion(
        client, cleaner, cot["id"], [_para_conversion(det_cot)]
    )
    assert r.status_code == 201, r.text
    assert pedido["estado"] == "PRODUCCION", "las sillas nuevas sí se fabrican"
    detalle = pedido["detalles"][0]

    ordenes = db.execute(text(
        "SELECT id, pieza_nombre, tipo, cantidad FROM orden_produccion "
        "WHERE detalle_pedido_id = :d ORDER BY id"
    ), {"d": detalle["id"]}).fetchall()
    assert len(ordenes) == 1, ordenes
    orden = ordenes[0]
    assert orden[1] == "Sillas nuevas"
    assert orden[2] == "PEDIDO"
    assert float(orden[3]) == 4.0
    cleaner.registrar("orden_produccion", orden[0])

    # La mesa ya está lista; las sillas no. El envío automático no se crea aún.
    pend = client.get(
        f"/api/v1/envio/pendientes/{pedido['id']}", headers=ADMIN_HEADERS
    ).json()["items"]
    por_pieza = {i["pieza_nombre"]: i for i in pend}
    assert float(por_pieza["Mesa del comedor"]["cantidad_lista"]) == 1.0
    assert float(por_pieza["Sillas nuevas"]["cantidad_lista"]) == 0.0
    assert envio_de_pedido(db, pedido["id"]) is None

    # El taller termina las sillas: el pedido cierra solo y el envío automático
    # incluye la mesa (sin orden) y las sillas (orden finalizada).
    empleado = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "EBANISTA"))
    etapa = crear_etapa(
        client, cleaner, orden[0], area_id(db, "Ebanistería"), empleado["id"]
    )
    avanzar_etapa(client, etapa["id"], "EN_PROCESO")
    registrar_mano_obra(client, cleaner, etapa["id"], empleado["id"], monto=5000.0)
    avanzar_etapa(client, etapa["id"], "COMPLETADA")
    finalizar_orden(client, orden[0])

    estado = db.execute(text(
        "SELECT estado FROM pedido WHERE id = :p"
    ), {"p": pedido["id"]}).scalar()
    assert estado == "TERMINADO"
    envio = envio_de_pedido(db, pedido["id"])
    assert envio is not None
    cleaner.registrar("envio", envio["id"])
    filas_envio = db.execute(text(
        "SELECT orden_produccion_id, detalle_pieza_id FROM envio_detalle "
        "WHERE envio_id = :e"
    ), {"e": envio["id"]}).fetchall()
    assert len(filas_envio) == 2, (
        "el envío automático debe incluir las sillas terminadas Y la mesa que ya "
        "estaba lista en exhibición"
    )
    assert any(f[0] is not None for f in filas_envio), "falta la silla fabricada"
    assert any(f[0] is None and f[1] is not None for f in filas_envio), "falta la mesa de exhibición"


def test_combo_exhibicion_con_retrabajo_crea_orden_retrabajo_sin_devolver_stock(client, db, cleaner):
    """Una pieza de exhibición con retoque entra al taller, pero NO vuelve al showroom."""
    pieza = _producto(
        client, cleaner, nombre=_uniq("pieza_ret"), costo=500.0, precio=900.0,
        es_exhibicion=True,
    )
    _entrar_showroom(client, cleaner, db, pieza["id"], 1, 500.0)

    cliente = client.post(
        "/api/v1/cliente/",
        json={"nombre": _uniq("cliente"), "telefono": "555-0000"},
        headers=ADMIN_HEADERS,
    ).json()
    cleaner.registrar("cliente", cliente["id"])

    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        _detalle_combo([
            {
                "nombre": "Sillón retapizado",
                "cantidad": 1,
                "producto_id": pieza["id"],
                "precio": 900.0,
                "origen": "EXHIBICION",
                "requiere_retrabajo": True,
                "modificacion": "Retapizar en lino gris",
                "precio_modificacion": 150.0,
            },
        ])
    ])
    det_cot = cot["detalles"][0]
    assert abs(float(det_cot["precio"]) - 1050.0) < 0.01

    r, pedido = convertir_cotizacion(
        client, cleaner, cot["id"], [_para_conversion(det_cot)]
    )
    assert r.status_code == 201, r.text
    assert pedido["estado"] == "PRODUCCION"
    detalle = pedido["detalles"][0]

    ordenes = db.execute(text(
        "SELECT id, tipo, producto_inventario_id, detalle_pieza_id, cantidad "
        "FROM orden_produccion WHERE detalle_pedido_id = :d"
    ), {"d": detalle["id"]}).fetchall()
    assert len(ordenes) == 1
    orden = ordenes[0]
    assert orden[1] == "RETRABAJO"
    assert orden[2] is None, "el retrabajo del pedido no está ligado a una fila de stock"
    assert orden[3] is not None
    cleaner.registrar("orden_produccion", orden[0])

    # La pieza salió del showroom al apartarla para el pedido.
    stock, _ = _stock_y_costo(db, pieza["id"])
    assert stock == 0.0

    # El taller retoca y finaliza: no debe volver a entrar stock.
    empleado = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "TAPICERO"))
    etapa = crear_etapa(
        client, cleaner, orden[0], area_id(db, "Tapicería"), empleado["id"]
    )
    avanzar_etapa(client, etapa["id"], "EN_PROCESO")
    registrar_mano_obra(client, cleaner, etapa["id"], empleado["id"], monto=5000.0)
    avanzar_etapa(client, etapa["id"], "COMPLETADA")
    final = finalizar_orden(client, orden[0])
    assert final["tipo"] == "RETRABAJO"

    stock_final, _ = _stock_y_costo(db, pieza["id"])
    assert stock_final == 0.0, "la pieza se entrega al cliente, no vuelve al showroom"
    entradas_retrabajo = db.execute(text(
        "SELECT COUNT(*) FROM movimiento_producto_inventario "
        "WHERE producto_id = :p AND referencia_tipo = 'PRODUCCION_RETRABAJO'"
    ), {"p": pieza["id"]}).scalar()
    assert entradas_retrabajo == 0

    # El pedido cerró solo (la única pieza ya está terminada) y la rentabilidad
    # suma el costo de la pieza + el retoque real.
    estado = db.execute(text(
        "SELECT estado FROM pedido WHERE id = :p"
    ), {"p": pedido["id"]}).scalar()
    assert estado == "TERMINADO"
    rent = client.get(
        f"/api/v1/pedido/{pedido['id']}/rentabilidad", headers=ADMIN_HEADERS
    ).json()
    assert float(rent["costo_real_produccion"]) >= 5500.0
    assert float(rent["margen_real"]) < 1050.0


def test_composicion_valida_precios_todos_o_ninguno_y_origen(client, cleaner):
    mesa = _producto(client, cleaner, nombre=_uniq("mesa"), costo=700.0, precio=900.0)
    silla = _producto(client, cleaner, nombre=_uniq("silla"), costo=75.0, precio=100.0)
    cliente = client.post(
        "/api/v1/cliente/",
        json={"nombre": _uniq("cliente"), "telefono": "555-0000"},
        headers=ADMIN_HEADERS,
    ).json()
    cleaner.registrar("cliente", cliente["id"])

    def _intentar(piezas, precio=100.0):
        return client.post("/api/v1/cotizacion/", json={
            "cliente_id": cliente["id"],
            "fecha": "2026-11-03",
            "estado": "BORRADOR",
            "total_estimado": precio,
            "moneda_id": 1,
            "tasa_cambio": 1.0,
            "detalles": [_detalle_combo(piezas, precio=precio)],
        }, headers=ADMIN_HEADERS)

    # Una pieza con precio y otra sin precio: el total no cuadraría.
    r = _intentar([
        {"nombre": "Mesa", "cantidad": 1, "producto_id": mesa["id"], "precio": 100.0},
        {"nombre": "Silla", "cantidad": 1, "producto_id": silla["id"]},
    ])
    assert r.status_code == 422, r.text
    assert "TODAS precio o NINGUNA" in r.text

    # Pieza de exhibición sin producto del catálogo: no se puede despiezar.
    r = _intentar([
        {"nombre": "Mesa", "cantidad": 1, "precio": 100.0, "origen": "EXHIBICION"},
    ])
    assert r.status_code == 422, r.text

    # Precio de modificación sin retrabajo: dato incoherente.
    r = _intentar([
        {
            "nombre": "Silla", "cantidad": 1, "producto_id": silla["id"],
            "precio": 100.0, "precio_modificacion": 20.0,
        },
    ])
    assert r.status_code == 422, r.text


def test_editar_cotizacion_compuesta_recalcula_precio_y_costo(client, db, cleaner):
    mesa = _producto(client, cleaner, nombre=_uniq("mesa"), costo=700.0, precio=900.0)
    silla = _producto(client, cleaner, nombre=_uniq("silla"), costo=75.0, precio=100.0)
    cliente = client.post(
        "/api/v1/cliente/",
        json={"nombre": _uniq("cliente"), "telefono": "555-0000"},
        headers=ADMIN_HEADERS,
    ).json()
    cleaner.registrar("cliente", cliente["id"])

    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        _detalle_combo([
            {
                "nombre": "Mesa",
                "cantidad": 1,
                "producto_id": mesa["id"],
                "precio": 900.0,
                "origen": "FABRICADO",
            },
        ], precio=900.0)
    ])
    det_id = cot["detalles"][0]["id"]

    # Edición: la UI manda el detalle completo y un total viejo (1). El backend
    # debe recalcular con las piezas: 900 + 2×100 = 1.100 y costo 700 + 2×75.
    r = client.put(f"/api/v1/cotizacion/{cot['id']}", json={
        "total_estimado": 1,
        "detalles": [_detalle_combo([
            {
                "nombre": "Mesa",
                "cantidad": 1,
                "producto_id": mesa["id"],
                "precio": 900.0,
                "origen": "FABRICADO",
            },
            {
                "nombre": "Sillas",
                "cantidad": 2,
                "producto_id": silla["id"],
                "precio": 100.0,
                "origen": "FABRICADO",
            },
        ], precio=1.0)],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["detalles"][0]["id"] != det_id, "los renglones se reemplazan completos"
    assert abs(float(body["detalles"][0]["precio"]) - 1100.0) < 0.01
    assert abs(float(body["total_estimado"]) - 1100.0) < 0.01
    assert abs(float(body["detalles"][0]["costo_total"]) - 850.0) < 0.01
    assert len(body["detalles"][0]["piezas"]) == 2
    assert body["detalles"][0]["piezas"][1]["producto_id"] == silla["id"]
