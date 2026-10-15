"""
Alcance del módulo Producción: el tablero del taller es COMPARTIDO.

Cualquier usuario con acceso al módulo Producción ve TODAS las órdenes (no
solo las que él creó); con `gestionar=True` además opera sobre ellas. Un rol
sin el módulo queda fuera del endpoint (403) y conserva el alcance por creador
en el resto del sistema.
"""
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _firmar_token,
    crear_cliente,
    crear_cotizacion,
    crear_orden_desde_pedido,
    crear_producto,
    registrar_venta_de_pedido,
)


def _crear_usuario_con_modulos(db, cleaner, nombre, modulos):
    """Crea (vía SQL) un usuario no-super con los módulos indicados
    [(clave, gestionar), ...] y devuelve sus headers firmados."""
    rol_id = db.execute(text(
        "INSERT INTO rol (nombre, descripcion, activo) VALUES (:n, 'Rol test produccion', true) RETURNING id"
    ), {"n": f"ROL_{nombre}"}).scalar()
    ids_rm = []
    for modulo, gestionar in modulos:
        ids_rm.append(db.execute(text(
            "INSERT INTO rol_modulo (rol_id, modulo, gestionar) VALUES (:r, :m, :g) RETURNING id"
        ), {"r": rol_id, "m": modulo, "g": gestionar}).scalar())
    uid = db.execute(text(
        "INSERT INTO usuario (nombre_usuario, email, password_hash, activo) "
        "VALUES (:u, NULL, 'e2e', true) RETURNING id"
    ), {"u": nombre}).scalar()
    urid = db.execute(text(
        "INSERT INTO usuario_rol (usuario_id, rol_id) VALUES (:u, :r) RETURNING id"
    ), {"u": uid, "r": rol_id}).scalar()
    db.commit()
    cleaner.registrar("usuario", uid)
    cleaner.registrar("usuario_rol", urid)
    for rm in ids_rm:
        cleaner.registrar("rol_modulo", rm)
    cleaner.registrar("rol", rol_id)
    return {"Authorization": f"Bearer {_firmar_token(nombre)}"}


def _pedido_con_orden(client, cleaner) -> dict:
    """Pedido de jackson (Dueño) con su orden de producción auto-creada."""
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


def _crear_etapa(client, orden_id, headers):
    return client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden_id, "area_id": 1,
        "empleado_responsable_id": 3, "estado": "ASIGNADA",
    }, headers=headers)


def test_produccion_alcance_compartido(client, db, cleaner):
    """Con el módulo Producción se VE y GESTIONA la orden de otro usuario."""
    orden = _pedido_con_orden(client, cleaner)
    headers = _crear_usuario_con_modulos(db, cleaner, "prod_comp", [("produccion", True)])

    # Ve la orden (creada por jackson) y aparece en el listado del Kanban.
    r = client.get(f"/api/v1/produccion/orden/{orden['id']}", headers=headers)
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/produccion/orden", params={"limite": 500}, headers=headers)
    assert r.status_code == 200, r.text
    assert any(o["id"] == orden["id"] for o in r.json()), (
        "el Kanban de producción debe ser compartido para quienes tienen el módulo"
    )

    # Gestiona sobre la orden de jackson: crea una etapa.
    r = _crear_etapa(client, orden["id"], headers)
    assert r.status_code == 201, r.text
    cleaner.registrar("etapa_produccion", r.json()["id"])


def test_produccion_solo_lectura_ve_pero_no_gestiona(client, db, cleaner):
    """Con el módulo en solo lectura se VE la orden, pero no se opera."""
    orden = _pedido_con_orden(client, cleaner)
    headers = _crear_usuario_con_modulos(db, cleaner, "prod_ver", [("produccion", False)])

    r = client.get(f"/api/v1/produccion/orden/{orden['id']}", headers=headers)
    assert r.status_code == 200, r.text

    r = _crear_etapa(client, orden["id"], headers)
    assert r.status_code == 403


def test_produccion_sin_modulo_no_entra(client, db, cleaner):
    """Sin el módulo Producción el endpoint queda cerrado (403)."""
    orden = _pedido_con_orden(client, cleaner)
    headers = _crear_usuario_con_modulos(db, cleaner, "prod_sin", [])

    r = client.get(f"/api/v1/produccion/orden/{orden['id']}", headers=headers)
    assert r.status_code == 403
