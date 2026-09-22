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


def confirmar_uso(client, consumo_id, cantidad_usada, extra=None):
    payload = {"cantidad_usada": cantidad_usada}
    if extra:
        payload.update(extra)
    return client.put(
        f"/api/v1/produccion/consumo/{consumo_id}/confirmar",
        json=payload,
        headers=ADMIN_HEADERS,
    )


def _setup(client, cleaner, db, costo=5000.0, stock=20):
    """Etapa EN_PROCESO + material en metros (madera) con stock."""
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=costo, unidad_medida_id=2)
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", stock)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    return orden, etapa, mat


def _setup_vol(client, cleaner, db, stock=5):
    """Etapa EN_PROCESO + material VOLUMÉTRICO (m³, unidad 193) con stock."""
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=5000.0, unidad_medida_id=193)
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", stock)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    return orden, etapa, mat


def _cerrar_etapa(db, cleaner, etapa_id):
    """Registra TODOS los consumos de la etapa y sus gastos automáticos,
    incluidos los hermanos que crea la confirmación multi-uso (ids que el
    test no conoce de antemano). Evita residuos de gastos/consumos."""
    from sqlalchemy import text
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


# ============================================================================
# 9. Pedido ABIERTO: piden "madera" a secas, sin cantidad
# ============================================================================

def test_pedido_abierto_sin_cantidad_no_toca_stock(client, cleaner, db):
    """El taller pide 'madera' sin especificar cuánto llevan: el consumo nace
    PENDIENTE con cantidad 0, SIN movimiento de inventario y SIN gasto
    provisional. Todo el descuento y el costo real ocurren al confirmar."""
    orden, etapa, mat = _setup(client, cleaner, db)
    r = pedir(client, etapa, mat["id"], None)
    assert r.status_code == 201, f"pedido abierto → {r.status_code}: {r.text}"
    consumo = r.json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    assert consumo["estado"] == "PENDIENTE"
    assert float(consumo["cantidad"]) == 0.0
    # Pedido abierto: cantidad_pedida NULL y costo provisional $0.
    assert consumo["cantidad_pedida"] is None
    assert float(consumo["costo_unitario"]) == 5000.0
    assert stock_actual(db, mat["id"]) == Decimal("20")
    assert gasto_monto(db, consumo["id"]) is None

    # Costos en vivo: provisional con total $0 (aún no se sabe lo usado).
    rv = client.get(f"/api/v1/produccion/orden/{orden['id']}/costos-en-vivo", headers=ADMIN_HEADERS)
    assert rv.status_code == 200, rv.text
    insumos = [i for s in rv.json()["secciones"] for i in s["insumos"]]
    fila = next((i for i in insumos if i["nombre"] == mat["nombre"]), None)
    assert fila is not None, "el pedido abierto debe aparecer en costos"
    assert fila["es_pendiente"] is True
    assert float(fila["total"]) == 0.0


def test_pedido_abierto_confirmar_uso_descuenta_todo_lo_usado(client, cleaner, db):
    """Al confirmar un pedido abierto, TODO lo digitado sale del depósito
    (nada fue entregado al pedir) y el gasto se CREA con el costo real."""
    _, etapa, mat = _setup(client, cleaner, db, stock=5)
    consumo = pedir(client, etapa, mat["id"], None).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    assert stock_actual(db, mat["id"]) == Decimal("5")

    r = confirmar_uso(client, consumo["id"], 3)
    assert r.status_code == 200, f"confirmar abierto → {r.status_code}: {r.text}"
    registrar_inventario_de_material(db, cleaner, mat["id"])
    conf = r.json()
    assert conf["estado"] == "CONFIRMADO"
    assert float(conf["cantidad"]) == 3.0
    assert conf["cantidad_pedida"] is None
    assert stock_actual(db, mat["id"]) == Decimal("2")
    # El gasto se CREÓ al confirmar (el pedido abierto no creó provisional).
    assert gasto_monto(db, consumo["id"]) == Decimal("15000.00")

    # Costos en vivo: ya no provisional, total = lo usado.
    orden_id = db.execute(
        text("SELECT orden_produccion_id FROM etapa_produccion WHERE id = :i"),
        {"i": etapa},
    ).fetchone()[0]
    rv = client.get(f"/api/v1/produccion/orden/{orden_id}/costos-en-vivo", headers=ADMIN_HEADERS)
    insumos = [i for s in rv.json()["secciones"] for i in s["insumos"]]
    fila = next(i for i in insumos if i["nombre"] == mat["nombre"])
    assert fila["es_pendiente"] is False
    assert float(fila["total"]) == 15000.0


