"""
test_cortes_laminas.py
======================
Sistema de cortes de láminas (SIN sobrantes: el inventario de retazos fue
retirado del sistema — ya no se crean, ni se consumen, ni se reponen).

  1. Matemática pura del motor (cortes por lámina, ambas orientaciones,
     láminas necesarias, costo proporcional).
  2. Consumo por cortes desde LÁMINA NUEVA (service) → descuenta láminas
     enteras; NO registra sobrantes.
  3. Los cortes "desde sobrante" de clientes viejos se RECHAZAN con mensaje.
  4. Reversa al eliminar el consumo (reingreso de láminas).
  5. Integración vía API: consumo en etapa EN_PROCESO con medidas de corte.
  6. Costeo paramétrico: receta CORTE escala por área y costo proporcional.
  7. Regresión: el flujo legacy (sin cortes) sigue intacto.

Ejecutar:  pytest test/test_cortes_laminas.py -v
"""
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_orden_desde_pedido,
    registrar_venta_de_pedido,
)

# ============================================================================
# 1. Motor de matemática pura (sin BD)
# ============================================================================

def test_cortes_por_lamina_orientaciones():
    from app.modules.inventory.laminas import cortes_que_caban
    # Lámina de prueba 150×80, corte 75×70: directo 2×1=2; rotado 2×1=2 → 2
    assert cortes_que_caban(150, 80, 75, 70) == 2
    # Lámina estándar 244×183, corte 80×130: directo 3×1=3; rotado 2×1=2 → 3
    assert cortes_que_caban(244, 183, 80, 130) == 3
    # Corte que NO cabe de ninguna forma
    assert cortes_que_caban(150, 80, 200, 200) == 0


def test_laminas_necesarias_redondeo_hacia_arriba():
    from app.modules.inventory.laminas import laminas_necesarias
    assert laminas_necesarias(1, 2) == 1
    assert laminas_necesarias(2, 2) == 1
    assert laminas_necesarias(3, 2) == 2
    assert laminas_necesarias(5, 3) == 2


def test_costo_proporcional_al_area():
    from app.modules.inventory.laminas import costo_por_corte
    # Lámina de 150×80=12000 cm² a $180.000 → 1 cm² = $15
    costo = costo_por_corte(Decimal("180000"), Decimal("6000"), Decimal("12000"))
    assert costo == Decimal("90000.00")  # mitad de lámina


# ============================================================================
# Helpers de material laminar (los importan otros tests del taller)
# ============================================================================

def crear_material_laminar(client, cleaner, nombre=None, largo=150, ancho=80, costo=180000.0):
    """Material laminar de prueba: lámina de 150×80 cm (área 12000 cm²)."""
    from conftest import _uniq
    payload = {
        "nombre": nombre or _uniq("lam"),
        "unidad_medida_id": 2,
        "costo_base": costo,
        "largo_cm": largo,
        "ancho_cm": ancho,
    }
    r = client.post("/api/v1/material/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear material laminar → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("material", body["id"])
    return body


def dar_stock(client, cleaner, material_id, cantidad):
    from conftest import crear_movimiento
    r, body = crear_movimiento(client, cleaner, material_id, "ENTRADA", cantidad)
    assert r.status_code in (200, 201), f"ENTRADA stock → {r.status_code}: {body}"
    return body


def stock_actual(db, material_id):
    row = db.execute(
        text("SELECT cantidad FROM inventario WHERE material_id = :m"),
        {"m": material_id},
    ).fetchone()
    return Decimal(str(row[0])) if row else Decimal("0")


def registrar_sobrantes_de_material(db, cleaner, material_id):
    """Helper de limpieza: registra en el cleaner los retazos históricos del
    material (la tabla quedó congelada; los flujos nuevos ya no crean filas)."""
    for (sid,) in db.execute(
        text("SELECT id FROM sobrante_lamina WHERE material_id = :m"), {"m": material_id}
    ).fetchall():
        cleaner._ids.setdefault("sobrante_lamina", set()).add(int(sid))


# ============================================================================
# 2-4. Servicio de cortes (consumir_por_cortes / revertir)
# ============================================================================

def test_consumo_lamina_nueva_descuenta_laminas_sin_sobrante(client, cleaner, db):
    from app.modules.inventory.cortes_service import consumir_por_cortes, revertir_consumo_por_cortes
    from app.modules.productos.model import Material

    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 10)
    material = db.query(Material).filter(Material.id == mat["id"]).first()

    # 2 cortes de 75×70 → caben 2 por lámina → 1 lámina entera
    res = consumir_por_cortes(
        db, material=material, cantidad_cortes=2,
        largo_corte_cm=70, ancho_corte_cm=75,
        ubicacion_id=1, referencia_tipo="produccion", referencia_id=999001,
    )
    db.flush()
    assert res["laminas_consumidas"] == 1
    assert res["costo_unitario"] == Decimal("78750.00")  # 180000 × (75×70)/12000
    assert res["costo_total"] == Decimal("157500.00")
    assert "sobrante" not in res, "el motor de cortes ya no produce sobrantes"
    assert stock_actual(db, mat["id"]) == Decimal("9")

    # NO se registra ningún retazo reutilizable (feature retirada)
    n = db.execute(text(
        "SELECT COUNT(*) FROM sobrante_lamina WHERE consumo_origen_id = 999001"
    )).scalar()
    assert n == 0, "el consumo por cortes no debe crear sobrantes"

    # Reversa: vuelve la lámina (sin sobrantes que borrar)
    detalle = revertir_consumo_por_cortes(
        db, material=material, consumo_id=999001, consumo_tipo="produccion",
        largo_corte_cm=70, ancho_corte_cm=75,
        laminas_consumidas=1, ubicacion_id=1,
    )
    db.flush()
    assert stock_actual(db, mat["id"]) == Decimal("10")
    assert "Reversa" in detalle


