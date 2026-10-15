"""F3: push offline de clientes, cotizaciones y pedidos.

Ejecutar: pytest test/test_sync_clientes_cotizaciones.py -v
"""
import uuid
from datetime import date

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_cliente,
    crear_cotizacion,
    crear_producto,
    registrar_venta_de_pedido,
)


def _push(client, operaciones):
    return client.post("/api/v1/sync/push", json={"operaciones": operaciones}, headers=ADMIN_HEADERS)


def _borrar_operaciones(db, ids):
    db.execute(text("DELETE FROM sync_operacion WHERE operacion_id = ANY(:ids)"), {"ids": [str(i) for i in ids]})
    db.commit()


def test_push_cliente_ciclo_completo(client, db, cleaner):
    op_crear, op_update, op_delete = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    id_local = str(uuid.uuid4())
    nombre = _uniq("sync_cli")
    try:
        crear = {
            "operacion_id": str(op_crear),
            "tipo": "cliente.crear",
            "payload": {"nombre": nombre, "telefono": "555-0000", "id_local": id_local},
        }
        resultado = _push(client, [crear]).json()["resultados"][0]
        assert resultado["estado"] == "ok", resultado
        assert resultado["entidad"]["id_local"] == id_local
        cliente_id = resultado["entidad"]["id"]
        cleaner.registrar("cliente", cliente_id)

        # Reintento idempotente: no crea otro cliente
        reintento = _push(client, [crear]).json()["resultados"][0]
        assert reintento == resultado
        repetidos = db.execute(
            text("SELECT count(*) FROM cliente WHERE nombre = :n"), {"n": nombre}
        ).scalar()
        assert repetidos == 1

        assert client.get(f"/api/v1/cliente/{cliente_id}", headers=ADMIN_HEADERS).json()["nombre"] == nombre

        actualizar = {
            "operacion_id": str(op_update),
            "tipo": "cliente.actualizar",
            "payload": {"cliente_id": cliente_id, "telefono": "555-9999"},
        }
        assert _push(client, [actualizar]).json()["resultados"][0]["estado"] == "ok"
        assert client.get(f"/api/v1/cliente/{cliente_id}", headers=ADMIN_HEADERS).json()["telefono"] == "555-9999"

        eliminar = {
            "operacion_id": str(op_delete),
            "tipo": "cliente.eliminar",
            "payload": {"cliente_id": cliente_id},
        }
        assert _push(client, [eliminar]).json()["resultados"][0]["estado"] == "ok"
        assert client.get(f"/api/v1/cliente/{cliente_id}", headers=ADMIN_HEADERS).status_code == 404

        # Otro intento con UUID nuevo sobre un cliente ya borrado → conflicto
        repetido = {
            "operacion_id": str(uuid.uuid4()),
            "tipo": "cliente.eliminar",
            "payload": {"cliente_id": cliente_id},
        }
        resultado = _push(client, [repetido]).json()["resultados"][0]
        assert resultado["estado"] == "conflicto"
        _borrar_operaciones(db, [repetido["operacion_id"]])
    finally:
        _borrar_operaciones(db, [op_crear, op_update, op_delete])


def test_push_cotizacion_ciclo(client, db, cleaner):
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    op_crear, op_update, op_delete = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    id_local = str(uuid.uuid4())
    try:
        crear = {
            "operacion_id": str(op_crear),
            "tipo": "cotizacion.crear",
            "payload": {
                "cliente_id": cli["id"],
                "fecha": str(date.today()),
                "estado": "BORRADOR",
                "total_estimado": 1000.0,
                "moneda_id": 1,
                "tasa_cambio": 1.0,
                "observaciones": _uniq("sync_cot"),
                "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 1000.0, "ancho": 1.6, "largo": 1.9}],
                "id_local": id_local,
            },
        }
        resultado = _push(client, [crear]).json()["resultados"][0]
        assert resultado["estado"] == "ok", resultado
        assert resultado["entidad"]["id_local"] == id_local
        cotizacion_id = resultado["entidad"]["id"]
        cleaner.registrar("cotizacion", cotizacion_id)

        ver = client.get(f"/api/v1/cotizacion/{cotizacion_id}", headers=ADMIN_HEADERS)
        assert ver.status_code == 200
        assert ver.json()["cliente_id"] == cli["id"]

        actualizar = {
            "operacion_id": str(op_update),
            "tipo": "cotizacion.actualizar",
            "payload": {"cotizacion_id": cotizacion_id, "observaciones": "editada offline"},
        }
        assert _push(client, [actualizar]).json()["resultados"][0]["estado"] == "ok"
        assert client.get(f"/api/v1/cotizacion/{cotizacion_id}", headers=ADMIN_HEADERS).json()["observaciones"] == "editada offline"

        eliminar = {
            "operacion_id": str(op_delete),
            "tipo": "cotizacion.eliminar",
            "payload": {"cotizacion_id": cotizacion_id},
        }
        assert _push(client, [eliminar]).json()["resultados"][0]["estado"] == "ok"
        assert client.get(f"/api/v1/cotizacion/{cotizacion_id}", headers=ADMIN_HEADERS).status_code == 404
    finally:
        _borrar_operaciones(db, [op_crear, op_update, op_delete])


def test_push_pedido_actualizar(client, db, cleaner):
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100_000.0)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 100_000.0}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])

    op_id = uuid.uuid4()
    try:
        op = {
            "operacion_id": str(op_id),
            "tipo": "pedido.actualizar",
            "payload": {"pedido_id": pedido["id"], "observaciones": "nota capturada offline"},
        }
        resultado = _push(client, [op]).json()["resultados"][0]
        assert resultado["estado"] == "ok", resultado
        ver = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
        assert ver.json()["observaciones"] == "nota capturada offline"
    finally:
        _borrar_operaciones(db, [op_id])
