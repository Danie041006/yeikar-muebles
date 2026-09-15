"""
test_pedido_uso_material.py — Pedido general de material (madera y demás).

Flujo híbrido: o se registra el uso directo (CONFIRMADO inmediato, como
siempre) o se PIDE el material (es_pedido=True) y se confirma después cuánto
se usó de verdad:

  1. Pedido: SALIDA de lo entregado, costo provisional, gasto provisional,
     consumo PENDIENTE con cantidad_pedida = lo entregado. Aparece en costos
     en vivo marcado como provisional (sin "usado" aún).
  2. Confirmar con MENOS de lo pedido → lo que sobró vuelve SOLO al depósito
     (ENTRADA), gasto ajustado al costo real, cantidad = lo usado.
  3. Confirmar con MÁS (stock suficiente) → SALIDA extra.
  4. Confirmar con MÁS sin stock → 400 sin tocar nada.
  5. Uso directo sigue CONFIRMADO inmediato (híbrido).
  6. Validaciones: pedido no admite cortes ni lámina completa.
  7. Eliminar un pedido PENDIENTE revierte el stock y el gasto.
  8. Pedido de madera en cm (captura flexible) → base en metros.

Ejecutar:  pytest test/test_pedido_uso_material.py -v
"""
import os
import sys
from datetime import datetime
from decimal import Decimal

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


def gasto_monto(db, consumo_id) -> Decimal | None:
    row = db.execute(
        text("SELECT monto FROM gasto WHERE observaciones LIKE :m"),
        {"m": f"%[consumo {consumo_id}]%"},
    ).fetchone()
    return Decimal(str(row[0])) if row else None


def pedir(client, etapa, material_id, cantidad, extra=None):
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


def usar_directo(client, etapa, material_id, cantidad, extra=None):
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


def confirmar_uso(client, consumo_id, cantidad_usada):
    return client.put(
        f"/api/v1/produccion/consumo/{consumo_id}/confirmar",
        json={"cantidad_usada": cantidad_usada},
        headers=ADMIN_HEADERS,
    )


def _setup(client, cleaner, db, costo=5000.0, stock=20):
    """Etapa EN_PROCESO + material en metros (madera) con stock."""
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=costo, unidad_medida_id=2)
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", stock)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    return orden, etapa, mat


def _cerrar(client, cleaner, db, mat, consumo_id):
    """Registra todo rastro del material para una limpieza completa."""
    cleaner.registrar("consumo_material", consumo_id)
    cleaner.registrar_gastos_like(db, f"[consumo {consumo_id}]")
    registrar_inventario_de_material(db, cleaner, mat["id"])


# ============================================================================
# 1. Pedido queda PENDIENTE y descuenta lo entregado
# ============================================================================

def test_pedido_madera_queda_pendiente_y_descuenta(client, cleaner, db):
    orden, etapa, mat = _setup(client, cleaner, db)
    r = pedir(client, etapa, mat["id"], 10)
    assert r.status_code == 201, f"pedido madera → {r.status_code}: {r.text}"
    consumo = r.json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    assert consumo["estado"] == "PENDIENTE"
    assert float(consumo["cantidad"]) == 10.0
    # Lo pedido queda guardado: el registro dice cuánto pidieron.
    assert float(consumo["cantidad_pedida"]) == 10.0
    assert float(consumo["costo_unitario"]) == 5000.0
    # Stock: 20 − 10 entregadas = 10. Gasto provisional = 10 × 5000.
    assert stock_actual(db, mat["id"]) == Decimal("10")
    assert gasto_monto(db, consumo["id"]) == Decimal("50000.00")

    # Costos en vivo: aparece con costo provisional, marcado como pendiente
    # (sin "usado" aún).
    rv = client.get(f"/api/v1/produccion/orden/{orden['id']}/costos-en-vivo", headers=ADMIN_HEADERS)
    assert rv.status_code == 200, rv.text
    insumos = [i for s in rv.json()["secciones"] for i in s["insumos"]]
    fila = next((i for i in insumos if i["nombre"] == mat["nombre"]), None)
    assert fila is not None, "el pedido debe aparecer en la tablita de costos"
    assert fila["es_pendiente"] is True
    assert float(fila["total"]) == 50000.0


# ============================================================================
# 2-4. Confirmar: sobrante al depósito / de más / sin stock
# ============================================================================

def test_confirmar_uso_parcial_devuelve_sobrante(client, cleaner, db):
    orden, etapa, mat = _setup(client, cleaner, db)
    r = pedir(client, etapa, mat["id"], 10)
    consumo = r.json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    r = confirmar_uso(client, consumo["id"], 6)
    assert r.status_code == 200, f"confirmar uso → {r.status_code}: {r.text}"
    registrar_inventario_de_material(db, cleaner, mat["id"])
    conf = r.json()
    assert conf["estado"] == "CONFIRMADO"
    assert float(conf["cantidad"]) == 6.0
    assert float(conf["cantidad_pedida"]) == 10.0
    # 20 − 10 entregadas + 4 devueltas = 14. Gasto real = 6 × 5000.
    assert stock_actual(db, mat["id"]) == Decimal("14")
    assert gasto_monto(db, consumo["id"]) == Decimal("30000.00")

    # Costos en vivo: ya no es provisional, total = lo usado.
    rv = client.get(f"/api/v1/produccion/orden/{orden['id']}/costos-en-vivo", headers=ADMIN_HEADERS)
    insumos = [i for s in rv.json()["secciones"] for i in s["insumos"]]
    fila = next(i for i in insumos if i["nombre"] == mat["nombre"])
    assert fila["es_pendiente"] is False
    assert float(fila["total"]) == 30000.0


