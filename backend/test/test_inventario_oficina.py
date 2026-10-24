"""Inventario de oficina: departamento OFICINA, consumo y conteo físico.

Los ítems de oficina son materiales normales (kardex, stock, alertas y libro
compartidos) con `departamento='OFICINA'`. La salida rápida guarda
`consumido_por` y el conteo físico puede dejar el stock en 0 con un AJUSTE.

Ejecutar:  pytest test/test_inventario_oficina.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import timedelta

from sqlalchemy import text

from conftest import ADMIN_HEADERS, _uniq, crear_material
from app.core.hora_ve import hoy_ve


def _crear_material_oficina(client, cleaner):
    r = client.post("/api/v1/material/", json={
        "nombre": _uniq("oficina"),
        "unidad_medida_id": 2,
        "costo_base": 500,
        "stock_minimo": 3,
        "departamento": "OFICINA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    mat = r.json()
    cleaner.registrar("material", mat["id"])
    return mat


def _registrar_inventario(db, cleaner, material_id):
    for (mid,) in db.execute(text(
        "SELECT id FROM movimiento_inventario WHERE material_id = :m"
    ), {"m": material_id}).fetchall():
        cleaner.registrar("movimiento_inventario", int(mid))
    for (iid,) in db.execute(text(
        "SELECT id FROM inventario WHERE material_id = :m"
    ), {"m": material_id}).fetchall():
        cleaner.registrar("inventario", int(iid))


def test_material_oficina_entrada_y_salida_con_consumido_por(client, cleaner, db):
    mat = _crear_material_oficina(client, cleaner)
    assert mat["departamento"] == "OFICINA"

    # Entrada de papelería: 10 resmas.
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "tipo": "ENTRADA",
        "cantidad": 10,
        "costo_unitario": 500,
        "departamento": "OFICINA",
        "proveedor_nombre": "PAPELERIA TEST",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text

    # Salida rápida: consumió la oficina / recepción.
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "tipo": "SALIDA",
        "cantidad": 4,
        "departamento": "OFICINA",
        "consumido_por": "Recepción",
        "referencia_tipo": "CONSUMO_OFICINA",
        "observaciones": "Reposición de impresora",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    assert mov["consumido_por"] == "Recepción"
    _registrar_inventario(db, cleaner, mat["id"])

    r = client.get(f"/api/v1/inventario/movimientos/material/{mat['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    kardex = r.json()
    salida = next(m for m in kardex if m["id"] == mov["id"])
    assert salida["tipo"] == "SALIDA"
    assert salida["consumido_por"] == "Recepción"
    assert salida["referencia_tipo"] == "CONSUMO_OFICINA"


def test_conteo_fisico_oficina_permite_ajuste_cero(client, cleaner, db):
    mat = _crear_material_oficina(client, cleaner)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 500,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text

    # Conteo físico: no queda ninguna unidad.
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "tipo": "AJUSTE",
        "cantidad": 0,
        "referencia_tipo": "CONTEO_OFICINA",
        "observaciones": "Conteo físico de oficina",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    _registrar_inventario(db, cleaner, mat["id"])
    assert float(r.json()["cantidad"]) == 0.0

    # Una SALIDA en 0 sí se rechaza.
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "tipo": "SALIDA",
        "cantidad": 0,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text


def test_libro_muestra_zona_oficina(client, cleaner, db):
    mat = _crear_material_oficina(client, cleaner)
    hoy = hoy_ve()
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "tipo": "ENTRADA",
        "cantidad": 1,
        "costo_unitario": 500,
        "departamento": "OFICINA",
        "fecha": hoy.isoformat(),
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    _registrar_inventario(db, cleaner, mat["id"])

    r = client.get("/api/v1/inventario/libro", params={
        "desde": (hoy - timedelta(days=1)).isoformat(),
        "hasta": hoy.isoformat(),
        "lado": "ENTRADAS",
        "tipo_item": "MATERIAL",
        "zona": "OFICINA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    libro = r.json()
    assert any(f["item_id"] == mat["id"] and f["zona"] == "OFICINA" for f in libro["filas"])
    assert any(z["zona"] == "OFICINA" and z["label"] == "Oficina" for z in libro["resumen"]["por_zona"])

    # La salida lleva "consumido_por" y también sale en el libro de SALIDAS.
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "tipo": "SALIDA",
        "cantidad": 1,
        "departamento": "OFICINA",
        "consumido_por": "Contabilidad",
        "fecha": hoy.isoformat(),
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    _registrar_inventario(db, cleaner, mat["id"])

    r = client.get("/api/v1/inventario/libro", params={
        "desde": (hoy - timedelta(days=1)).isoformat(),
        "hasta": hoy.isoformat(),
        "lado": "SALIDAS",
        "tipo_item": "MATERIAL",
        "zona": "OFICINA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    salida = next(f for f in r.json()["filas"] if f["item_id"] == mat["id"])
    assert salida["consumido_por"] == "Contabilidad"


def test_compra_oficina_se_clasifica_como_papeleria(client, cleaner, db):
    cuenta = db.execute(text("SELECT id FROM metodo_caja ORDER BY id LIMIT 1")).scalar()
    if cuenta is None:
        import pytest
        pytest.skip("No hay cuentas de caja en la BD de pruebas")

    mat = _crear_material_oficina(client, cleaner)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 500,
        "departamento": "OFICINA",
        "pagado_desde_metodo_caja_id": int(cuenta),
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    _registrar_inventario(db, cleaner, mat["id"])

    gasto = db.execute(text("""
        SELECT g.id, tg.nombre
        FROM gasto g
        JOIN tipo_gasto tg ON tg.id = g.tipo_gasto_id
        WHERE g.descripcion LIKE :pat
        ORDER BY g.id DESC LIMIT 1
    """), {"pat": f"%{mat['nombre']}%"}).fetchone()
    assert gasto is not None, "La compra de oficina debe generar gasto"
    gid, tipo = gasto
    cleaner.registrar("gasto", gid)
    cleaner.registrar_caja_ref(f"Gasto #{gid}")
    assert tipo == "PAPELERIA DE OFICINA", tipo
