"""F0 de sincronización offline: bitácora de cambios (triggers + tombstones),
push idempotente y handlers reales.

Ejecutar: pytest test/test_sync_offline.py -v
"""
import uuid

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_orden_desde_pedido,
    crear_producto,
    registrar_venta_de_pedido,
)
from app.modules.sync.handlers import HANDLERS, SyncConflicto


def _ultimo_cambio(db, tabla, pk, op=None):
    sql = "SELECT id FROM sync_cambio WHERE tabla = :t AND pk = :p"
    params = {"t": tabla, "p": str(pk)}
    if op is not None:
        sql += " AND op = :o"
        params["o"] = op
    sql += " ORDER BY id DESC LIMIT 1"
    db.expire_all()
    return db.execute(text(sql), params).fetchone()


def _push(client, operaciones):
    return client.post("/api/v1/sync/push", json={"operaciones": operaciones}, headers=ADMIN_HEADERS)


def _borrar_operaciones(db, ids):
    db.execute(text("DELETE FROM sync_operacion WHERE operacion_id = ANY(:ids)"), {"ids": [str(i) for i in ids]})
    db.commit()


def _pedido_con_orden(client, cleaner) -> dict:
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
    return crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])


# ---------------------------------------------------------------------------
# Triggers: I/U/D y cascadas
# ---------------------------------------------------------------------------
def test_trigger_registra_insert_update_delete(client, db, cleaner):
    cli = crear_cliente(client, cleaner)
    assert _ultimo_cambio(db, "cliente", cli["id"], "I"), "falta el insert en sync_cambio"

    r = client.put(
        f"/api/v1/cliente/{cli['id']}",
        json={"nombre": cli["nombre"] + " editado", "telefono": "555-9999"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    assert _ultimo_cambio(db, "cliente", cli["id"], "U"), "falta el update en sync_cambio"

    r = client.delete(f"/api/v1/cliente/{cli['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 204, r.text
    assert _ultimo_cambio(db, "cliente", cli["id"], "D"), "falta el tombstone del delete"


def test_trigger_registra_borrado_en_cascada(client, db, cleaner):
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 50_000.0)

    detalle_ids = [
        r[0] for r in db.execute(
            text("SELECT id FROM detalle_cotizacion WHERE cotizacion_id = :c"), {"c": cot["id"]}
        ).fetchall()
    ]
    assert detalle_ids, "la cotización no generó detalles"

    r = client.delete(f"/api/v1/cotizacion/{cot['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 204, r.text
    for detalle_id in detalle_ids:
        assert _ultimo_cambio(db, "detalle_cotizacion", detalle_id, "D"), (
            f"la cascada no dejó tombstone del detalle #{detalle_id}"
        )


# ---------------------------------------------------------------------------
# Push: idempotencia, conflictos y errores
# ---------------------------------------------------------------------------
def test_push_idempotente_no_duplica_efectos(client, db):
    llamadas = []

    def _eco(db_s, payload, usuario):
        llamadas.append(payload["n"])
        return {"detalle": f"eco {payload['n']}"}

    HANDLERS["test.eco"] = _eco
    op_id = uuid.uuid4()
    try:
        op = {"operacion_id": str(op_id), "tipo": "test.eco", "payload": {"n": 7}}
        r1 = _push(client, [op])
        r2 = _push(client, [op])
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert r1.json()["resultados"][0]["estado"] == "ok"
        assert r2.json()["resultados"][0] == r1.json()["resultados"][0]
        assert llamadas == [7], "el reintento volvió a ejecutar el handler"
    finally:
        HANDLERS.pop("test.eco", None)
        _borrar_operaciones(db, [op_id])


def test_push_conflicto_se_reporta_y_es_idempotente(client, db):
    def _choca(db_s, payload, usuario):
        raise SyncConflicto("el estado del servidor cambió")

    HANDLERS["test.choca"] = _choca
    op_id = uuid.uuid4()
    try:
        op = {"operacion_id": str(op_id), "tipo": "test.choca", "payload": {}}
        r1 = _push(client, [op])
        r2 = _push(client, [op])
        assert r1.json()["resultados"][0]["estado"] == "conflicto"
        assert r2.json()["resultados"][0] == r1.json()["resultados"][0]
    finally:
        HANDLERS.pop("test.choca", None)
        _borrar_operaciones(db, [op_id])


def test_push_tipo_desconocido(client, db):
    op_id = uuid.uuid4()
    try:
        r = _push(client, [{"operacion_id": str(op_id), "tipo": "no.existe", "payload": {}}])
        assert r.status_code == 200, r.text
        resultado = r.json()["resultados"][0]
        assert resultado["estado"] == "error"
        r2 = _push(client, [{"operacion_id": str(op_id), "tipo": "no.existe", "payload": {}}])
        assert r2.json()["resultados"][0] == resultado
    finally:
        _borrar_operaciones(db, [op_id])


def test_push_handler_real_etapa_produccion(client, db, cleaner):
    orden = _pedido_con_orden(client, cleaner)
    r = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"],
        "area_id": 1,
        "empleado_responsable_id": 3,
        "estado": "ASIGNADA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    etapa = r.json()
    cleaner.registrar("etapa_produccion", etapa["id"])

    op_id = uuid.uuid4()
    try:
        op = {
            "operacion_id": str(op_id),
            "tipo": "produccion.etapa.estado",
            "payload": {"etapa_id": etapa["id"], "estado": "EN_PROCESO"},
        }
        r = _push(client, [op])
        resultado = r.json()["resultados"][0]
        assert resultado["estado"] == "ok", resultado
        assert resultado["entidad"]["tabla"] == "etapa_produccion"

        ver = client.get(f"/api/v1/produccion/etapa/{etapa['id']}", headers=ADMIN_HEADERS)
        assert ver.json()["estado"] == "EN_PROCESO"

        r2 = _push(client, [op])
        assert r2.json()["resultados"][0] == resultado
    finally:
        _borrar_operaciones(db, [op_id])


# ---------------------------------------------------------------------------
# Cambios y estado
# ---------------------------------------------------------------------------
def test_cambios_paginados_y_estado(client, db, cleaner):
    cli = crear_cliente(client, cleaner)

    r = client.get("/api/v1/sync/cambios", params={"desde": 0, "limite": 1}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    pagina = r.json()
    assert len(pagina["cambios"]) == 1
    assert pagina["hay_mas"] is True
    assert pagina["cursor"] == pagina["cambios"][0]["cursor"]

    visto = False
    desde = 0
    for _ in range(50):
        r = client.get("/api/v1/sync/cambios", params={"desde": desde, "limite": 2000}, headers=ADMIN_HEADERS)
        cuerpo = r.json()
        if any(c["tabla"] == "cliente" and c["pk"] == str(cli["id"]) and c["op"] == "I" for c in cuerpo["cambios"]):
            visto = True
            break
        if not cuerpo["hay_mas"]:
            break
        desde = cuerpo["cursor"]
    assert visto, "el cambio del cliente no apareció en la bitácora"

    r = client.get("/api/v1/sync/estado", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json()["cursor"] >= pagina["cursor"]
