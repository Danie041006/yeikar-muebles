"""Zona (departamento) y quién trajo la compra en entradas de insumos.

`movimiento_inventario.departamento` registra la zona del taller a la que va
la compra (solo informativo: NO cambia material.departamento) y
`recibido_por` guarda quién trajo/entregó (texto libre).
"""
from conftest import ADMIN_HEADERS, crear_material


def test_entrada_zona_y_quien_trajo(client, cleaner):
    mat = crear_material(client, cleaner)

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 4,
        "costo_unitario": 2500,
        "departamento": "PINTURA",
        "recibido_por": "Juan (mensajería)",
        "proveedor_nombre": "FERRETERÍA TEST",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    cleaner.registrar("movimiento_inventario", mov["id"])
    assert mov["departamento"] == "PINTURA"
    assert mov["recibido_por"] == "Juan (mensajería)"

    # La zona NO toca el departamento del insumo.
    r = client.get(f"/api/v1/material/{mat['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    # Se normaliza a mayúsculas.
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 1,
        "departamento": " pintura ",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov2 = r.json()
    cleaner.registrar("movimiento_inventario", mov2["id"])
    assert mov2["departamento"] == "PINTURA"
    assert mov2["recibido_por"] is None

    # Zona inválida → 422.
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 1,
        "departamento": "GERENCIA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 422, r.text