def test_pedido_abierto_confirmar_uso_sin_stock_rechazado(client, cleaner, db):
    _, etapa, mat = _setup(client, cleaner, db, stock=5)
    consumo = pedir(client, etapa, mat["id"], None).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    r = confirmar_uso(client, consumo["id"], 7)
    assert r.status_code == 400, f"usar 7 con stock 5 → {r.status_code}: {r.text}"
    db.expire_all()
    assert stock_actual(db, mat["id"]) == Decimal("5")
    row = db.execute(
        text("SELECT estado, cantidad FROM consumo_material WHERE id = :i"),
        {"i": consumo["id"]},
    ).fetchone()
    assert row[0] == "PENDIENTE" and Decimal(str(row[1])) == Decimal("0")


def test_pedido_abierto_no_admite_captura_flexible(client, cleaner, db):
    """Sin cantidad no hay nada que convertir: cm/por pieza es un error."""
    _, etapa, mat = _setup(client, cleaner, db)
    r = pedir(client, etapa, mat["id"], None, extra={"unidad_captura": "CM"})
    assert r.status_code == 400, r.text


def test_uso_directo_sin_cantidad_rechazado(client, cleaner, db):
    """El pedido abierto es exclusivo del modo 'Pedir': el uso directo exige
    cantidad (es lo que se consume y descuenta de una vez)."""
    _, etapa, mat = _setup(client, cleaner, db)
    r = usar_directo(client, etapa, mat["id"], None)
    assert r.status_code in (400, 422), r.text


# ============================================================================
# 10. Captura flexible al CONFIRMAR (m³/por pieza y cm)
# ============================================================================

def test_confirmar_uso_por_pieza_formula_casa(client, cleaner, db):
    """Al confirmar se puede digitar por pieza (fórmula de la casa):
    (L×A×E) × piezas ÷ 10000 = m³ usados."""
    orden, etapa, mat = _setup(client, cleaner, db)
    # La fórmula de la casa solo aplica a materiales VOLUMÉTRICOS (m³).
    mat = crear_material(client, cleaner, costo_base=5000.0, unidad_medida_id=193)
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", 5)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    r = pedir(client, etapa, mat["id"], None)
    assert r.status_code == 201, r.text
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    registrar_inventario_de_material(db, cleaner, mat["id"])

    r = confirmar_uso(client, consumo["id"], 2, extra={
        "pieza_largo": 200, "pieza_ancho": 20, "pieza_espesor": 4,
    })
    assert r.status_code == 200, f"confirmar por pieza → {r.status_code}: {r.text}"
    registrar_inventario_de_material(db, cleaner, mat["id"])
    conf = r.json()
    assert conf["estado"] == "CONFIRMADO"
    # (200×20×4) × 2 ÷ 10000 = 3.2 m³.
    assert abs(float(conf["cantidad"]) - 3.2) < 0.001
    # Trazabilidad: cómo se digitó queda guardado.
    assert float(conf["pieza_largo"]) == 200.0
    assert float(conf["pieza_ancho"]) == 20.0
    assert float(conf["pieza_espesor"]) == 4.0
    # Stock: 5 − 3.2 = 1.8. Gasto real = 3.2 × 5000.
    assert stock_actual(db, mat["id"]) == Decimal("1.8")
    assert gasto_monto(db, consumo["id"]) == Decimal("16000.00")