def test_corte_mas_grande_que_lamina_rechazado(client, cleaner, db):
    from app.modules.inventory.cortes_service import consumir_por_cortes
    from app.modules.productos.model import Material

    mat = crear_material_laminar(client, cleaner, largo=150, ancho=80)
    dar_stock(client, cleaner, mat["id"], 3)
    material = db.query(Material).filter(Material.id == mat["id"]).first()
    with pytest.raises(ValueError, match="no cabe"):
        consumir_por_cortes(
            db, material=material, cantidad_cortes=1,
            largo_corte_cm=200, ancho_corte_cm=200,
            ubicacion_id=1, referencia_tipo="produccion", referencia_id=999005,
        )


def test_material_no_laminar_rechaza_cortes(client, cleaner, db):
    from app.modules.inventory.cortes_service import consumir_por_cortes
    from app.modules.productos.model import Material

    mat = crear_material(client, cleaner)  # sin dimensiones → no laminar
    material = db.query(Material).filter(Material.id == mat["id"]).first()
    with pytest.raises(ValueError, match="no tiene dimensiones"):
        consumir_por_cortes(
            db, material=material, cantidad_cortes=1,
            largo_corte_cm=80, ancho_corte_cm=80,
            ubicacion_id=1, referencia_tipo="produccion", referencia_id=999006,
        )


# ============================================================================
# 5. Integración vía API: consumo en etapa con medidas de corte
# ============================================================================

