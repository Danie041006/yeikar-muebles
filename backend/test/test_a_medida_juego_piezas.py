# -*- coding: utf-8 -*-
"""
test_a_medida_juego_piezas.py — Cotizaciones de papel con juegos (un renglón,
precio global) y checklist de piezas auto-detectado.

Caso real: cotización de JOHAN RODRIGUEZ (el juego de sala se cotiza como UN
renglón: sofá de 3 puestos + 2 poltronas, precio global $2.650). Cubre:

  1. Alta de renglones "a medida" (FABRICADO sin producto de catálogo).
  2. Conversión cotización→pedido SIN colapsar renglones a medida (el bug
     histórico indexaba por producto_id NULL y perdía renglones).
  3. Auto-detección del checklist de piezas y su marcado por el taller.
  4. Producción real del juego: consumo descuenta inventario + gasto,
     mano de obra, finalizar calcula el costo con gastos de sección, pedido
     TERMINADO + envío automático.
  5. Ataques/bordes: renglones idénticos, precios alterados, renglones
     ajenos, piezas inexistentes/canceladas, validaciones de descripción.

Ejecutar:
  cd backend && source venv/bin/activate && python -m pytest test/test_a_medida_juego_piezas.py -v
"""
import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_material,
    registrar_inventario_de_material,
    _uniq,
)
from helpers_e2e import (
    area_id,
    avanzar_etapa,
    cargo_id,
    convertir_cotizacion,
    crear_cotizacion_multidetalle,
    crear_consumo,
    crear_empleado,
    crear_etapa,
    entrar_stock_material,
    envio_de_pedido,
    finalizar_orden,
    registrar_mano_obra,
    stock_material,
    venta_de_pedido,
)


# ---------------------------------------------------------------------------
# Cotización de JOHAN RODRIGUEZ (transcrita de la nota de papel)
# ---------------------------------------------------------------------------
LINEAS_JOHAN = [
    {
        "desc": (
            "JUEGO DE SALA TAL CUAL EL VIDEO ES UN SOFA DE 3 PUESTOS CON SUS HERRAJES "
            "DESPLAZABLES Y 2 POLTRONAS. TAPIZAR LOS MUEBLES EN TELA DOTTY HOME 1310 Y LOS "
            "BRAZOS EN CUERINA PRANNA CAPUCHINO Y 3 COJINES EN LA MISMA CUERINA Y 3 COJINES "
            "EN PERSEA CREMA, PINTAR LA PASE Y LAS PATAS DEL MUEBLE EN EL TONO DE LA CUERINA."
        ),
        "cantidad": 1, "precio": 2650.0, "ancho": 3.0, "largo": 1.0,
    },
    {
        "desc": (
            "POLTRONAS TAL CUAL AL MODELO, TAPIZAR EN TELA JOURNEY 01 CRUDO CON SUS 2 COJINES "
            "EN TELA VERA HOME 9600 Y PINTAR EN EL TONO DEL MUEBLE PRINCIPAL, LAS PATAS"
        ),
        "cantidad": 2, "precio": 630.0,
    },
    {
        "desc": "JUEGO DE MESAS DE CENTRO, PINTAR, CAPUCHINO",
        "cantidad": 1, "precio": 480.0,
    },
    {
        "desc": (
            "CAMA MATRIMONIAL MODELO DE ESPALDAR COMO EL DE LA FOTO, HACERLA AEREA Y PINTAR "
            "LOS LARGUEROS Y EL PIECERO QUE VAYA TAPIZADO LISO Y LOS BORDES PINTADOS"
        ),
        "cantidad": 1, "precio": 1150.0,
    },
    {
        "desc": "MESAS DE NOCHE DEL MODELO DE LA FOTO PINTAR EN WENGUE CON MANIJA DORADA, AEREA",
        "cantidad": 2, "precio": 215.0,
    },
    {
        "desc": "ESPEJO DECORATIVO DE 2X1",
        "cantidad": 1, "precio": 290.0,
    },
    {
        "desc": "COJIN ENTRELAZADO BLANCO",
        "cantidad": 1, "precio": 35.0,
    },
]
TOTAL_JOHAN = 6295.0  # 2650 + 2×630 + 480 + 1150 + 2×215 + 290 + 35


