"""Eliminar insumos SOLO con stock 0.

- Un insumo nuevo, sin stock ni referencias, se borra de verdad.
- Con stock > 0 se rechaza (409).
- Con historial (entradas/salidas) y stock 0 se desactiva: desaparece del
  catálogo/selectores pero el kardex queda intacto.
- Si está en la receta de un producto se rechaza (409).

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_eliminar_material_stock_cero.py -v
"""
from conftest import (
    ADMIN_HEADERS,
    crear_material,
    crear_movimiento,
)


def test_eliminar_material_sin_stock_sin_referencias(client, cleaner):
    mat = crear_material(client, cleaner, nombre="TEST BORRAR INSUMO LIMPIO")
    r = client.delete(f"/api/v1/material/{mat['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 204, r.text
    r = client.get(f"/api/v1/material/{mat['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 404


def test_eliminar_material_con_stock_es_409(client, cleaner):
    mat = crear_material(client, cleaner, nombre="TEST BORRAR INSUMO CON STOCK")
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", 5)
    r = client.delete(f"/api/v1/material/{mat['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 409, r.text
    assert "stock" in r.json()["detail"].lower()


def test_eliminar_material_stock_cero_con_historial_lo_desactiva(client, cleaner):
    mat = crear_material(client, cleaner, nombre="TEST BORRAR INSUMO CON HISTORIAL")
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", 5)
    crear_movimiento(client, cleaner, mat["id"], "SALIDA", 5)

    r = client.delete(f"/api/v1/material/{mat['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 204, r.text

    # El registro sigue existiendo (historial intacto) pero inactivo.
    r = client.get(f"/api/v1/material/{mat['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json()["activo"] is False

    # Y ya no aparece en el catálogo normal.
    r = client.get(
        "/api/v1/material/",
        params={"buscar": "TEST BORRAR INSUMO CON HISTORIAL", "limite": 50},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200
    assert all(m["id"] != mat["id"] for m in r.json())