def test_confirmar_uso_por_pieza_incompleta_rechazado(client, cleaner, db):
    _, etapa, mat = _setup(client, cleaner, db)
    consumo = pedir(client, etapa, mat["id"], None).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    r = confirmar_uso(client, consumo["id"], 2, extra={"pieza_largo": 200, "pieza_ancho": 20})
    assert r.status_code == 400, r.text
    db.expire_all()
    row = db.execute(
        text("SELECT estado FROM consumo_material WHERE id = :i"),
        {"i": consumo["id"]},
    ).fetchone()
    assert row[0] == "PENDIENTE"


def test_confirmar_uso_en_cm_lineal(client, cleaner, db):
    """Material LINEAL digitado en cm al confirmar: 152 cm = 1.52 m."""
    _, etapa, mat = _setup(client, cleaner, db, stock=10)
    r = pedir(client, etapa, mat["id"], None)
    assert r.status_code == 201, r.text
    consumo = r.json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    r = confirmar_uso(client, consumo["id"], 152, extra={"unidad_captura": "CM"})
    assert r.status_code == 200, r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])
    conf = r.json()
    assert abs(float(conf["cantidad"]) - 1.52) < 0.001
    assert conf["unidad_captura"] == "CM"
    assert abs(float(stock_actual(db, mat["id"])) - 8.48) < 0.001


def test_pedido_con_cantidad_confirmar_cm_tambien(client, cleaner, db):
    """El modo híbrido con entrega también admite captura flexible al confirmar:
    entrega 2 m, confirman 100 cm (1 m) → 1 m vuelve al depósito."""
    _, etapa, mat = _setup(client, cleaner, db, stock=5)
    r = pedir(client, etapa, mat["id"], 2)
    assert r.status_code == 201, r.text
    consumo = r.json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    assert stock_actual(db, mat["id"]) == Decimal("3")

    r = confirmar_uso(client, consumo["id"], 100, extra={"unidad_captura": "CM"})
    assert r.status_code == 200, r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])
    assert abs(float(r.json()["cantidad"]) - 1.0) < 0.001
    assert stock_actual(db, mat["id"]) == Decimal("4")
    assert gasto_monto(db, consumo["id"]) == Decimal("5000.00")


# ============================================================================
# 11. Confirmación MULTI-LÍNEA (varios usos en un confirmar) y modo cm
# ============================================================================

def confirmar_usos(client, consumo_id, usos):
    return client.put(
        f"/api/v1/produccion/consumo/{consumo_id}/confirmar",
        json={"usos": usos},
        headers=ADMIN_HEADERS,
    )


def _consumos_de_etapa(db, etapa_id):
    return db.execute(
        text(
            "SELECT id, cantidad, estado, detalle_uso, cantidad_pedida"
            " FROM consumo_material WHERE etapa_produccion_id = :e ORDER BY id"
        ),
        {"e": etapa_id},
    ).fetchall()


def _gastos_de_etapa(db, etapa_id):
    rows = db.execute(
        text(
            "SELECT monto FROM gasto WHERE observaciones LIKE :m"
        ),
        {"m": f"%(Etapa #{etapa_id})%"},
    ).fetchall()
    return [Decimal(str(r[0])) for r in rows]


