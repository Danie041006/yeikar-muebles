"""
Alcance de cotizaciones: TODOS con el módulo pueden VER todas las
cotizaciones (lectura compartida), pero solo su autor (o un rol de alcance
total: Dueño/Administrador) puede MODIFICARLAS: editar, cambiar estado,
eliminar o convertir a pedido.
"""
from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente, crear_cotizacion, crear_producto, _firmar_token


def crear_usuario_cotizador(db, cleaner, nombre, con_clientes=False):
    """Crea (vía SQL) un usuario no-super con módulos cotizaciones + pedidos
    (gestionar) y devuelve sus headers firmados. Registra todo en el cleaner."""
    rol_id = db.execute(text(
        "INSERT INTO rol (nombre, descripcion, activo) VALUES (:n, 'Rol test alcance', true) RETURNING id"
    ), {"n": f"ROL_{nombre}"}).scalar()
    rmid = db.execute(text(
        "INSERT INTO rol_modulo (rol_id, modulo, gestionar) VALUES (:r, 'cotizaciones', true) RETURNING id"
    ), {"r": rol_id}).scalar()
    rmid2 = db.execute(text(
        "INSERT INTO rol_modulo (rol_id, modulo, gestionar) VALUES (:r, 'pedidos', true) RETURNING id"
    ), {"r": rol_id}).scalar()
    ids_rm = [rmid, rmid2]
    if con_clientes:
        ids_rm.append(db.execute(text(
            "INSERT INTO rol_modulo (rol_id, modulo, gestionar) VALUES (:r, 'clientes', true) RETURNING id"
        ), {"r": rol_id}).scalar())
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


def detalles_de(cotizacion) -> list:
    """Replica los detalles de la cotización tal cual (para convertir)."""
    return [
        {
            "producto_id": d["producto_id"],
            "tipo_item": d.get("tipo_item") or "FABRICADO",
            "cantidad": d["cantidad"],
            "precio": d["precio"],
            "ancho": d.get("ancho"),
            "largo": d.get("largo"),
        }
        for d in cotizacion["detalles"]
    ]


def test_cotizaciones_lectura_compartida_escritura_solo_autor(client, db, cleaner):
    headers_a = crear_usuario_cotizador(db, cleaner, "alcance_a")
    headers_b = crear_usuario_cotizador(db, cleaner, "alcance_b")
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)

    # A crea la cotización (autor: A).
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], 100000.0,
                           estado="ENVIADA", headers=headers_a)
    cot_id = cot["id"]

    # B VE la cotización de A: en el listado y en el detalle.
    r = client.get("/api/v1/cotizacion/", params={"solo_mes_actual": False, "limite": 1000}, headers=headers_b)
    assert r.status_code == 200
    assert any(q["id"] == cot_id for q in r.json()), "B debe ver las cotizaciones de otros"
    r = client.get(f"/api/v1/cotizacion/{cot_id}", headers=headers_b)
    assert r.status_code == 200

    # B NO puede EDITAR la cotización de A.
    r = client.put(f"/api/v1/cotizacion/{cot_id}", json={
        "cliente_id": cliente["id"], "fecha": cot["fecha"],
        "estado": "APROBADA", "total_estimado": 100000.0,
        "observaciones": "intento de edición",
    }, headers=headers_b)
    assert r.status_code == 400
    assert "otro usuario" in r.json()["detail"]

    # B NO puede ELIMINARLA.
    r = client.delete(f"/api/v1/cotizacion/{cot_id}", headers=headers_b)
    assert r.status_code == 400
    assert "otro usuario" in r.json()["detail"]

    # B NO puede CONVERTIRLA a pedido.
    r = client.post(f"/api/v1/pedido/convertir/{cot_id}", json={
        "detalles": detalles_de(cot),
    }, headers=headers_b)
    assert r.status_code == 400
    assert "otro usuario" in r.json()["detail"]

    # A sí puede EDITAR su cotización.
    r = client.put(f"/api/v1/cotizacion/{cot_id}", json={
        "cliente_id": cliente["id"], "fecha": cot["fecha"],
        "estado": "APROBADA", "total_estimado": 100000.0,
        "observaciones": "editada por su autor",
    }, headers=headers_a)
    assert r.status_code == 200
    assert r.json()["observaciones"] == "editada por su autor"

    # Un rol de alcance total (Dueño) también puede editar la de A.
    r = client.put(f"/api/v1/cotizacion/{cot_id}", json={
        "cliente_id": cliente["id"], "fecha": cot["fecha"],
        "estado": "APROBADA", "total_estimado": 100000.0,
        "observaciones": "editada por admin",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json()["observaciones"] == "editada por admin"


def test_editar_cotizacion_reemplaza_renglones(client, db, cleaner):
    """Editar desde la UI envía los detalles completos: los renglones quedan
    exactamente como se guardaron (precio, cantidad y costos), no se acumulan."""
    headers_a = crear_usuario_cotizador(db, cleaner, "alcance_edit")
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], 100000.0,
                           estado="BORRADOR", headers=headers_a)

    r = client.put(f"/api/v1/cotizacion/{cot['id']}", json={
        "cliente_id": cliente["id"],
        "fecha": cot["fecha"],
        "estado": "BORRADOR",
        "total_estimado": 240000.0,
        "observaciones": "renglón editado",
        "detalles": [
            {
                "producto_id": producto["id"],
                "tipo_item": "FABRICADO",
                "cantidad": 2,
                "precio": 120000.0,
                "ancho": 1.6,
                "largo": 1.9,
                "costo_materiales": 10000.0,
                "costo_mano_obra": 5000.0,
                "costo_gastos": 2000.0,
                "costo_total": 17000.0,
            }
        ],
    }, headers=headers_a)
    assert r.status_code == 200, r.text
    detalles = r.json()["detalles"]
    assert len(detalles) == 1, "los renglones deben reemplazarse, no acumularse"
    assert detalles[0]["precio"] == 120000.0
    assert detalles[0]["cantidad"] == 2
    assert detalles[0]["costo_total"] == 17000.0


