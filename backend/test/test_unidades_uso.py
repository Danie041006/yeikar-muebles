"""Unidades de USO de materiales (colbón en cuñete consumido en pistoladas).

El stock y los costos viven SIEMPRE en la unidad base del material. La unidad
de uso (galón, pistolada, litro…) tiene un factor PRÁCTICO por material
(`material_unidad_uso.factor_base`: 1 unidad de uso = factor unidades base) y
el backend convierte con el mismo motor único (production/unidades.py).

Cubre:
  1. Motor: multiplicación por factor y mutex con captura de medidas.
  2. CRUD: PUT reemplaza el set; duplicados y factores inválidos rechazados.
  3. Uso directo en galón → stock/gasto/etiqueta en base, cantidad_uso intacta.
  4. Pedido entregado en galón + confirmación multi-uso (pistoladas + litro).
  5. Validaciones: unidad de otro material, mezcla con pieza, pedido abierto.

Ejecutar:  pytest test/test_unidades_uso.py -v
"""
import os
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_material,
    crear_movimiento,
    registrar_inventario_de_material,
)

from test_cortes_laminas import (
    stock_actual,
    _pedido_con_etapa_en_proceso,
)

from app.modules.production.unidades import resolver_cantidad_consumo, etiqueta_uso


# Base del test: LITRO (unidad 4). Factores de práctica, no teóricos.
GALON = 3.785
PISTOLADA = 0.25


def _material_fake(abrev="L"):
    return SimpleNamespace(unidad_medida=SimpleNamespace(abreviatura=abrev))


def _unidad_uso_fake(nombre="GALÓN", factor=GALON):
    return SimpleNamespace(nombre=nombre, factor_base=Decimal(str(factor)))


# ============================================================================
# 1. Motor puro
# ============================================================================

def test_motor_multiplica_por_factor():
    base = resolver_cantidad_consumo(_material_fake(), 2, unidad_uso=_unidad_uso_fake())
    assert base == Decimal("7.5700")

    base = resolver_cantidad_consumo(
        _material_fake(), Decimal("0.75"), unidad_uso=_unidad_uso_fake("PISTOLADA", PISTOLADA)
    )
    assert base == Decimal("0.1875")


def test_motor_unidad_uso_excluyente_con_pieza_y_captura():
    try:
        resolver_cantidad_consumo(
            _material_fake("m3"), 2, pieza_largo=2, pieza_ancho=10, pieza_espesor=5,
            unidad_uso=_unidad_uso_fake(),
        )
        assert False, "debía rechazar la mezcla"
    except ValueError as e:
        assert "no ambas" in str(e)

    try:
        resolver_cantidad_consumo(_material_fake(), 2, "CM", unidad_uso=_unidad_uso_fake())
        assert False, "debía rechazar la mezcla"
    except ValueError as e:
        assert "no ambas" in str(e)


def test_etiqueta_uso_con_equivalencia():
    etiqueta = etiqueta_uso(0.75, unidad_uso=_unidad_uso_fake("PISTOLADA", PISTOLADA), base_abrev="L")
    assert etiqueta == "0.75 PISTOLADA (= 0.1875 L)"


# ============================================================================
# 2. CRUD de unidades de uso
# ============================================================================

