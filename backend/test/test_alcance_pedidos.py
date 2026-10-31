"""
Alcance del módulo Pedidos: lectura COMPARTIDA, escritura del autor.

Cualquier usuario con el módulo `pedidos` ve TODOS los pedidos (igual que
cotizaciones, ventas y el tablero de producción): Paola necesita abrir el
pedido que registró otra cuenta (p. ej. desde "Ver pedido" en Cotizaciones).
Editar/borrar sigue siendo del autor o de un rol con alcance total.
"""
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _firmar_token,
    crear_cliente,
    crear_cotizacion,
    crear_producto,
    registrar_venta_de_pedido,
)


def _crear_usuario_con_modulos(db, cleaner, nombre, modulos):
    """Crea (vía SQL) un usuario no-super con los módulos indicados
    [(clave, gestionar), ...] y devuelve sus headers firmados."""
    rol_id = db.execute(text(
        "INSERT INTO rol (nombre, descripcion, activo) VALUES (:n, 'Rol test alcance pedidos', true) RETURNING id"
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


def _pedido_de_jackson(client, cleaner) -> dict:
    """Pedido creado por jackson (Dueño) con su venta auto-generada."""
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
    return ped


def test_pedidos_lectura_compartida_escritura_solo_autor(client, db, cleaner):
    """Con el módulo Pedidos se VE el pedido de otro usuario (y su ficha),
    pero editar/borrar sigue siendo solo del autor."""
    ped = _pedido_de_jackson(client, cleaner)
    headers = _crear_usuario_con_modulos(db, cleaner, "ped_gestion", [("pedidos", True)])

    # Se ve en el listado y por id.
    r = client.get("/api/v1/pedido/", params={"limite": 1000}, headers=headers)
    assert r.status_code == 200, r.text
    assert any(o["id"] == ped["id"] for o in r.json()), (
        "el pedido de otro usuario debe aparecer en el listado (lectura compartida)"
    )

    r = client.get(f"/api/v1/pedido/{ped['id']}", headers=headers)
    assert r.status_code == 200, r.text

    r = client.get(f"/api/v1/pedido/{ped['id']}/rentabilidad", headers=headers)
    assert r.status_code == 200, r.text

    # La ficha del historial ("Ver información del Pedido") también abre.
    r = client.get(f"/api/v1/historial/pedido/{ped['id']}", headers=headers)
    assert r.status_code == 200, r.text

    # Mover el pedido ajeno sigue repelido, aunque tenga gestionar=True.
    r = client.put(
        f"/api/v1/pedido/{ped['id']}",
        json={"observaciones": "intento de otro usuario"},
        headers=headers,
    )
    assert r.status_code in (403, 404), r.text

    r = client.delete(f"/api/v1/pedido/{ped['id']}", headers=headers)
    assert r.status_code in (403, 404), r.text


def test_pedidos_sin_modulo_no_entra(client, db, cleaner):
    """Sin el módulo Pedidos el endpoint queda cerrado (403), aunque tenga
    cualquier otro módulo."""
    ped = _pedido_de_jackson(client, cleaner)
    headers = _crear_usuario_con_modulos(db, cleaner, "ped_sin_mod", [("ventas", True)])

    r = client.get(f"/api/v1/pedido/{ped['id']}", headers=headers)
    assert r.status_code == 403, r.text