def test_cliente_rapido_sin_modulo_clientes(client, db, cleaner):
    """Crear cliente desde la cotización NO exige el módulo clientes (caso
    Andrea: cotizaciones sin clientes). Si el teléfono ya existe, devuelve el
    cliente actual en vez de duplicar."""
    headers = crear_usuario_cotizador(db, cleaner, "rapido_cliente")  # sin clientes

    r = client.post("/api/v1/cotizacion/cliente-rapido", json={
        "nombre": "CLIENTE RAPIDO", "telefono": "0412-9999999",
    }, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    cleaner.registrar("cliente", body["id"])
    assert body["nombre"] == "CLIENTE RAPIDO"

    # Mismo teléfono → mismo cliente, no se duplica.
    r2 = client.post("/api/v1/cotizacion/cliente-rapido", json={
        "nombre": "OTRO NOMBRE", "telefono": "0412-9999999",
    }, headers=headers)
    assert r2.status_code == 201
    assert r2.json()["id"] == body["id"]

    # Validaciones mínimas (nombre vacío → 422 del schema, teléfono vacío → 400).
    r = client.post("/api/v1/cotizacion/cliente-rapido", json={
        "nombre": "", "telefono": "0412-0000000",
    }, headers=headers)
    assert r.status_code == 422
    r = client.post("/api/v1/cotizacion/cliente-rapido", json={
        "nombre": "SIN TELEFONO", "telefono": "   ",
    }, headers=headers)
    assert r.status_code == 400

    # El usuario recién creado puede cotizar con el cliente.
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, body["id"], producto["id"], 100000.0, headers=headers)
    assert cot["cliente_id"] == body["id"]


def test_cliente_rapido_exige_cotizaciones(client, db, cleaner):
    """Un rol sin el módulo cotizaciones no puede usar el endpoint."""
    rol_id = db.execute(text(
        "INSERT INTO rol (nombre, descripcion, activo) VALUES (:n, 'Rol sin modulos', true) RETURNING id"
    ), {"n": "ROL_sin_modulos"}).scalar()
    uid = db.execute(text(
        "INSERT INTO usuario (nombre_usuario, email, password_hash, activo) "
        "VALUES ('sin_modulos', NULL, 'e2e', true) RETURNING id"
    )).scalar()
    urid = db.execute(text(
        "INSERT INTO usuario_rol (usuario_id, rol_id) VALUES (:u, :r) RETURNING id"
    ), {"u": uid, "r": rol_id}).scalar()
    db.commit()
    cleaner.registrar("usuario", uid)
    cleaner.registrar("usuario_rol", urid)
    cleaner.registrar("rol", rol_id)
    headers = {"Authorization": f"Bearer {_firmar_token('sin_modulos')}"}

    r = client.post("/api/v1/cotizacion/cliente-rapido", json={
        "nombre": "X", "telefono": "0412-1111111",
    }, headers=headers)
    assert r.status_code == 403