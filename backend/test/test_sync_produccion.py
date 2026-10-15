"""F2: push offline del taller — pasar a área, consumos y mano de obra.

Ejecutar: pytest test/test_sync_produccion.py -v
"""
import uuid

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_orden_desde_pedido,
    crear_producto,
    registrar_inventario_de_material,
    registrar_venta_de_pedido,
)
from helpers_e2e import areas, entrar_stock_material


def _push(client, operaciones):
    return client.post("/api/v1/sync/push", json={"operaciones": operaciones}, headers=ADMIN_HEADERS)


def _borrar_operaciones(db, ids):
    db.execute(text("DELETE FROM sync_operacion WHERE operacion_id = ANY(:ids)"), {"ids": [str(i) for i in ids]})
    db.commit()


def _etapa_en_proceso(client, etapa_id):
    r = client.put(
        f"/api/v1/produccion/etapa/{etapa_id}/estado",
        params={"estado": "EN_PROCESO"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text


def _orden_con_etapa(client, cleaner, db):
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100_000.0)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 100_000.0}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    orden = crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])

    area_actual = next(iter(areas(db).values()))
    r = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"],
        "area_id": area_actual,
        "empleado_responsable_id": 3,
        "estado": "ASIGNADA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    etapa = r.json()
    cleaner.registrar("etapa_produccion", etapa["id"])
    return orden, etapa


def test_push_pasar_area_completa_y_crea_nueva(client, db, cleaner):
    orden, etapa = _orden_con_etapa(client, cleaner, db)
    destino = next(v for v in areas(db).values() if v != etapa["area_id"])

    op_id = uuid.uuid4()
    try:
        op = {
            "operacion_id": str(op_id),
            "tipo": "produccion.etapa.pasar-area",
            "payload": {
                "etapa_id": etapa["id"],
                "area_id": destino,
                "empleado_responsable_id": 3,
                "empleados_adicionales_ids": [],
            },
        }
        r = _push(client, [op])
        resultado = r.json()["resultados"][0]
        assert resultado["estado"] == "ok", resultado

        vieja = client.get(f"/api/v1/produccion/etapa/{etapa['id']}", headers=ADMIN_HEADERS).json()
        assert vieja["estado"] == "COMPLETADA"

        nueva_id = resultado["entidad"]["id"]
        cleaner.registrar("etapa_produccion", nueva_id)
        nueva = client.get(f"/api/v1/produccion/etapa/{nueva_id}", headers=ADMIN_HEADERS).json()
        assert nueva["estado"] == "ASIGNADA"
        assert nueva["area_id"] == destino
        assert nueva["orden_produccion_id"] == orden["id"]

        # Reintento idempotente: no crea otra etapa
        r2 = _push(client, [op])
        assert r2.json()["resultados"][0] == resultado
        activas = db.execute(text(
            "SELECT count(*) FROM etapa_produccion WHERE orden_produccion_id = :o AND estado != 'COMPLETADA'"
        ), {"o": orden["id"]}).scalar()
        assert activas == 1
    finally:
        _borrar_operaciones(db, [op_id])


def test_push_consumo_y_mano_obra(client, db, cleaner):
    orden, etapa = _orden_con_etapa(client, cleaner, db)
    _etapa_en_proceso(client, etapa["id"])
    material = crear_material(client, cleaner)
    entrar_stock_material(client, cleaner, material["id"], 10)

    consumo_op = uuid.uuid4()
    mano_op = uuid.uuid4()
    try:
        id_local = str(uuid.uuid4())
        op_consumo = {
            "operacion_id": str(consumo_op),
            "tipo": "produccion.consumo.registrar",
            "payload": {
                "etapa_produccion_id": etapa["id"],
                "material_id": material["id"],
                "cantidad": 2,
                "fecha": "2026-10-13T10:00:00",
                "solicitante_empleado_id": 3,
                "observaciones": "consumo offline",
                "id_local": id_local,
            },
        }
        r = _push(client, [op_consumo])
        resultado = r.json()["resultados"][0]
        assert resultado["estado"] == "ok", resultado
        assert resultado["entidad"]["id_local"] == id_local

        consumo_id = resultado["entidad"]["id"]
        cleaner.registrar("consumo_material", consumo_id)
        for (gid,) in db.execute(text(
            "SELECT id FROM gasto WHERE observaciones LIKE :pat"
        ), {"pat": f"%[consumo {consumo_id}]%"}).fetchall():
            cleaner.registrar("gasto", gid)
        registrar_inventario_de_material(db, cleaner, material["id"])

        listado = client.get(f"/api/v1/produccion/consumo/por-orden/{orden['id']}", headers=ADMIN_HEADERS).json()
        assert any(c["id"] == consumo_id for c in listado)

        op_mano = {
            "operacion_id": str(mano_op),
            "tipo": "produccion.mano-obra.registrar",
            "payload": {
                "etapa_produccion_id": etapa["id"],
                "empleado_id": 3,
                "monto": 250.0,
                "porcentaje_recargo": 0.0,
                "observaciones": "MO offline",
            },
        }
        r = _push(client, [op_mano])
        resultado_mano = r.json()["resultados"][0]
        assert resultado_mano["estado"] == "ok", resultado_mano
        cleaner.registrar("mano_obra", resultado_mano["entidad"]["id"])
    finally:
        _borrar_operaciones(db, [consumo_op, mano_op])


def test_push_consumo_pendiente_no_se_elimina_en_servidor(client, db, cleaner):
    orden, etapa = _orden_con_etapa(client, cleaner, db)
    op_id = uuid.uuid4()
    try:
        op = {
            "operacion_id": str(op_id),
            "tipo": "produccion.consumo.eliminar",
            "payload": {"consumo_id": -1234},
        }
        r = _push(client, [op])
        resultado = r.json()["resultados"][0]
        assert resultado["estado"] == "conflicto"
        assert "dispositivo" in (resultado["detalle"] or "")
    finally:
        _borrar_operaciones(db, [op_id])


def test_push_pasar_area_conflicto_si_ya_esta_completada(client, db, cleaner):
    orden, etapa = _orden_con_etapa(client, cleaner, db)
    destino = next(v for v in areas(db).values() if v != etapa["area_id"])
    _etapa_en_proceso(client, etapa["id"])
    r = client.put(
        f"/api/v1/produccion/etapa/{etapa['id']}/estado",
        params={"estado": "COMPLETADA"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text

    op_id = uuid.uuid4()
    try:
        op = {
            "operacion_id": str(op_id),
            "tipo": "produccion.etapa.pasar-area",
            "payload": {
                "etapa_id": etapa["id"],
                "area_id": destino,
                "empleado_responsable_id": 3,
                "empleados_adicionales_ids": [],
            },
        }
        r = _push(client, [op])
        resultado = r.json()["resultados"][0]
        assert resultado["estado"] == "conflicto"
        assert "completada" in (resultado["detalle"] or "").lower()
    finally:
        _borrar_operaciones(db, [op_id])
