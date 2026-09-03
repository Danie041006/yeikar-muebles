"""
test_lamina_pendiente_confirmacion.py
=====================================
Flujo "lámina completa → PENDIENTE → confirmación por cortes":

  1. Pedido de lámina completa: SALIDA de N láminas, costo provisional
     (N × costo_base), gasto provisional, consumo en estado PENDIENTE.
  2. Confirmación con MENOS láminas de las pedidas → ENTRADA de la
     diferencia, costo real por área, sobrante reutilizable, gasto ajustado.
  3. Confirmación con MÁS láminas (stock suficiente) → SALIDA extra.
  4. Confirmación con MÁS láminas sin stock → rechazada (400), sin tocar nada.
  5. Validación dura: material sin dimensiones no puede pedirse por láminas;
     modo lámina completa + medidas de corte → rechazado.
  6. Reversa exacta por DELETE después de confirmar.
  7. El PENDIENTE no bloquea: confirmar con la etapa COMPLETADA.

Ejecutar:  pytest test/test_lamina_pendiente_confirmacion.py -v
"""
import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import text

from conftest import ADMIN_HEADERS

from test_cortes_laminas import (
    crear_material_laminar,
    dar_stock,
    stock_actual,
    registrar_sobrantes_de_material,
    _pedido_con_etapa_en_proceso,
)


def gasto_monto(db, consumo_id) -> Decimal | None:
    row = db.execute(
        text("SELECT monto FROM gasto WHERE observaciones LIKE :m"),
        {"m": f"%[consumo {consumo_id}]%"},
    ).fetchone()
    return Decimal(str(row[0])) if row else None


def pedir_lamina(client, etapa, material_id, cantidad, extra=None):
    payload = {
        "etapa_produccion_id": etapa,
        "material_id": material_id,
        "cantidad": cantidad,
        "es_lamina_completa": True,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
    }
    if extra:
        payload.update(extra)
    return client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)


def confirmar_uso(client, consumo_id, cortes, largo, ancho, extra=None):
    payload = {
        "cantidad_cortes": cortes,
        "largo_corte_cm": largo,
        "ancho_corte_cm": ancho,
    }
    if extra:
        payload.update(extra)
    return client.put(f"/api/v1/produccion/consumo/{consumo_id}/confirmar", json=payload, headers=ADMIN_HEADERS)


# ============================================================================
# 1. Pedido de lámina completa → PENDIENTE
# ============================================================================

def test_pedido_lamina_completa_queda_pendiente_y_descuenta(client, cleaner, db):
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)  # 150×80 cm, $180.000
    dar_stock(client, cleaner, mat["id"], 10)

    r = pedir_lamina(client, etapa, mat["id"], 2)
    assert r.status_code == 201, f"pedido lámina completa → {r.status_code}: {r.text}"
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")

    # Estado PENDIENTE, costo provisional = N láminas × costo_base
    assert consumo["estado"] == "PENDIENTE"
    assert float(consumo["cantidad"]) == 2.0
    assert float(consumo["costo_unitario"]) == 180000.00
    assert consumo.get("ancho_corte_cm") is None

    # Stock: 10 − 2 láminas enteras = 8
    assert stock_actual(db, mat["id"]) == Decimal("8")

    # Gasto provisional = 2 × 180.000 = 360.000
    assert gasto_monto(db, consumo["id"]) == Decimal("360000.00")

    # El estado llega por el endpoint de listado por orden
    r2 = client.get(f"/api/v1/produccion/consumo/por-orden/{orden['id']}", headers=ADMIN_HEADERS)
    assert r2.status_code == 200, r2.text
    assert any(c["id"] == consumo["id"] and c["estado"] == "PENDIENTE" for c in r2.json())


def test_lamina_completa_material_sin_dimensiones_rechazado(client, cleaner):
    from conftest import crear_material
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner)  # sin largo_cm/ancho_cm

    r = pedir_lamina(client, etapa, mat["id"], 1)
    assert r.status_code == 400, r.text
    assert "no tiene dimensiones" in r.json()["detail"]