def test_confirmar_multi_uso_abierto_pieza_y_cm(client, cleaner, db):
    """Un pedido abierto se confirma con VARIOS usos (cm + piezas de tamaños
    distintos): un consumo por uso, stock y gasto exactos, y la tablita de
    costos en vivo muestra cada uso como renglón aparte con su etiqueta."""
    orden, etapa, mat = _setup_vol(client, cleaner, db, stock=5)
    consumo = pedir(client, etapa, mat["id"], None).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    r = confirmar_usos(client, consumo["id"], [
        {"cantidad": 1500, "unidad_captura": "CM"},                       # 0.15 m³
        {"cantidad": 2, "pieza_largo": 2, "pieza_ancho": 10, "pieza_espesor": 5},   # 0.02
        {"cantidad": 1, "pieza_largo": 3, "pieza_ancho": 20, "pieza_espesor": 4},   # 0.024
    ])
    assert r.status_code == 200, f"multi-uso → {r.status_code}: {r.text}"
    _cerrar_etapa(db, cleaner, etapa)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    db.expire_all()

    # Tres consumos CONFIRMADO (cabeza + 2 hermanos), cada uno con su etiqueta.
    filas = _consumos_de_etapa(db, etapa)
    assert len(filas) == 3, filas
    por_id = {f[0]: f for f in filas}
    cabeza = por_id[consumo["id"]]
    assert abs(float(cabeza[1]) - 0.15) < 0.001
    assert cabeza[3] == "1500 cm (cuenta del taller)"
    etiquetas = {f[3] for f in filas}
    assert "Pieza 2×10×5 × 2" in etiquetas
    assert "Pieza 3×20×4 × 1" in etiquetas
    for f in filas:
        assert f[2] == "CONFIRMADO"

    # Stock: 5 − (0.15 + 0.02 + 0.024) = 4.806.
    assert stock_actual(db, mat["id"]) == Decimal("4.806")

    # Gasto total exacto: 0.194 × 5000 = 970 (tres gastos que suman).
    ids = [f[0] for f in filas]
    total_gastos = sum(
        (gasto_monto(db, i) or Decimal("0")) for i in ids
    )
    assert total_gastos == Decimal("970.00"), total_gastos

    # Costos en vivo: un renglón por uso con la captura visible.
    rv = client.get(f"/api/v1/produccion/orden/{orden['id']}/costos-en-vivo", headers=ADMIN_HEADERS)
    assert rv.status_code == 200, rv.text
    insumos = [i for s in rv.json()["secciones"] for i in s["insumos"]]
    del_material = [i for i in insumos if i["nombre"] == mat["nombre"]]
    assert len(del_material) == 3, del_material
    capturas = {i["captura"] for i in del_material}
    assert "1500 cm (cuenta del taller)" in capturas
    assert "Pieza 2×10×5 × 2" in capturas
    total_costos = sum(i["total"] for i in del_material)
    assert abs(total_costos - 970.0) < 0.01, total_costos


def test_confirmar_multi_uso_con_entrega_devuelve_sobrante(client, cleaner, db):
    """Pedido con entrega (2 m) confirmado con 2 usos (0.058 m³): la cabeza
    ajusta la entrega y el stock queda en 5 − 0.058."""
    _, etapa, mat = _setup_vol(client, cleaner, db, stock=5)
    consumo = pedir(client, etapa, mat["id"], 2).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    assert stock_actual(db, mat["id"]) == Decimal("3")

    r = confirmar_usos(client, consumo["id"], [
        {"cantidad": 1, "pieza_largo": 2, "pieza_ancho": 10, "pieza_espesor": 5},  # 0.01
        {"cantidad": 2, "pieza_largo": 3, "pieza_ancho": 20, "pieza_espesor": 4},  # 0.048
    ])
    assert r.status_code == 200, r.text
    _cerrar_etapa(db, cleaner, etapa)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    db.expire_all()

    filas = _consumos_de_etapa(db, etapa)
    assert len(filas) == 2, filas
    cabeza = [f for f in filas if f[0] == consumo["id"]][0]
    assert abs(float(cabeza[1]) - 0.01) < 0.001
    # cantidad_pedida se conserva en la cabeza.
    assert cabeza[4] is not None and abs(float(cabeza[4]) - 2.0) < 0.001
    # Stock: 5 − 0.058 = 4.942.
    assert stock_actual(db, mat["id"]) == Decimal("4.942")


