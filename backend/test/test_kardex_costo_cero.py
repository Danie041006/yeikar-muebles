"""Kardex con movimientos históricos de costo 0 (carga inicial de Excel).

Regresión: MovimientoResponse heredaba las validaciones del schema de entrada
(costo_unitario gt=0), así que un material con una carga inicial
(`costo_unitario = 0`) devolvía 500 en el kardex y la UI mostraba
"No se registran movimientos".
"""
from decimal import Decimal

from conftest import ADMIN_HEADERS, crear_material
from app.db.session import session_local
from app.modules.inventory.model import MovimientoInventario, MovimientoProductoInventario


def test_kardex_material_con_carga_inicial_costo_cero(client, cleaner):
    mat = crear_material(client, cleaner)

    db = session_local()
    mov = MovimientoInventario(
        material_id=mat["id"],
        ubicacion_id=1,
        tipo="ENTRADA",
        cantidad=Decimal("1"),
        costo_unitario=Decimal("0.00"),
        referencia_tipo="CARGA_INICIAL",
        observaciones="Carga inicial de inventario (Excel)",
    )
    db.add(mov)
    db.commit()
    db.refresh(mov)
    db.close()
    cleaner.registrar("movimiento_inventario", mov.id)

    r = client.get(f"/api/v1/inventario/movimientos/material/{mat['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    ids = [m["id"] for m in r.json()]
    assert mov.id in ids
    carga = next(m for m in r.json() if m["id"] == mov.id)
    assert float(carga["costo_unitario"]) == 0
    assert carga["referencia_tipo"] == "CARGA_INICIAL"


def test_kardex_producto_con_carga_inicial_costo_cero(client, cleaner):
    r = client.post("/api/v1/producto/", json={
        "nombre": "TEST KARDEX COSTO CERO",
        "tipo_producto_id": 2,
        "es_reventa": True,
        "moneda_id": 2,
        "activo": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    prod = r.json()
    cleaner.registrar("producto", prod["id"])

    db = session_local()
    mov = MovimientoProductoInventario(
        producto_id=prod["id"],
        ubicacion_id=1,
        tipo="ENTRADA",
        cantidad=Decimal("2"),
        costo_unitario=Decimal("0.00"),
        referencia_tipo="CARGA_INICIAL",
    )
    db.add(mov)
    db.commit()
    db.refresh(mov)
    db.close()
    cleaner.registrar("movimiento_producto_inventario", mov.id)

    r = client.get(f"/api/v1/inventario/movimientos/producto/{prod['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert mov.id in [m["id"] for m in r.json()]