def test_lamina_completa_no_admite_medidas_de_corte(client, cleaner):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)

    r = pedir_lamina(client, etapa, mat["id"], 1, extra={
        "ancho_corte_cm": 75, "largo_corte_cm": 70,
    })
    assert r.status_code == 400, r.text
    assert "no admite medidas de corte" in r.json()["detail"]


# ============================================================================
# 2. Confirmación con MENOS láminas de las pedidas
# ============================================================================

def test_confirmar_devuelve_laminas_sobrantes_y_ajusta_gasto(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)  # 150×80, $180.000
    dar_stock(client, cleaner, mat["id"], 10)

    r = pedir_lamina(client, etapa, mat["id"], 2)
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")

    # 2 cortes de 75×70: caben 2 por lámina → solo se abre 1 de las 2 pedidas
    r = confirmar_uso(client, consumo["id"], 2, 70, 75)
    assert r.status_code == 200, f"confirmar → {r.status_code}: {r.text}"
    c = r.json()
    registrar_sobrantes_de_material(db, cleaner, mat["id"])

    assert c["estado"] == "CONFIRMADO"
    assert float(c["cantidad"]) == 2.0          # ahora son 2 CORTES
    assert float(c["costo_unitario"]) == 78750.00  # 180000 × (75×70)/12000
    assert float(c["laminas_consumidas"]) == 1.0

    # Stock: 10 − 2 (pedido) + 1 (devolución) = 9
    assert stock_actual(db, mat["id"]) == Decimal("9")

    # Sobrante creado: 12000 − 2×5250 = 1500 cm² (150×10)
    row = db.execute(text(
        "SELECT largo_cm, ancho_cm, estado FROM sobrante_lamina WHERE consumo_origen_id = :c"
    ), {"c": consumo["id"]}).fetchone()
    assert row is not None, "La confirmación debe crear el sobrante reutilizable"
    largo, ancho, estado = row
    assert Decimal(str(largo)) * Decimal(str(ancho)) == Decimal("1500.00")
    assert estado == "DISPONIBLE"

    # Gasto ajustado al costo real: 2 × 78.750 = 157.500
    assert gasto_monto(db, consumo["id"]) == Decimal("157500.00")

    # Confirmar de nuevo → rechazado (ya está CONFIRMADO)
    r2 = confirmar_uso(client, consumo["id"], 1, 70, 75)
    assert r2.status_code == 400, r2.text
    assert "no está pendiente" in r2.json()["detail"]


# ============================================================================
# 3. Confirmación con MÁS láminas de las pedidas (stock suficiente)
# ============================================================================

def test_confirmar_descarta_laminas_extra_si_hay_stock(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 5)

    r = pedir_lamina(client, etapa, mat["id"], 1)
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")
    assert stock_actual(db, mat["id"]) == Decimal("4")

    # 5 cortes de 75×70: caben 2 por lámina → se abren 3 láminas (faltan 2)
    r = confirmar_uso(client, consumo["id"], 5, 70, 75)
    assert r.status_code == 200, f"confirmar → {r.status_code}: {r.text}"
    c = r.json()
    registrar_sobrantes_de_material(db, cleaner, mat["id"])

    assert float(c["laminas_consumidas"]) == 3.0
    assert float(c["costo_unitario"]) == 78750.00
    # Stock: 5 − 1 (pedido) − 2 (faltantes) = 2
    assert stock_actual(db, mat["id"]) == Decimal("2")
    assert gasto_monto(db, consumo["id"]) == Decimal("393750.00")

    # Sobrante: última lámina con 1 corte → restan 6750 cm². El motor propone
    # el rectángulo honesto (redondea hacia abajo): 84.37×80 = 6749.6 cm².
    row = db.execute(text(
        "SELECT largo_cm, ancho_cm FROM sobrante_lamina WHERE consumo_origen_id = :c"
    ), {"c": consumo["id"]}).fetchone()
    assert row is not None
    area = Decimal(str(row[0])) * Decimal(str(row[1]))
    assert Decimal("6749.00") <= area <= Decimal("6750.00")


