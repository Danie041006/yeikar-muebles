"""
test_llevada.py
===============
"La llevada" (flete/aduana) en entradas de inventario:
  - Insumo: ENTRADA pagada desde una cuenta con llevada → gasto aparte
    "FLETE / LLEVADA DE INSUMO" + segunda salida de esa caja.
  - Reventa: idem con "FLETE / LLEVADA REVENTA".
  - Opcional: sin llevada no se genera ningún gasto extra.

Ejecutar:  pytest test/test_llevada.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from conftest import ADMIN_HEADERS, _uniq, crear_material
from sqlalchemy import text


def _cuenta_id(db):
    """Una cuenta de caja existente (usa la primera que encuentre)."""
    row = db.execute(text(
        "SELECT m.id FROM metodo_caja m ORDER BY m.id LIMIT 1"
    )).fetchone()
    return int(row[0]) if row else None


def _gastos_llevada(db, desc_like):
    rows = db.execute(text(
        "SELECT id, monto, descripcion FROM gasto WHERE descripcion LIKE :pat"
    ), {"pat": f"%{desc_like}%"}).fetchall()
    return rows


def test_entrada_insumo_con_llevada_genera_gasto_aparte(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")

    mat = crear_material(client, cleaner, costo_base=10000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 5,
        "costo_unitario": 10000,
        # "La llevada": se paga además de la compra
        "llevada": 5000,
        "pagado_desde_metodo_caja_id": cuenta,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    assert float(mov["llevada"]) == 5000.0
    from conftest import registrar_inventario_de_material
    registrar_inventario_de_material(db, cleaner, mat["id"])
    cleaner.registrar_gastos_like(db, "Llevada (flete/aduana) de ")
    cleaner.registrar_gastos_like(db, "Compra ")

    # Dos gastos: la compra (50.000) y la llevada (5.000), ambos del material
    gastos = _gastos_llevada(db, mat["nombre"])
    montos = sorted(float(g[1]) for g in gastos)
    assert montos == [5000.0, 50000.0], f"Se esperaban compra 50.000 + llevada 5.000, hay: {montos}"
    assert any("Llevada" in g[2] for g in gastos)


def test_entrada_sin_llevada_no_genera_gasto_extra(client, cleaner, db):
    mat = crear_material(client, cleaner, costo_base=1000.0)
    # Sin cuenta → sin gastos de compra ni de llevada
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 1000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201)
    assert r.json().get("llevada") is None


def test_entrada_reventa_con_llevada(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")

    prod = client.post("/api/v1/producto/", json={
        "nombre": _uniq("reventa"), "tipo_producto_id": 2, "es_reventa": True,
    }, headers=ADMIN_HEADERS).json()
    cleaner.registrar("producto", prod["id"])
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": prod["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 3,
        "costo_unitario": 200000,
        "llevada": 20000,
        "pagado_desde_metodo_caja_id": cuenta,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    assert float(mov["llevada"]) == 20000.0
    # Registrar inventario/movimientos del producto para la limpieza
    for (mid,) in db.execute(text(
        "SELECT id FROM movimiento_producto_inventario WHERE producto_id = :p"
    ), {"p": prod["id"]}).fetchall():
        cleaner.registrar("movimiento_producto_inventario", int(mid))
    for (iid,) in db.execute(text(
        "SELECT id FROM producto_inventario WHERE producto_id = :p"
    ), {"p": prod["id"]}).fetchall():
        cleaner.registrar("producto_inventario", int(iid))
    cleaner.registrar_gastos_like(db, "Llevada (flete/aduana) de reventa")

    llevada = _gastos_llevada(db, "Llevada (flete/aduana) de reventa")
    assert llevada, "Debe existir el gasto FLETE / LLEVADA REVENTA"
    assert float(llevada[0][1]) == 20000.0