def test_confirmar_multi_uso_sin_stock_rechazado_y_atomico(client, cleaner, db):
    """Si el total de usos supera el stock: 400 y NADA se crea ni se toca."""
    _, etapa, mat = _setup_vol(client, cleaner, db, stock=1)
    consumo = pedir(client, etapa, mat["id"], None).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    r = confirmar_usos(client, consumo["id"], [
        {"cantidad": 5000, "unidad_captura": "CM"},   # 0.5 m³
        {"cantidad": 6000, "unidad_captura": "CM"},   # 0.6 → total 1.1 > 1
    ])
    assert r.status_code == 400, r.text
    db.expire_all()
    filas = _consumos_de_etapa(db, etapa)
    assert len(filas) == 1 and filas[0][2] == "PENDIENTE"
    assert stock_actual(db, mat["id"]) == Decimal("1")


def test_confirmar_cm_volumetrico_un_solo_campo(client, cleaner, db):
    """Modo cm del ebanista: 832 (su cuenta) ÷ 10000 = 0.0832 m³."""
    _, etapa, mat = _setup_vol(client, cleaner, db, stock=5)
    consumo = pedir(client, etapa, mat["id"], None).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])

    r = confirmar_uso(client, consumo["id"], 832, extra={"unidad_captura": "CM"})
    assert r.status_code == 200, r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])
    conf = r.json()
    assert abs(float(conf["cantidad"]) - 0.0832) < 0.0001
    assert conf["detalle_uso"] == "832 cm (cuenta del taller)"
    assert stock_actual(db, mat["id"]) == Decimal("4.9168")
    assert gasto_monto(db, consumo["id"]) == Decimal("416.00")


def test_registrar_cm_volumetrico_un_solo_campo(client, cleaner, db):
    """El registro también acepta la cuenta del ebanista en cm."""
    _, etapa, mat = _setup_vol(client, cleaner, db, stock=5)
    r = usar_directo(client, etapa, mat["id"], 832, extra={"unidad_captura": "CM"})
    assert r.status_code == 201, f"registro cm → {r.status_code}: {r.text}"
    consumo = r.json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    assert abs(float(consumo["cantidad"]) - 0.0832) < 0.0001
    assert consumo["detalle_uso"] == "832 cm (cuenta del taller)"
    assert stock_actual(db, mat["id"]) == Decimal("4.9168")


def test_multi_uso_rechaza_lista_con_cantidad_usada(client, cleaner, db):
    """No se mezclan los dos formatos (usos y cantidad_usada)."""
    _, etapa, mat = _setup(client, cleaner, db)
    consumo = pedir(client, etapa, mat["id"], None).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    r = client.put(
        f"/api/v1/produccion/consumo/{consumo['id']}/confirmar",
        json={"cantidad_usada": 1, "usos": [{"cantidad": 1}]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, r.text


def test_eliminar_uso_hermano_repone_stock_y_gasto(client, cleaner, db):
    """Cada uso tiene su propio movimiento: eliminar un hermano repone su
    stock exacto y revierte su egreso, sin tocar los demás."""
    _, etapa, mat = _setup_vol(client, cleaner, db, stock=5)
    consumo = pedir(client, etapa, mat["id"], None).json()
    _cerrar(client, cleaner, db, mat, consumo["id"])
    r = confirmar_usos(client, consumo["id"], [
        {"cantidad": 1500, "unidad_captura": "CM"},                  # 0.15
        {"cantidad": 2, "pieza_largo": 2, "pieza_ancho": 10, "pieza_espesor": 5},  # 0.02
    ])
    assert r.status_code == 200, r.text
    _cerrar_etapa(db, cleaner, etapa)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    db.expire_all()
    assert stock_actual(db, mat["id"]) == Decimal("4.83")

    hermano_id = [f[0] for f in _consumos_de_etapa(db, etapa) if f[0] != consumo["id"]][0]
    r = client.delete(f"/api/v1/produccion/consumo/{hermano_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 204, r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])
    db.expire_all()
    # 4.83 + 0.02 = 4.85 (solo el hermano; la cabeza no se toca).
    assert stock_actual(db, mat["id"]) == Decimal("4.85")
    assert gasto_monto(db, hermano_id) is None
    assert gasto_monto(db, consumo["id"]) == Decimal("750.00")