def _detalles_payload(lineas=LINEAS_JOHAN):
    """Renglones a medida tal como los manda el frontend (sin producto)."""
    detalles = []
    for linea in lineas:
        detalle = {
            "tipo_item": "FABRICADO",
            "cantidad": linea["cantidad"],
            "precio": linea["precio"],
            "descripcion_especifica": linea["desc"],
        }
        if linea.get("ancho") is not None:
            detalle["ancho"] = linea["ancho"]
        if linea.get("largo") is not None:
            detalle["largo"] = linea["largo"]
        detalles.append(detalle)
    return detalles


def _orden_de_detalle(db, detalle_pedido_id) -> int:
    row = db.execute(
        text("SELECT id FROM orden_produccion WHERE detalle_pedido_id = :d"),
        {"d": detalle_pedido_id},
    ).fetchone()
    assert row, f"no hay orden de producción para el detalle {detalle_pedido_id}"
    return int(row[0])


def _piezas_de_orden(client, orden_id) -> list[dict]:
    r = client.get(f"/api/v1/produccion/orden/{orden_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET orden → {r.status_code}: {r.text}"
    return r.json().get("piezas", [])


# ===========================================================================
# 1. La cotización completa de JOHAN entra, se guarda y convierte íntegra.
# ===========================================================================
def test_cotizacion_johan_convierte_sin_colapsar_renglones(client, db, cleaner):
    cliente = crear_cliente(client, cleaner, nombre=_uniq("johan"))
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], _detalles_payload())
    assert abs(float(cot["total_estimado"]) - TOTAL_JOHAN) < 0.01, cot["total_estimado"]
    assert len(cot["detalles"]) == len(LINEAS_JOHAN)
    assert all(d["producto_id"] is None for d in cot["detalles"])

    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], _detalles_payload())
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    assert pedido["estado"] == "PRODUCCION"

    # Los 7 renglones a medida sobreviven: antes el indexado por producto_id
    # NULL colapsaba todo en una sola clave y la conversión fallaba. La
    # relación no garantiza orden, así que se empareja por descripción.
    assert len(pedido["detalles"]) == len(LINEAS_JOHAN)
    for esperado in LINEAS_JOHAN:
        coincidencias = [
            d for d in pedido["detalles"]
            if esperado["desc"][:40] in (d["descripcion_especifica"] or "")
        ]
        assert len(coincidencias) == 1, f"renglón '{esperado['desc'][:40]}' no está 1:1"
        enviado = coincidencias[0]
        assert enviado["producto_id"] is None
        assert enviado["tipo_item"] == "FABRICADO"
        assert abs(float(enviado["precio"]) - esperado["precio"]) < 0.01
        assert abs(float(enviado["cantidad"]) - esperado["cantidad"]) < 0.001

    # Una orden de producción por renglón fabricado + la factura con el total.
    ordenes = db.execute(
        text(
            "SELECT o.id FROM orden_produccion o JOIN detalle_pedido d ON d.id = o.detalle_pedido_id "
            "WHERE d.pedido_id = :p ORDER BY o.id"
        ),
        {"p": pedido["id"]},
    ).fetchall()
    assert len(ordenes) == len(LINEAS_JOHAN)
    venta = venta_de_pedido(client, db, pedido["id"])
    assert venta and abs(float(venta["total"]) - TOTAL_JOHAN) < 0.01

    def _detalle_por_texto(fragmento: str) -> dict:
        return next(
            d for d in pedido["detalles"]
            if fragmento in (d["descripcion_especifica"] or "")
        )

    # El juego detecta sus piezas solo, desde el texto de la nota.
    juego_detalle = _detalle_por_texto("JUEGO DE SALA")
    piezas = _piezas_de_orden(client, _orden_de_detalle(db, juego_detalle["id"]))
    assert [(p["nombre"], float(p["cantidad"])) for p in piezas] == [
        ("Sofá de 3 puestos", 1.0),
        ("Poltrona", 2.0),
    ]

    # Un mueble suelto (cama, espejo…) NO genera checklist: cero ruido.
    cama_detalle = _detalle_por_texto("CAMA MATRIMONIAL")
    assert _piezas_de_orden(client, _orden_de_detalle(db, cama_detalle["id"])) == []