def test_crud_unidades_uso(client, cleaner):
    mat = crear_material(client, cleaner, unidad_medida_id=4)

    r = client.put(
        f"/api/v1/material/{mat['id']}/unidades-uso",
        json={"unidades": [
            {"nombre": "galón", "factor_base": GALON},
            {"nombre": "pistolada", "factor_base": PISTOLADA},
        ]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    filas = r.json()
    assert [f["nombre"] for f in filas] == ["GALÓN", "PISTOLADA"]  # normalizadas a mayúsculas
    assert float(filas[0]["factor_base"]) == GALON

    # GET devuelve lo mismo
    r = client.get(f"/api/v1/material/{mat['id']}/unidades-uso", headers=ADMIN_HEADERS)
    assert r.status_code == 200 and len(r.json()) == 2

    # Embebidas en el listado de materiales
    r = client.get("/api/v1/material/", params={"buscar": mat["nombre"]}, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    emb = next(m for m in r.json() if m["id"] == mat["id"])
    assert len(emb["unidades_uso"]) == 2

    # Duplicadas (mismo nombre normalizado) → 400
    r = client.put(
        f"/api/v1/material/{mat['id']}/unidades-uso",
        json={"unidades": [
            {"nombre": "galón", "factor_base": 1},
            {"nombre": "GALÓN", "factor_base": 2},
        ]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, r.text
    assert "repetidas" in r.json()["detail"]

    # Factor inválido → 422 (Pydantic)
    r = client.put(
        f"/api/v1/material/{mat['id']}/unidades-uso",
        json={"unidades": [{"nombre": "GALÓN", "factor_base": 0}]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422, r.text

    # Reemplazo a vacío deja el material como siempre
    r = client.put(
        f"/api/v1/material/{mat['id']}/unidades-uso",
        json={"unidades": []},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200 and r.json() == []


def _crear_unidades(client, mat_id, unidades):
    r = client.put(
        f"/api/v1/material/{mat_id}/unidades-uso",
        json={"unidades": unidades},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    return {u["nombre"]: u["id"] for u in r.json()}


def _usar_directo(client, etapa, material_id, cantidad, extra=None):
    payload = {
        "etapa_produccion_id": etapa,
        "material_id": material_id,
        "cantidad": cantidad,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
    }
    if extra:
        payload.update(extra)
    return client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)


def _pedir(client, etapa, material_id, cantidad, extra=None):
    payload = {
        "etapa_produccion_id": etapa,
        "material_id": material_id,
        "cantidad": cantidad,
        "es_pedido": True,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
    }
    if extra:
        payload.update(extra)
    return client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)


def _cerrar_etapa(db, cleaner, etapa_id):
    ids = [
        r[0]
        for r in db.execute(
            text("SELECT id FROM consumo_material WHERE etapa_produccion_id = :e"),
            {"e": etapa_id},
        ).fetchall()
    ]
    cleaner.registrar_muchos("consumo_material", ids)
    for i in ids:
        cleaner.registrar_gastos_like(db, f"[consumo {i}]")
    return ids


def _gasto_monto(db, consumo_id):
    row = db.execute(
        text("SELECT monto FROM gasto WHERE observaciones LIKE :m"),
        {"m": f"%[consumo {consumo_id}]%"},
    ).fetchone()
    return Decimal(str(row[0])) if row else None


# ============================================================================
# 3. Uso directo en galón
# ============================================================================

def test_uso_directo_en_galon(client, cleaner, db):
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=1000.0, unidad_medida_id=4)
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", 100)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    ids = _crear_unidades(client, mat["id"], [
        {"nombre": "GALÓN", "factor_base": GALON},
        {"nombre": "PISTOLADA", "factor_base": PISTOLADA},
    ])

    r = _usar_directo(client, etapa, mat["id"], 2, {"unidad_uso_id": ids["GALÓN"]})
    assert r.status_code in (200, 201), r.text
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")
    registrar_inventario_de_material(db, cleaner, mat["id"])

    assert Decimal(str(consumo["cantidad"])) == Decimal("7.5700")  # 2 gal × 3,785
    assert Decimal(str(consumo["cantidad_uso"])) == Decimal("2")
    assert consumo["unidad_uso"]["nombre"] == "GALÓN"
    assert consumo["detalle_uso"] == "2 GALÓN (= 7.57 L)"
    assert stock_actual(db, mat["id"]) == Decimal("92.4300")
    assert _gasto_monto(db, consumo["id"]) == Decimal("7570.00")  # 7,57 × 1000


def test_unidad_de_otro_material_rechazada(client, cleaner, db):
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat_a = crear_material(client, cleaner, unidad_medida_id=4)
    mat_b = crear_material(client, cleaner, unidad_medida_id=4)
    crear_movimiento(client, cleaner, mat_b["id"], "ENTRADA", 10)
    registrar_inventario_de_material(db, cleaner, mat_b["id"])
    ids = _crear_unidades(client, mat_a["id"], [{"nombre": "GALÓN", "factor_base": GALON}])

    r = _usar_directo(client, etapa, mat_b["id"], 1, {"unidad_uso_id": ids["GALÓN"]})
    assert r.status_code == 400, r.text
    assert "no pertenece" in r.json()["detail"]


def test_pedido_abierto_no_admite_unidad_uso(client, cleaner, db):
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner, unidad_medida_id=4)
    ids = _crear_unidades(client, mat["id"], [{"nombre": "GALÓN", "factor_base": GALON}])

    payload = {
        "etapa_produccion_id": etapa,
        "material_id": mat["id"],
        "es_pedido": True,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
        "unidad_uso_id": ids["GALÓN"],
    }
    r = client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text

    # Mutex con pieza
    r = _usar_directo(client, etapa, mat["id"], 1, {
        "unidad_uso_id": ids["GALÓN"], "pieza_largo": 2, "pieza_ancho": 10, "pieza_espesor": 5,
    })
    assert r.status_code == 400, r.text


# ============================================================================
# 4. Pedido en galón + confirmación multi-uso
# ============================================================================

def test_pedido_galon_confirmacion_multi_uso(client, cleaner, db):
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=1000.0, unidad_medida_id=4)
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", 100)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    ids = _crear_unidades(client, mat["id"], [
        {"nombre": "GALÓN", "factor_base": GALON},
        {"nombre": "PISTOLADA", "factor_base": PISTOLADA},
    ])

    # Entrega 2 galones (7,57 L) — costo provisional
    r = _pedir(client, etapa, mat["id"], 2, {"unidad_uso_id": ids["GALÓN"]})
    assert r.status_code in (200, 201), r.text
    pedido = r.json()
    assert Decimal(str(pedido["cantidad_pedida"])) == Decimal("7.5700")
    assert stock_actual(db, mat["id"]) == Decimal("92.4300")

    # Se usaron 3 pistoladas (0,75 L) + medio litro (0,5 L)
    r = client.put(
        f"/api/v1/produccion/consumo/{pedido['id']}/confirmar",
        json={"usos": [
            {"cantidad": 3, "unidad_uso_id": ids["PISTOLADA"]},
            {"cantidad": 0.5},
        ]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    head = r.json()
    assert Decimal(str(head["cantidad"])) == Decimal("0.7500")
    assert head["detalle_uso"] == "3 PISTOLADA (= 0.75 L)"
    assert Decimal(str(head["cantidad_pedida"])) == Decimal("7.5700")  # se conserva

    ids_consumos = _cerrar_etapa(db, cleaner, etapa)
    assert len(ids_consumos) == 2  # cabeza + hermano

    # El hermano (medio litro, uso directo en base) quedó aislado
    hermano = db.execute(
        text(
            "SELECT cantidad, detalle_uso, unidad_uso_id FROM consumo_material"
            " WHERE etapa_produccion_id = :e AND id <> :h"
        ),
        {"e": etapa, "h": pedido["id"]},
    ).fetchone()
    assert hermano is not None
    assert Decimal(str(hermano[0])) == Decimal("0.5000")
    assert hermano[1] == "0.5 (unidad base)"
    assert hermano[2] is None

    # Stock final: 100 - 0,75 - 0,5 (la entrega de más volvió)
    assert stock_actual(db, mat["id"]) == Decimal("98.7500")


def test_reversa_restaura_stock_exacto(client, cleaner, db):
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=1000.0, unidad_medida_id=4)
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", 50)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    ids = _crear_unidades(client, mat["id"], [{"nombre": "PISTOLADA", "factor_base": PISTOLADA}])

    r = _usar_directo(client, etapa, mat["id"], 3, {"unidad_uso_id": ids["PISTOLADA"]})
    assert r.status_code in (200, 201), r.text
    consumo = r.json()
    registrar_inventario_de_material(db, cleaner, mat["id"])
    assert stock_actual(db, mat["id"]) == Decimal("49.2500")

    r = client.delete(f"/api/v1/produccion/consumo/{consumo['id']}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 204), r.text
    assert stock_actual(db, mat["id"]) == Decimal("50.0000")