# ============================================================================
# 4. Confirmación con MÁS láminas SIN stock → rechazada sin tocar nada
# ============================================================================

def test_confirmar_sin_stock_suficiente_rechazado(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 1)

    r = pedir_lamina(client, etapa, mat["id"], 1)
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")
    assert stock_actual(db, mat["id"]) == Decimal("0")

    # 5 cortes → necesitan 3 láminas → faltan 2 y el depósito está vacío
    r = confirmar_uso(client, consumo["id"], 5, 70, 75)
    assert r.status_code == 400, r.text
    assert "faltan" in r.json()["detail"]

    # Nada cambió: sigue PENDIENTE, sin sobrante, gasto provisional intacto
    row = db.execute(text(
        "SELECT estado FROM consumo_material WHERE id = :c"
    ), {"c": consumo["id"]}).fetchone()
    assert row[0] == "PENDIENTE"
    n = db.execute(text(
        "SELECT COUNT(*) FROM sobrante_lamina WHERE consumo_origen_id = :c"
    ), {"c": consumo["id"]}).scalar()
    assert n == 0
    assert gasto_monto(db, consumo["id"]) == Decimal("180000.00")


# ============================================================================
# 5. Confirmación manual del sobrante (dimensiones editadas por el operario)
# ============================================================================

def test_confirmar_con_sobrante_manual(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 10)

    r = pedir_lamina(client, etapa, mat["id"], 1)
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")

    r = confirmar_uso(client, consumo["id"], 2, 70, 75, extra={
        "sobrante_largo_cm": 80, "sobrante_ancho_cm": 18,
    })
    assert r.status_code == 200, r.text
    registrar_sobrantes_de_material(db, cleaner, mat["id"])
    row = db.execute(text(
        "SELECT largo_cm, ancho_cm FROM sobrante_lamina WHERE consumo_origen_id = :c"
    ), {"c": consumo["id"]}).fetchone()
    assert row is not None
    assert float(row[0]) == 80.0 and float(row[1]) == 18.0


# ============================================================================
# 6. Reversa exacta por DELETE después de confirmar
# ============================================================================

def test_delete_despues_de_confirmar_revierte_exacto(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 10)

    r = pedir_lamina(client, etapa, mat["id"], 2)
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")
    registrar_sobrantes_de_material(db, cleaner, mat["id"])

    r = confirmar_uso(client, consumo["id"], 2, 70, 75)
    assert r.status_code == 200, r.text
    assert stock_actual(db, mat["id"]) == Decimal("9")

    r = client.delete(f"/api/v1/produccion/consumo/{consumo['id']}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 204), r.text

    # Reversa del corte: entra la lámina consumida (la devuelta ya había entrado)
    assert stock_actual(db, mat["id"]) == Decimal("10")
    n = db.execute(text(
        "SELECT COUNT(*) FROM sobrante_lamina WHERE consumo_origen_id = :c"
    ), {"c": consumo["id"]}).scalar()
    assert n == 0, "El DELETE debe borrar el sobrante generado por la confirmación"
    assert gasto_monto(db, consumo["id"]) is None, "El DELETE debe revertir el gasto"


# ============================================================================
# 7. PENDIENTE no bloquea: confirmar aunque la etapa esté COMPLETADA
# ============================================================================

def test_confirmar_con_etapa_completada_permitido(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 5)

    r = pedir_lamina(client, etapa, mat["id"], 1)
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")

    # La etapa se completa con el consumo pendiente (no bloquea nada)
    r = client.put(f"/api/v1/produccion/etapa/{etapa}/estado",
                   params={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    r = confirmar_uso(client, consumo["id"], 2, 70, 75)
    assert r.status_code == 200, f"confirmar con etapa COMPLETADA → {r.status_code}: {r.text}"
    assert r.json()["estado"] == "CONFIRMADO"
    registrar_sobrantes_de_material(db, cleaner, mat["id"])