# ===========================================================================
# 2. El juego se fabrica de verdad: inventario, gasto, costos y cierre.
# ===========================================================================
def test_juego_produccion_descuenta_inventario_calcula_costo_y_cierra(client, db, cleaner):
    cliente = crear_cliente(client, cleaner, nombre=_uniq("juego"))
    material = crear_material(client, cleaner, costo_base=1000.0)
    entrar_stock_material(client, cleaner, material["id"], 100)
    assert stock_material(db, material["id"]) == 100.0

    juego = [LINEAS_JOHAN[0]]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], _detalles_payload(juego))
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], _detalles_payload(juego))
    assert r.status_code == 201, r.text

    detalle_id = pedido["detalles"][0]["id"]
    orden_id = _orden_de_detalle(db, detalle_id)
    piezas = _piezas_de_orden(client, orden_id)
    assert len(piezas) == 2

    # El taller marca las piezas al armarlas (checklist informativo).
    for pieza in piezas:
        r = client.put(
            f"/api/v1/produccion/pieza/{pieza['id']}",
            json={"completada": True},
            headers=ADMIN_HEADERS,
        )
        assert r.status_code == 200, r.text
        assert r.json()["completada"] is True
        assert r.json()["fecha_completada"] is not None
    piezas = _piezas_de_orden(client, orden_id)
    assert all(p["completada"] for p in piezas)

    empleado = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "EBANISTA"))
    etapa = crear_etapa(client, cleaner, orden_id, area_id(db, "Ebanistería"), empleado["id"])
    avanzar_etapa(client, etapa["id"], "EN_PROCESO")

    r, consumo = crear_consumo(client, cleaner, db, etapa["id"], material["id"], 3, empleado["id"])
    assert r.status_code == 201, f"consumo → {r.status_code}: {r.text}"
    # Inventario descontado y reflejado en el kardex.
    assert stock_material(db, material["id"]) == 97.0
    mov = db.execute(
        text(
            "SELECT tipo, cantidad FROM movimiento_inventario "
            "WHERE material_id = :m ORDER BY id DESC LIMIT 1"
        ),
        {"m": material["id"]},
    ).fetchone()
    assert mov and mov[0] == "SALIDA" and float(mov[1]) == 3.0
    # El consumo generó su egreso en el P&L (gasto automático por consumo).
    gasto = db.execute(
        text("SELECT monto FROM gasto WHERE observaciones LIKE :p"),
        {"p": f"%[consumo {consumo['id']}]%"},
    ).fetchone()
    assert gasto and float(gasto[0]) == 3000.0

    registrar_mano_obra(client, cleaner, etapa["id"], empleado["id"], 200000.0)
    avanzar_etapa(client, etapa["id"], "COMPLETADA")

    finalizada = finalizar_orden(client, orden_id)
    assert finalizada["estado"] == "FINALIZADA"

    # Costo real guardado: materiales + MO + gastos de sección (Ebanistería 10%).
    costo = db.execute(
        text(
            "SELECT costo_material, costo_mano_obra, costo_gastos, costo_total "
            "FROM costo_produccion WHERE orden_produccion_id = :o"
        ),
        {"o": orden_id},
    ).fetchone()
    assert costo is not None
    assert float(costo[0]) == pytest.approx(3000.0, abs=0.01)
    assert float(costo[1]) == pytest.approx(200000.0, abs=0.01)
    assert float(costo[2]) == pytest.approx(20300.0, abs=0.01)  # 10% de 203.000
    assert float(costo[3]) == pytest.approx(223300.0, abs=0.01)
    assert float(costo[3]) == pytest.approx(
        float(costo[0]) + float(costo[1]) + float(costo[2]), abs=0.01
    )

    # La orden única del pedido: pedido TERMINADO + envío automático.
    estado_pedido = db.execute(
        text("SELECT estado FROM pedido WHERE id = :p"), {"p": pedido["id"]}
    ).scalar()
    assert estado_pedido == "TERMINADO"
    envio = envio_de_pedido(db, pedido["id"])
    assert envio is not None and envio["estado"] == "PREPARADO"

    # Las piezas marcadas sobreviven al cierre (no se pierden ni se resetean).
    piezas_final = _piezas_de_orden(client, orden_id)
    assert len(piezas_final) == 2 and all(p["completada"] for p in piezas_final)


