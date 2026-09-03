"""Proveedor/cliente en los movimientos de inventario como TEXTO LIBRE.

Se puede escribir el nombre sin que exista un registro del catálogo: queda
guardado en el movimiento. Si el nombre coincide con un proveedor/cliente
existente, además se linkea el id (mejor trazabilidad).
"""
from conftest import ADMIN_HEADERS, crear_material, crear_proveedor, crear_cliente


def test_movimiento_proveedor_cliente_texto_libre(client, cleaner):
    mat = crear_material(client, cleaner)

    # Proveedor y cliente nuevos (sin registro): se guardan como texto.
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 5,
        "costo_unitario": 1000,
        "proveedor_nombre": "PROVEEDOR NUEVO C.A.",
        "cliente_nombre": "Cliente especial",
        "observaciones": "test texto libre",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    cleaner.registrar("movimiento_inventario", mov["id"])
    assert mov["proveedor_nombre"] == "PROVEEDOR NUEVO C.A."
    assert mov["cliente_nombre"] == "Cliente especial"
    assert mov["proveedor_id"] is None
    assert mov["cliente_id"] is None

    # Mismo nombre pero ahora existe un proveedor/cliente: se linkea el id.
    prov = crear_proveedor(client, cleaner, nombre="PROVEEDOR NUEVO C.A.")
    cli = crear_cliente(client, cleaner, nombre="Cliente especial")
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 900,
        "proveedor_nombre": "PROVEEDOR NUEVO C.A.",
        "cliente_nombre": "Cliente especial",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov2 = r.json()
    cleaner.registrar("movimiento_inventario", mov2["id"])
    assert mov2["proveedor_id"] == prov["id"]
    assert mov2["cliente_id"] == cli["id"]
    assert mov2["proveedor_nombre"] == "PROVEEDOR NUEVO C.A."


def test_movimiento_producto_proveedor_cliente_texto_libre(client, cleaner):
    r = client.post("/api/v1/producto/", json={
        "nombre": "TEST REVENTA LIBRE",
        "tipo_producto_id": 2,
        "es_reventa": True,
        "moneda_id": 2,
        "activo": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    prod = r.json()
    cleaner.registrar("producto", prod["id"])

    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": prod["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 3,
        "costo_unitario": 250,
        "proveedor_nombre": "DISTRIBUIDORA DE COLCHONES",
        "cliente_nombre": "Cliente showroom",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    cleaner.registrar("movimiento_producto_inventario", mov["id"])
    assert mov["proveedor_nombre"] == "DISTRIBUIDORA DE COLCHONES"
    assert mov["cliente_nombre"] == "Cliente showroom"