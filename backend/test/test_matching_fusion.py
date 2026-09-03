"""
test_matching_fusion.py
=======================
Matching de insumos del Excel contra el catálogo de inventario (MAPEADO /
AMBIGUO / PENDIENTE), preview visual del importador, edición de elementos
(PUT con sinónimos) y fusión de materiales duplicados.

Ejecutar:  pytest test/test_matching_fusion.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from conftest import ADMIN_HEADERS, _uniq, crear_material


# ============================================================================
# Helpers
# ============================================================================

def crear_sinonimo(db, material_id, sinonimo):
    from app.modules.productos.model import MaterialSinonimo
    s = MaterialSinonimo(material_id=material_id, sinonimo=sinonimo)
    db.add(s)
    db.commit()
    return s


# ============================================================================
# 1. Matcher: MAPEADO / AMBIGUO / PENDIENTE
# ============================================================================

def test_matcher_exacto_unico_mapeado(client, cleaner, db):
    from app.modules.productos.estructura_import import resolver_material
    mat = crear_material(client, cleaner, nombre="GRAPAS TEST UNIQUE")
    res = resolver_material(db, "GRAPAS TEST UNIQUE")
    assert res["estado"] == "MAPEADO"
    assert res["material"].id == mat["id"]


def test_matcher_exacto_duplicado_ambiguo(client, cleaner, db):
    from app.modules.productos.estructura_import import resolver_material
    nombre = _uniq("duplicado")
    m1 = crear_material(client, cleaner, nombre=nombre)
    m2 = crear_material(client, cleaner, nombre=nombre)
    res = resolver_material(db, nombre)
    assert res["estado"] == "AMBIGUO"
    assert res["material"] is None
    ids = {c.id for c in res["candidatos"]}
    assert {m1["id"], m2["id"]} <= ids


def test_matcher_sinonimo_mapeado(client, cleaner, db):
    from app.modules.productos.estructura_import import resolver_material
    mat = crear_material(client, cleaner, nombre="TORNILLOS DE 2 PULG")
    crear_sinonimo(db, mat["id"], "TORNILLO 2 PULGADAS")
    res = resolver_material(db, "TORNILLO 2 PULGADAS")
    assert res["estado"] == "MAPEADO"
    assert res["material"].id == mat["id"]


def test_matcher_contiene_unico_mapeado_y_multiple_ambiguo(client, cleaner, db):
    from app.modules.productos.estructura_import import resolver_material
    unica = crear_material(client, cleaner, nombre="TELA UNIQUE EXTRA FINA")
    res = resolver_material(db, "TELA UNIQUE")
    assert res["estado"] == "MAPEADO"
    assert res["material"].id == unica["id"]

    # Dos candidatos distintos que contienen el texto → AMBIGUO
    crear_material(client, cleaner, nombre="TELA UNIQUE RUSTICA")
    res2 = resolver_material(db, "TELA UNIQUE")
    assert res2["estado"] == "AMBIGUO"
    assert len(res2["candidatos"]) >= 2


def test_matcher_inactivos_excluidos_en_contiene(client, cleaner, db):
    from app.modules.productos.estructura_import import resolver_material
    mat = crear_material(client, cleaner, nombre="RESANE TEST OFF")
    r = client.put(f"/api/v1/material/{mat['id']}", json={"activo": False}, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    res = resolver_material(db, "RESANE TEST")
    assert res["estado"] == "PENDIENTE", "Un material inactivo no debe matchear por 'contiene'"


def test_matcher_desconocido_pendiente(client, cleaner, db):
    from app.modules.productos.estructura_import import resolver_material
    res = resolver_material(db, _uniq("inexistente"))
    assert res["estado"] == "PENDIENTE"
    assert res["material"] is None


# ============================================================================
# 2. Preview del importador: estructura visual con estados de matching
# ============================================================================

def test_preview_estructura_con_estados(client, cleaner, db):
    mat = crear_material(client, cleaner, nombre="MADERA PINO TEST", costo_base=140)
    duplicado_a = crear_material(client, cleaner, nombre=_uniq("LAM X"))
    duplicado_b = crear_material(client, cleaner, nombre="MISMO NOMBRE LAM X")
    # renombrar el primero para que ambos coincidan
    r = client.put(f"/api/v1/material/{duplicado_a['id']}", json={"nombre": "MISMO NOMBRE LAM X"},
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200

    texto = (
        "NOMBRE DEL PRODUCTO:  \t\tPRUEBA VISUAL\t\t\t\n"
        "MATERIA PRIMA\t\tUNIDAD DE MEDIDA\t\tV/UNIT\tPRECIO TOTAL\n"
        "MADERA PINO TEST\t1170\tCMS\t\t140.00\t163,800.00\n"
        "MISMO NOMBRE LAM X\t1\tLAMINA\t\t65,000.00\t65,000.00\n"
        "COSA INEXISTENTE XYZ\t1\tund\t\t10,000.00\t10,000.00\n"
        "TOTAL PRODUCCION\t\t\t\t\t238,800.00\n"
    )
    r = client.post("/api/v1/producto/importar-estructura-texto", json={
        "texto": texto, "nombre": "PRUEBA VISUAL", "tipo_producto_id": 1, "dry_run": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    estructura = r.json()["estructura"]
    assert len(estructura) == 1
    filas = {i["nombre"]: i for i in estructura[0]["insumos"]}

    assert filas["MADERA PINO TEST"]["estado"] == "MAPEADO"
    assert filas["MADERA PINO TEST"]["material_id"] == mat["id"]
    assert filas["MADERA PINO TEST"]["total"] == 163800.0

    assert filas["MISMO NOMBRE LAM X"]["estado"] == "AMBIGUO"
    assert len(filas["MISMO NOMBRE LAM X"]["candidatos"]) >= 2

    assert filas["COSA INEXISTENTE XYZ"]["estado"] == "PENDIENTE"

    # Mano de obra / totales en la estructura visual
    assert estructura[0]["total"] == 238800.0


# ============================================================================
# 3. PUT /elemento/{id}: asociar material + registrar sinónimo
# ============================================================================

def test_put_elemento_asocia_y_registra_sinonimo(client, cleaner, db):
    prod = client.post("/api/v1/producto/", json={
        "nombre": _uniq("prod"), "tipo_producto_id": 1,
    }, headers=ADMIN_HEADERS).json()
    cleaner.registrar("producto", prod["id"])

    sec = client.post("/api/v1/seccion/", json={
        "producto_id": prod["id"], "nombre": "EBANISTERÍA",
    }, headers=ADMIN_HEADERS).json()
    cleaner.registrar("seccion_producto", sec["id"])

    el = client.post(f"/api/v1/seccion/{sec['id']}/elemento", json={
        "seccion_id": sec["id"],
        "nombre_insumo_original": "COLBON TEST",
        "cantidad": 3,
    }, headers=ADMIN_HEADERS).json()
    cleaner.registrar("elemento_seccion", el["id"])
    assert el["estado_resolucion"] == "PENDIENTE"

    mat = crear_material(client, cleaner, nombre="COLBON TEST REAL")
    r = client.put(f"/api/v1/elemento/{el['id']}", json={
        "material_id_normalizado": mat["id"],
        "registrar_sinonimo": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado_resolucion"] == "MAPEADO"
    assert body["material_id_normalizado"] == mat["id"]

    # El sinónimo quedó registrado: el matcher ahora lo encuentra exacto
    from app.modules.productos.estructura_import import resolver_material
    res = resolver_material(db, "COLBON TEST")
    assert res["estado"] == "MAPEADO"
    assert res["material"].id == mat["id"]

    # Desasociar → vuelve a PENDIENTE
    r2 = client.put(f"/api/v1/elemento/{el['id']}", json={
        "material_id_normalizado": None,
    }, headers=ADMIN_HEADERS)
    assert r2.status_code == 200
    assert r2.json()["estado_resolucion"] == "PENDIENTE"


# ============================================================================
# 4. Duplicados y fusión de materiales
# ============================================================================

def _preparar_duplicados(client, cleaner, db):
    nombre = _uniq("fusion")
    origen = crear_material(client, cleaner, nombre=nombre, costo_base=1000)
    destino = crear_material(client, cleaner, nombre=nombre, costo_base=5000)

    # Stock: origen 4 y destino 10 en la misma ubicación (se SUMAN) + historial
    r, _ = __import__("conftest").crear_movimiento(client, cleaner, origen["id"], "ENTRADA", 4)
    assert r.status_code in (200, 201)
    r, _ = __import__("conftest").crear_movimiento(client, cleaner, destino["id"], "ENTRADA", 10)
    assert r.status_code in (200, 201)
    # Un movimiento histórico extra del origen (el kardex debe seguir contando)
    r, _ = __import__("conftest").crear_movimiento(client, cleaner, origen["id"], "DAÑO", 1)
    assert r.status_code in (200, 201)

    # Una receta que usa el ORIGEN (producto_material, FK RESTRICT)
    prod = client.post("/api/v1/producto/", json={
        "nombre": _uniq("prod"), "tipo_producto_id": 1,
    }, headers=ADMIN_HEADERS).json()
    cleaner.registrar("producto", prod["id"])
    rec = client.post(f"/api/v1/producto/{prod['id']}/receta", json={
        "producto_id": prod["id"], "material_id": origen["id"],
        "cantidad_base": 2, "tipo_escala": "FIJO", "seccion": "EBANISTERIA",
    }, headers=ADMIN_HEADERS).json()
    cleaner.registrar("producto_material", rec["id"])

    return nombre, origen, destino


def test_detectar_duplicados_agrupa_por_nombre(client, cleaner, db):
    nombre, origen, destino = _preparar_duplicados(client, cleaner, db)
    r = client.get("/api/v1/material/duplicados", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    grupos = {g["nombre"]: g for g in r.json()}
    g = grupos.get(nombre.upper())
    assert g is not None, f"No se detectó el grupo {nombre}: {list(grupos)[:5]}"
    ids = {i["id"] for i in g["items"]}
    assert {origen["id"], destino["id"]} <= ids
    item_origen = next(i for i in g["items"] if i["id"] == origen["id"])
    assert item_origen["stock"] == 3  # 4 entró, 1 se dañó
    assert item_origen["referencias"].get("producto_material") == 1


def test_fusionar_mueve_stock_recetas_kardex_y_elimina_origen(client, cleaner, db):
    from sqlalchemy import text
    nombre, origen, destino = _preparar_duplicados(client, cleaner, db)
    crear_sinonimo(db, origen["id"], "SINONIMO DE ORIGEN")

    r = client.post("/api/v1/material/fusionar", json={
        "material_origen_id": origen["id"],
        "material_destino_id": destino["id"],
        "costo_base": 5000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    # El origen ya no existe
    r_get = client.get(f"/api/v1/material/{origen['id']}", headers=ADMIN_HEADERS)
    assert r_get.status_code == 404

    # Stock SUMADO en el destino: 10 + 4 − 1 (daño) = 13
    row = db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id = :m"
    ), {"m": destino["id"]}).fetchone()
    assert row is not None
    assert float(row[0]) == 13.0

    # El kardex del origen ahora apunta al destino (historial conservado)
    n_movs = db.execute(text(
        "SELECT COUNT(*) FROM movimiento_inventario WHERE material_id = :m"
    ), {"m": destino["id"]}).scalar()
    assert n_movs >= 3

    # La receta apunta al destino
    mat_rec = db.execute(text(
        "SELECT material_id FROM producto_material WHERE id = ("
        "  SELECT id FROM producto_material WHERE material_id = :m LIMIT 1)"
    ), {"m": destino["id"]}).scalar()
    assert mat_rec == destino["id"]

    # El sinónimo sobrevivió, apuntando al destino
    sin = db.execute(text(
        "SELECT material_id FROM material_sinonimo WHERE sinonimo = 'SINONIMO DE ORIGEN'"
    )).fetchone()
    assert sin is not None
    assert sin[0] == destino["id"]


def test_fusionar_requiere_admin(client, cleaner, db):
    from conftest import VENTAS_HEADERS
    nombre, origen, destino = _preparar_duplicados(client, cleaner, db)
    r = client.post("/api/v1/material/fusionar", json={
        "material_origen_id": origen["id"],
        "material_destino_id": destino["id"],
    }, headers=VENTAS_HEADERS)
    assert r.status_code == 403, "Un usuario de ventas no puede fusionar materiales"


def test_fusionar_mismo_material_rechazado(client, cleaner, db):
    mat = crear_material(client, cleaner)
    r = client.post("/api/v1/material/fusionar", json={
        "material_origen_id": mat["id"],
        "material_destino_id": mat["id"],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400