# ===========================================================================
# 3. Ataques y bordes.
# ===========================================================================
def test_ataques_renglones_a_medida(client, db, cleaner):
    cliente = crear_cliente(client, cleaner, nombre=_uniq("ataques"))

    # 3a. Dos renglones a medida IDÉNTICOS no se colapsan ni se mezclan.
    detalle = {
        "tipo_item": "FABRICADO",
        "cantidad": 1,
        "precio": 700.0,
        "descripcion_especifica": "MUEBLE DE 2 PUESTOS TAL CUAL A LA FOTO",
    }
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle, dict(detalle)])
    assert len(cot["detalles"]) == 2
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [detalle, dict(detalle)])
    assert r.status_code == 201, r.text
    assert len(pedido["detalles"]) == 2
    assert len({d["id"] for d in pedido["detalles"]}) == 2

    # 3b. Precio alterado en un renglón a medida → rechazo con mensaje claro.
    cot2 = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle])
    alterado = dict(detalle, precio=1.0)
    r, _ = convertir_cotizacion(client, cleaner, cot2["id"], [alterado])
    assert r.status_code == 400
    assert "no coincide" in r.json()["detail"].lower()

    # 3c. Renglón con producto que no pertenece a la cotización → rechazo
    # (los renglones a medida no tienen clave: se emparejan por posición).
    cot3 = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle])
    ajeno = {
        "tipo_item": "REVENTA", "producto_id": 999999999,
        "cantidad": 1, "precio": 999.0,
    }
    r, _ = convertir_cotizacion(client, cleaner, cot3["id"], [ajeno])
    assert r.status_code == 400
    assert "no forma parte" in r.json()["detail"].lower()

    # 3d. FABRICADO sin producto NI descripción → 422 del esquema.
    r = client.post(
        "/api/v1/cotizacion/",
        json={
            "cliente_id": cliente["id"], "fecha": "2026-10-06", "estado": "BORRADOR",
            "total_estimado": 100.0, "moneda_id": 1, "tasa_cambio": 1.0,
            "detalles": [{"tipo_item": "FABRICADO", "cantidad": 1, "precio": 100.0}],
        },
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422

    # 3e. REVENTA sin producto sigue siendo inválida (no es a medida).
    r = client.post(
        "/api/v1/cotizacion/",
        json={
            "cliente_id": cliente["id"], "fecha": "2026-10-06", "estado": "BORRADOR",
            "total_estimado": 100.0, "moneda_id": 1, "tasa_cambio": 1.0,
            "detalles": [{"tipo_item": "REVENTA", "cantidad": 1, "precio": 100.0,
                          "descripcion_especifica": "colchón sin producto"}],
        },
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422


def test_ataques_piezas(client, db, cleaner):
    cliente = crear_cliente(client, cleaner, nombre=_uniq("piezas"))

    # Orden cancelada: no admite piezas nuevas ni cambios.
    juego = [LINEAS_JOHAN[0]]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], _detalles_payload(juego))
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], _detalles_payload(juego))
    assert r.status_code == 201, r.text
    orden_id = _orden_de_detalle(db, pedido["detalles"][0]["id"])

    r = client.post(
        f"/api/v1/produccion/orden/{orden_id}/piezas",
        json={"nombre": "Puff extra", "cantidad": 1},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    pieza_extra = r.json()

    # Cantidad inválida y nombre vacío son rechazados por el esquema/servicio.
    r = client.post(
        f"/api/v1/produccion/orden/{orden_id}/piezas",
        json={"nombre": "Mala", "cantidad": 0},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422
    r = client.put(
        f"/api/v1/produccion/pieza/{pieza_extra['id']}",
        json={"nombre": "   "},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400

    # Pieza inexistente → 404.
    r = client.put(
        "/api/v1/produccion/pieza/999999999",
        json={"completada": True},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 404

    # El toggle es idempotente: marcar dos veces NO reescribe la fecha original.
    r1 = client.put(
        f"/api/v1/produccion/pieza/{pieza_extra['id']}",
        json={"completada": True},
        headers=ADMIN_HEADERS,
    )
    fecha1 = r1.json()["fecha_completada"]
    r2 = client.put(
        f"/api/v1/produccion/pieza/{pieza_extra['id']}",
        json={"completada": True},
        headers=ADMIN_HEADERS,
    )
    assert r2.json()["fecha_completada"] == fecha1
    # Desmarcar limpia fecha/quién; volver a marcar la pone de nuevo.
    r3 = client.put(
        f"/api/v1/produccion/pieza/{pieza_extra['id']}",
        json={"completada": False},
        headers=ADMIN_HEADERS,
    )
    assert r3.json()["completada"] is False
    assert r3.json()["fecha_completada"] is None

    # Borrar la pieza; repetir el borrado → 404.
    assert client.delete(
        f"/api/v1/produccion/pieza/{pieza_extra['id']}", headers=ADMIN_HEADERS
    ).status_code == 204
    assert client.delete(
        f"/api/v1/produccion/pieza/{pieza_extra['id']}", headers=ADMIN_HEADERS
    ).status_code == 404

    # Orden cancelada: ni agregar ni modificar piezas.
    r = client.put(
        f"/api/v1/produccion/orden/{orden_id}/estado",
        params={"estado": "CANCELADA"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    r = client.post(
        f"/api/v1/produccion/orden/{orden_id}/piezas",
        json={"nombre": "Tarde", "cantidad": 1},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400
    piezas = _piezas_de_orden(client, orden_id)
    if piezas:
        r = client.put(
            f"/api/v1/produccion/pieza/{piezas[0]['id']}",
            json={"completada": True},
            headers=ADMIN_HEADERS,
        )
        assert r.status_code == 400


def test_conversion_mixta_a_medida_insumo_reparacion(client, db, cleaner):
    """Mezcla de renglones: a medida (posicional) + insumo (por material) +
    reparación (pieza del cliente). El emparejamiento híbrido no debe cruzarlos."""
    cliente = crear_cliente(client, cleaner, nombre=_uniq("mixta"))
    material = crear_material(client, cleaner, costo_base=500.0)
    entrar_stock_material(client, cleaner, material["id"], 10)
    detalles = [
        {"tipo_item": "FABRICADO", "cantidad": 1, "precio": 500.0,
         "descripcion_especifica": "JUEGO DE MUEBLES DE 3 PUESTOS Y 2 POLTRONAS"},
        {"tipo_item": "INSUMO", "material_id": material["id"], "cantidad": 2, "precio": 100.0},
        {"tipo_item": "REPARACION", "cantidad": 1, "precio": 300.0,
         "descripcion_especifica": "TAPIZAR SOFA DEL CLIENTE"},
        {"tipo_item": "FABRICADO", "cantidad": 2, "precio": 700.0,
         "descripcion_especifica": "MUEBLE DE 2 PUESTOS TAL CUAL A LA FOTO"},
    ]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], detalles)
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], detalles)
    assert r.status_code == 201, r.text
    # La factura automática descontó el insumo: registrar su kardex/inventario.
    registrar_inventario_de_material(db, cleaner, material["id"])
    assert len(pedido["detalles"]) == 4
    # Cada tipo conserva su precio/cantidad exactos (nada se cruzó).
    por_tipo = {}
    for d in pedido["detalles"]:
        por_tipo.setdefault(d["tipo_item"], []).append(d)
    assert len(por_tipo["FABRICADO"]) == 2
    assert len(por_tipo["INSUMO"]) == 1 and len(por_tipo["REPARACION"]) == 1
    # 500 + 2×100 (insumo) + 300 (reparación) + 2×700 = 2400
    assert abs(sum(float(d["precio"]) * float(d["cantidad"]) for d in pedido["detalles"]) - 2400.0) < 0.01


def test_checklist_no_bloquea_finalizar_aunque_falte_marcar(client, db, cleaner):
    """Regla elegida: el checklist AVISA (frontend), no bloquea el cierre."""
    cliente = crear_cliente(client, cleaner, nombre=_uniq("soft"))
    juego = [LINEAS_JOHAN[0]]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], _detalles_payload(juego))
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], _detalles_payload(juego))
    assert r.status_code == 201, r.text
    orden_id = _orden_de_detalle(db, pedido["detalles"][0]["id"])

    # Piezas SIN marcar (ninguna completada) y aun así la orden finaliza.
    assert all(not p["completada"] for p in _piezas_de_orden(client, orden_id))
    empleado = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "EBANISTA"))
    etapa = crear_etapa(client, cleaner, orden_id, area_id(db, "Ebanistería"), empleado["id"])
    avanzar_etapa(client, etapa["id"], "EN_PROCESO")
    avanzar_etapa(client, etapa["id"], "COMPLETADA")
    finalizada = finalizar_orden(client, orden_id)
    assert finalizada["estado"] == "FINALIZADA"


