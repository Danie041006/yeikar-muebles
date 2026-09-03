"""
test_descuento_materiales.py
============================
Verificación de INTEGRACIÓN (vía API, con etapa EN_PROCESO) de que el stock
descuenta bien cuando los materiales se toman POR MEDIDAS:

  Láminas (espuma, melamina — igual que MDF: cortes bidimensionales):
    consumo por cortes → descuenta LÁMINAS enteras y deja el sobrante.

  Madera:
    volumétrica (m³) por pieza con medidas → descuenta la fórmula de la casa
      (L×A×E) × piezas ÷ 1000 = m³.
    lineal (metros) capturado en cm → descuenta la conversión (1520 cm → 15.2 m).

Ejecutar:  pytest test/test_descuento_materiales.py -v
"""
import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_material
from test_cortes_laminas import (
    _pedido_con_etapa_en_proceso,
    dar_stock,
    registrar_sobrantes_de_material,
    stock_actual,
)

UNIDAD_M3 = 193   # Metro cúbico (m³) — insertada por la migración de captura flexible
UNIDAD_METRO = 2  # Metro (m)


def _consumir(client, cleaner, db, etapa, material_id, payload):
    body = {
        "etapa_produccion_id": etapa,
        "material_id": material_id,
        "cantidad": payload.get("cantidad", 1),
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
    }
    body.update(payload.get("extra", {}))
    r = client.post("/api/v1/produccion/consumo/", json=body, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"consumo → {r.status_code}: {r.text}"
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")
    from conftest import registrar_inventario_de_material
    registrar_inventario_de_material(db, cleaner, material_id)
    registrar_sobrantes_de_material(db, cleaner, material_id)
    return consumo


def _movimiento_material(db, material_id):
    row = db.execute(text(
        "SELECT cantidad, tipo, llevada FROM movimiento_inventario "
        "WHERE material_id = :m ORDER BY id DESC LIMIT 1"
    ), {"m": material_id}).fetchone()
    return row


# ============================================================================
# Láminas: espuma y melamina se comportan igual que MDF (cortes 2D)
# ============================================================================

def test_espuma_lamina_cortes_descuenta_lamina_y_deja_sobrante(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    # Espuma de lámina 200×140 cm (como una espuma real de colchón)
    espuma = crear_material(client, cleaner, nombre="ESPUMA TEST 200X140",
                            costo_base=48000, unidad_medida_id=36)
    r = client.put(f"/api/v1/material/{espuma['id']}", json={
        "largo_cm": 200, "ancho_cm": 140,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    dar_stock(client, cleaner, espuma["id"], 10)

    # 2 cortes de 70×100 → caben 4 por lámina → se abre 1 lámina
    consumo = _consumir(client, cleaner, db, etapa, espuma["id"], {
        "cantidad": 2,
        "extra": {"ancho_corte_cm": 70, "largo_corte_cm": 100},
    })
    assert float(consumo["laminas_consumidas"]) == 1.0
    assert stock_actual(db, espuma["id"]) == Decimal("9"), "Espuma: 10 − 1 lámina = 9"

    # El kardex descontó 1 LÁMINA (no 2 "cortes")
    mov = _movimiento_material(db, espuma["id"])
    assert mov is not None and float(mov[0]) == 1.0

    # Dejó sobrante (140×100 = 14000 cm²)
    n = db.execute(text(
        "SELECT COUNT(*) FROM sobrante_lamina WHERE material_id = :m AND estado='DISPONIBLE'"
    ), {"m": espuma["id"]}).scalar()
    assert n == 1, "El corte de espuma debe registrar el sobrante"


def test_melamina_lamina_cortes_descuenta_bien(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mel = crear_material(client, cleaner, nombre="MELAMINA TEST 244X183",
                         costo_base=65000, unidad_medida_id=36)
    r = client.put(f"/api/v1/material/{mel['id']}", json={
        "largo_cm": 244, "ancho_cm": 183,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    dar_stock(client, cleaner, mel["id"], 6)

    # 3 cortes de 80×130 → caben 3 por lámina (orientación 3×1) → 1 lámina
    consumo = _consumir(client, cleaner, db, etapa, mel["id"], {
        "cantidad": 3,
        "extra": {"ancho_corte_cm": 80, "largo_corte_cm": 130},
    })
    assert float(consumo["laminas_consumidas"]) == 1.0
    assert stock_actual(db, mel["id"]) == Decimal("5"), "Melamina: 6 − 1 = 5"
    mov = _movimiento_material(db, mel["id"])
    assert float(mov[0]) == 1.0

    # 6 cortes (2 láminas) → stock 3 y sobrante del área de la última
    consumo2 = _consumir(client, cleaner, db, etapa, mel["id"], {
        "cantidad": 6,
        "extra": {"ancho_corte_cm": 80, "largo_corte_cm": 130},
    })
    assert float(consumo2["laminas_consumidas"]) == 2.0
    assert stock_actual(db, mel["id"]) == Decimal("3")


def test_espuma_sirve_desde_sobrante_sin_tocar_stock(client, cleaner, db):
    from app.modules.inventory.model import SobranteLamina
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    espuma = crear_material(client, cleaner, nombre="ESPUMA SOB 140X100",
                            costo_base=30000, unidad_medida_id=36)
    r = client.put(f"/api/v1/material/{espuma['id']}", json={
        "largo_cm": 140, "ancho_cm": 100,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    dar_stock(client, cleaner, espuma["id"], 4)

    sob = SobranteLamina(
        material_id=espuma["id"], ubicacion_id=1,
        largo_cm=Decimal("140"), ancho_cm=Decimal("100"), estado="DISPONIBLE",
    )
    db.add(sob)
    db.commit()
    registrar_sobrantes_de_material(db, cleaner, espuma["id"])

    # 2 cortes de 50×50 desde el sobrante → NO toca el stock de láminas
    consumo = _consumir(client, cleaner, db, etapa, espuma["id"], {
        "cantidad": 2,
        "extra": {"ancho_corte_cm": 50, "largo_corte_cm": 50, "origen_sobrante_id": sob.id},
    })
    assert float(consumo["laminas_consumidas"]) == 0.0
    assert stock_actual(db, espuma["id"]) == Decimal("4"), "Desde sobrante no se descuentan láminas"
    db.refresh(sob)
    assert Decimal(str(sob.largo_cm)) * Decimal(str(sob.ancho_cm)) == Decimal("9000.00")


# ============================================================================
# Madera: volumétrica por pieza (m³) y lineal en cm
# ============================================================================

def test_madera_volumetrica_pieza_descuenta_m3(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    madera = crear_material(client, cleaner, nombre="MADERA TEST VOLUMETRICA",
                            costo_base=2000000, unidad_medida_id=UNIDAD_M3)
    dar_stock(client, cleaner, madera["id"], 20)   # 20 m³

    # 2 piezas de 20×4×2 → (20×4×2)×2 ÷ 1000 = 0.32 m³
    consumo = _consumir(client, cleaner, db, etapa, madera["id"], {
        "cantidad": 2,
        "extra": {
            "pieza_largo": 20, "pieza_ancho": 4, "pieza_espesor": 2,
        },
    })
    # La cantidad almacenada en el consumo es la CANÓNICA (0.32 m³)
    assert float(consumo["cantidad"]) == 0.32, consumo["cantidad"]
    assert stock_actual(db, madera["id"]) == Decimal("19.68"), "20 − 0.32 m³ = 19.68"
    mov = _movimiento_material(db, madera["id"])
    assert float(mov[0]) == 0.32, "El kardex descuenta los m³ convertidos"


def test_madera_volumetrica_una_pieza_016(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    madera = crear_material(client, cleaner, nombre="MADERA TEST PIEZA 016",
                            costo_base=2000000, unidad_medida_id=UNIDAD_M3)
    dar_stock(client, cleaner, madera["id"], 1)
    # 1 pieza 20×4×2 → 0.16 m³
    _consumir(client, cleaner, db, etapa, madera["id"], {
        "cantidad": 1,
        "extra": {"pieza_largo": 20, "pieza_ancho": 4, "pieza_espesor": 2},
    })
    assert stock_actual(db, madera["id"]) == Decimal("0.84")


def test_madera_lineal_en_cm_descuenta_metros(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    madera = crear_material(client, cleaner, nombre="MADERA TEST LINEAL",
                            costo_base=140, unidad_medida_id=UNIDAD_METRO)
    dar_stock(client, cleaner, madera["id"], 50)   # 50 metros

    # 1520 cm → 15.20 m
    consumo = _consumir(client, cleaner, db, etapa, madera["id"], {
        "cantidad": 1520,
        "extra": {"unidad_captura": "CM"},
    })
    assert float(consumo["cantidad"]) == 15.20, consumo["cantidad"]
    assert stock_actual(db, madera["id"]) == Decimal("34.80"), "50 − 15.2 m = 34.8"
    mov = _movimiento_material(db, madera["id"])
    assert float(mov[0]) == 15.20


def test_madera_lineal_en_metros_pasa_tal_cual(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    madera = crear_material(client, cleaner, nombre="MADERA TEST MTS",
                            costo_base=140, unidad_medida_id=UNIDAD_METRO)
    dar_stock(client, cleaner, madera["id"], 10)
    _consumir(client, cleaner, db, etapa, madera["id"], {
        "cantidad": 2.5,
        "extra": {"unidad_captura": "M"},
    })
    assert stock_actual(db, madera["id"]) == Decimal("7.50")


def test_reversa_madera_por_pieza_repone_el_m3_exacto(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    madera = crear_material(client, cleaner, nombre="MADERA TEST REVERSA",
                            costo_base=2000000, unidad_medida_id=UNIDAD_M3)
    dar_stock(client, cleaner, madera["id"], 20)

    r = client.post("/api/v1/produccion/consumo/", json={
        "etapa_produccion_id": etapa,
        "material_id": madera["id"],
        "cantidad": 2,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
        "pieza_largo": 20, "pieza_ancho": 4, "pieza_espesor": 2,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")
    from conftest import registrar_inventario_de_material
    registrar_inventario_de_material(db, cleaner, madera["id"])

    assert stock_actual(db, madera["id"]) == Decimal("19.68")

    # Eliminar el consumo → la reversa repone los 0.32 m³ EXACTOS (usa la
    # cantidad canónica almacenada, no los datos de captura originales).
    r = client.delete(f"/api/v1/produccion/consumo/{consumo['id']}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 204), r.text
    assert stock_actual(db, madera["id"]) == Decimal("20.00"), "Reversa debe reponer los m³"
    n = db.execute(text(
        "SELECT COUNT(*) FROM movimiento_inventario WHERE material_id = :m"
    ), {"m": madera["id"]}).scalar()
    assert n >= 2, "Debe quedar el movimiento de reversa (ENTRADA) en el kardex"