def _pedido_con_etapa_en_proceso(client, cleaner):
    cli = crear_cliente(client, cleaner)
    prod = crear_producto_simple(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100_000)
    r = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 100_000}]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    orden = crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])
    r = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 3, "estado": "ASIGNADA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    etapa = r.json()["id"]
    cleaner.registrar("etapa_produccion", etapa)
    r = client.put(f"/api/v1/produccion/etapa/{etapa}/estado",
                   params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return ped, orden, etapa


def crear_producto_simple(client, cleaner, nombre=None):
    from conftest import _uniq
    payload = {
        "nombre": nombre or _uniq("prod"),
        "tipo_producto_id": 1,
        "ancho_base": 1.60,
        "largo_base": 1.90,
    }
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    body = r.json()
    cleaner.registrar("producto", body["id"])
    return body


def test_api_consumo_con_cortes_y_reversa(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 10)

    payload = {
        "etapa_produccion_id": etapa,
        "material_id": mat["id"],
        "cantidad": 2,
        "ancho_corte_cm": 75,
        "largo_corte_cm": 70,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
    }
    r = client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"consumo con cortes → {r.status_code}: {r.text}"
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")

    # El consumo guarda las medidas y el costo POR CORTE (no de la lámina)
    assert float(consumo["ancho_corte_cm"]) == 75.0
    assert float(consumo["largo_corte_cm"]) == 70.0
    assert float(consumo["costo_unitario"]) == 78750.00
    assert float(consumo["laminas_consumidas"]) == 1.0

    # Stock: 10 − 1 lámina = 9
    assert stock_actual(db, mat["id"]) == Decimal("9")

    # Sin sobrantes: el pedazo restante ya no se inventaría
    n = db.execute(text(
        "SELECT COUNT(*) FROM sobrante_lamina WHERE consumo_origen_id = :c"
    ), {"c": consumo["id"]}).scalar()
    assert n == 0, "el consumo por cortes ya no debe crear sobrantes"

    # Kardex: la SALIDA es de 1 lámina (no de 2 "cortes")
    kardex = client.get(f"/api/v1/inventario/movimientos/material/{mat['id']}", headers=ADMIN_HEADERS).json()
    salidas = [m for m in kardex if m["tipo"] == "SALIDA"]
    assert len(salidas) == 1
    assert float(salidas[0]["cantidad"]) == 1.0

    # ── Reversa vía DELETE ────────────────────────────────────────────────
    r = client.delete(f"/api/v1/produccion/consumo/{consumo['id']}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 204), r.text
    assert stock_actual(db, mat["id"]) == Decimal("10"), "La reversa debe reponer la lámina"


def test_api_corte_desde_sobrante_rechazado(client, cleaner, db):
    """Un cliente viejo que mande origen_sobrante_id recibe un 400 claro (los
    sobrantes de lámina ya no existen): no se descuenta nada en silencio."""
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 4)

    payload = {
        "etapa_produccion_id": etapa,
        "material_id": mat["id"],
        "cantidad": 2,
        "ancho_corte_cm": 50,
        "largo_corte_cm": 50,
        "origen_sobrante_id": 999999,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
    }
    r = client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"corte desde sobrante debe rechazarse → {r.status_code}: {r.text}"
    assert "ya no está disponible" in r.json()["detail"]
    assert stock_actual(db, mat["id"]) == Decimal("4"), "el rechazo no debe tocar el stock"


# ============================================================================
# 6. Costeo paramétrico con receta CORTE
# ============================================================================

def test_costeo_receta_corte_proporcional(client, cleaner, db):
    from conftest import crear_receta

    prod = crear_producto_simple(client, cleaner)
    mat = crear_material_laminar(client, cleaner, costo=180000.0, largo=150, ancho=80)
    # 2 cortes de 75×70 a medidas base
    receta = crear_receta(client, cleaner, prod["id"], mat["id"], 2, tipo_escala="CORTE")
    # La receta debe aceptar (y guardar) las medidas del corte
    r = client.put(f"/api/v1/receta/{receta['id']}", json={
        "ancho_corte_cm": 75, "largo_corte_cm": 70,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    r = client.post(f"/api/v1/producto/{prod['id']}/calcular-precio", params={
        "ancho": 1.60, "largo": 1.90, "ganancia": 0, "iva": 0,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    lineas = [m for m in body["materiales"] if m["material_id"] == mat["id"]]
    assert lineas, "La receta CORTE debe aparecer en el desglose"
    linea = lineas[0]
    assert linea.get("es_corte") is True
    assert float(linea["cantidad_calculada"]) == 2.0
    assert float(linea["costo_unitario"]) == 78750.00  # por corte
    assert float(linea["costo_total"]) == 157500.00
    assert abs(linea["laminas_equivalentes"] - 0.875) < 1e-6  # 10500/12000

    # Escala por área: doble de área → doble de cortes
    r2 = client.post(f"/api/v1/producto/{prod['id']}/calcular-precio", params={
        "ancho": 3.20, "largo": 1.90, "ganancia": 0, "iva": 0,
    }, headers=ADMIN_HEADERS)
    assert r2.status_code == 200
    linea2 = [m for m in r2.json()["materiales"] if m["material_id"] == mat["id"]][0]
    assert abs(float(linea2["cantidad_calculada"]) - 4.0) < 1e-6


# ============================================================================
# 7. Regresión: flujo legacy sin cortes intacto + sobrantes desactivados
# ============================================================================

def test_regresion_consumo_legacy_sin_cortes(client, cleaner, db):
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=1000.0)
    dar_stock(client, cleaner, mat["id"], 20)

    payload = {
        "etapa_produccion_id": etapa,
        "material_id": mat["id"],
        "cantidad": 3,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
    }
    r = client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")

    assert float(consumo["costo_unitario"]) == 1000.0
    assert consumo.get("ancho_corte_cm") is None
    assert stock_actual(db, mat["id"]) == Decimal("17")


def test_endpoints_sobrantes_desactivados(client, cleaner, db):
    """Los endpoints de sobrantes ya no existen (feature retirada)."""
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 5)

    r = client.get("/api/v1/inventario/sobrantes", headers=ADMIN_HEADERS)
    assert r.status_code == 404
    r = client.post("/api/v1/inventario/sobrantes", json={
        "material_id": mat["id"], "ubicacion_id": 1,
        "largo_cm": 120, "ancho_cm": 40,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 404


def test_categorias_de_inventario_siguen_intactas(client, cleaner, db):
    mat = crear_material_laminar(client, cleaner)
    dar_stock(client, cleaner, mat["id"], 5)

    # Categorías de material: el catálogo existe y se puede asignar una
    # (los nombres dependen de la configuración de cada BD).
    r = client.get("/api/v1/inventario/categorias", params={"tipo": "MATERIAL"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    cats = r.json()
    assert cats, "debe existir al menos una categoría de MATERIAL"

    cat = cats[0]
    r = client.put(f"/api/v1/material/{mat['id']}", json={"categoria_inventario_id": cat["id"]},
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/inventario/", params={"material_id": mat["id"]}, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    items = r.json()
    assert items, "El material de prueba debe tener stock"
    assert items[0]["material_largo_cm"] == "150.00" or float(items[0]["material_largo_cm"]) == 150.0
    assert items[0]["categoria_inventario_nombre"] == cat["nombre"]