# ===========================================================================
# 4. Ficha/Hoja de Trabajo para muebles a la medida (sin producto).
# ===========================================================================
def test_referencia_receta_sin_producto_trae_piezas(client, db, cleaner):
    cliente = crear_cliente(client, cleaner, nombre=_uniq("ref"))
    juego = [LINEAS_JOHAN[0]]
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], _detalles_payload(juego))
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], _detalles_payload(juego))
    assert r.status_code == 201, r.text
    orden_id = _orden_de_detalle(db, pedido["detalles"][0]["id"])

    empleado = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "EBANISTA"))
    etapa = crear_etapa(client, cleaner, orden_id, area_id(db, "Ebanistería"), empleado["id"])

    # Antes devolvía 404 (sin producto no había ficha ni Hoja de Trabajo).
    r = client.get(
        f"/api/v1/produccion/etapa/{etapa['id']}/referencia-receta", headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, f"referencia sin producto → {r.status_code}: {r.text}"
    data = r.json()
    assert data["producto_id"] is None
    assert data["materiales"] == []
    assert data["descripcion_especifica"] in data["producto_nombre"]
    assert [(p["nombre"], float(p["cantidad"])) for p in data["piezas_mueble"]] == [
        ("Sofá de 3 puestos", 1.0),
        ("Poltrona", 2.0),
    ]
    assert data["cliente_nombre"] == cliente["nombre"]
    assert len(data["piezas_mueble"]) == 2


# ===========================================================================
# 5. Motor de detección (sin HTTP): conservador y a prueba de basura.
# ===========================================================================
def test_detector_de_piezas_bordes():
    from app.modules.production.piezas import detectar_piezas

    # Juego real: sofá + poltronas con conteo en palabras y números.
    assert detectar_piezas("JUEGO: DOS SOFAS Y TRES SILLAS") == [
        {"nombre": "Sofá", "cantidad": 2},
        {"nombre": "Silla", "cantidad": 3},
    ]
    # Un mueble suelto no genera checklist (la cantidad vive en el renglón).
    assert detectar_piezas("MUEBLE DE 2 PUESTOS TAL CUAL A LA FOTO") == []
    assert detectar_piezas("2 MESAS DE NOCHE PINTADAS") == []
    assert detectar_piezas("POLTRONA TAL CUAL A LA FOTO") == []
    # Sin descripción tampoco.
    assert detectar_piezas(None) == []
    assert detectar_piezas("") == []
    # Números fuera de rango o sin sustantivo no inventan piezas.
    assert detectar_piezas("JUEGO DE 99 POLTRONAS") == []
    assert detectar_piezas("JUEGO DE 0 POLTRONAS") == []
    # Abreviatura de taller.
    assert detectar_piezas("SOFA 3P + 2 POLTRONAS") == [
        {"nombre": "Sofá de 3 puestos", "cantidad": 1},
        {"nombre": "Poltrona", "cantidad": 2},
    ]
    # Defensa: descripciones absurdas no llenan la tarjeta (máx. 12 líneas).
    absurdo = "JUEGO " + " ".join(
        f"{i + 2} POLTRONAS" for i in range(30)
    )
    piezas = detectar_piezas(absurdo)
    assert len(piezas) == 1  # el mismo sustantivo se acumula, no se duplica
    assert piezas[0]["nombre"] == "Poltrona"
    assert piezas[0]["cantidad"] > 0