def test_confirmar_uso_de_mas_con_stock_descuenta_extra(client, cleaner, db):
    _, etapa, mat = _setup(client, cleaner, db)
    consumo = pedir(client, etapa, mat["id"], 10).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    r = confirmar_uso(client, consumo["id"], 12)
    assert r.status_code == 200, r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])
    assert float(r.json()["cantidad"]) == 12.0
    # 20 − 10 − 2 extra = 8. Gasto real = 12 × 5000.
    assert stock_actual(db, mat["id"]) == Decimal("8")
    assert gasto_monto(db, consumo["id"]) == Decimal("60000.00")


def test_confirmar_uso_de_mas_sin_stock_rechazado(client, cleaner, db):
    _, etapa, mat = _setup(client, cleaner, db, stock=10)
    consumo = pedir(client, etapa, mat["id"], 10).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    assert stock_actual(db, mat["id"]) == Decimal("0")

    r = confirmar_uso(client, consumo["id"], 12)
    assert r.status_code == 400, f"usar de más sin stock → {r.status_code}: {r.text}"
    # Nada se movió: sigue PENDIENTE con lo pedido.
    db.expire_all()
    assert stock_actual(db, mat["id"]) == Decimal("0")
    row = db.execute(
        text("SELECT estado, cantidad FROM consumo_material WHERE id = :i"),
        {"i": consumo["id"]},
    ).fetchone()
    assert row[0] == "PENDIENTE" and Decimal(str(row[1])) == Decimal("10")


def test_confirmar_dos_veces_rechazado(client, cleaner, db):
    _, etapa, mat = _setup(client, cleaner, db)
    consumo = pedir(client, etapa, mat["id"], 10).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    assert confirmar_uso(client, consumo["id"], 6).status_code == 200
    registrar_inventario_de_material(db, cleaner, mat["id"])
    r = confirmar_uso(client, consumo["id"], 5)
    assert r.status_code == 400, r.text


# ============================================================================
# 5-6. Híbrido y validaciones
# ============================================================================

def test_uso_directo_sigue_confirmado_inmediato(client, cleaner, db):
    _, etapa, mat = _setup(client, cleaner, db)
    r = usar_directo(client, etapa, mat["id"], 4)
    assert r.status_code == 201, r.text
    consumo = r.json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    assert consumo["estado"] == "CONFIRMADO"
    assert consumo["cantidad_pedida"] is None
    assert stock_actual(db, mat["id"]) == Decimal("16")


def test_pedido_no_admite_cortes(client, cleaner, db):
    from test_cortes_laminas import crear_material_laminar
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)
    r = pedir(client, etapa, mat["id"], 2, extra={"ancho_corte_cm": 80, "largo_corte_cm": 130})
    assert r.status_code == 400, r.text


def test_pedido_no_se_combina_con_lamina_completa(client, cleaner, db):
    from test_cortes_laminas import crear_material_laminar, dar_stock
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 5)
    r = pedir(client, etapa, mat["id"], 2, extra={"es_lamina_completa": True})
    assert r.status_code == 400, r.text


def test_confirmar_exige_un_solo_modo(client, cleaner, db):
    _, etapa, mat = _setup(client, cleaner, db)
    consumo = pedir(client, etapa, mat["id"], 10).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    r = client.put(
        f"/api/v1/produccion/consumo/{consumo['id']}/confirmar",
        json={"cantidad_usada": 5, "cantidad_cortes": 2, "largo_corte_cm": 10, "ancho_corte_cm": 10},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, r.text
    r = client.put(
        f"/api/v1/produccion/consumo/{consumo['id']}/confirmar",
        json={},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code in (400, 422), r.text


# ============================================================================
# 7-8. Eliminar pendiente y captura en cm
# ============================================================================

def test_eliminar_pedido_pendiente_revierte_stock_y_gasto(client, cleaner, db):
    _, etapa, mat = _setup(client, cleaner, db)
    consumo = pedir(client, etapa, mat["id"], 10).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    assert stock_actual(db, mat["id"]) == Decimal("10")

    r = client.delete(f"/api/v1/produccion/consumo/{consumo['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 204, r.text
    db.expire_all()
    assert stock_actual(db, mat["id"]) == Decimal("20")
    assert gasto_monto(db, consumo["id"]) is None


def test_pedido_madera_en_cm_y_confirmar(client, cleaner, db):
    """La entrega se digita en cm (250 cm = 2.5 m en base); el uso se confirma
    en la unidad base y el sobrante vuelve al depósito."""
    _, etapa, mat = _setup(client, cleaner, db)
    r = pedir(client, etapa, mat["id"], 250, extra={"unidad_captura": "CM"})
    assert r.status_code == 201, r.text
    consumo = r.json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    assert consumo["estado"] == "PENDIENTE"
    assert abs(float(consumo["cantidad"]) - 2.5) < 0.001
    assert stock_actual(db, mat["id"]) == Decimal("17.5")

    r = confirmar_uso(client, consumo["id"], 2.0)
    assert r.status_code == 200, r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])
    assert abs(float(r.json()["cantidad"]) - 2.0) < 0.001
    assert stock_actual(db, mat["id"]) == Decimal("18.0")
    assert gasto_monto(db, consumo["id"]) == Decimal("10000.00")
