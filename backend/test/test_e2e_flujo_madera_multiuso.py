"""
test_e2e_flujo_madera_multiuso.py — E2E del flujo REAL de producción con
madera multi-uso.

Ejercita la cadena completa sobre una etapa EN_PROCESO:

  1. Consumos DIRECTOS de varios materiales: una lámina por corte (motor de
     láminas + sobrante) y un material simple.
  2. Pedido ABIERTO de madera volumétrica (es_pedido=True sin cantidad): nace
     PENDIENTE sin tocar stock ni gasto.
  3. Confirmación MULTI-uso del pedido abierto con usos MIXTOS: una línea en
     cm (cuenta del taller) + dos piezas de tamaños distintos. Cada uso queda
     como consumo CONFIRMADO propio con su etiqueta, su movimiento y su gasto.
  4. Verificación contra BD (stock, filas, gastos) y contra la API
     (costos-en-vivo: un renglón por uso, cada uno con su `captura`).
  5. Retrocompatibilidad: confirmación individual legacy (cantidad_usada) en
     modo pieza.

Ejecutar:  pytest test/test_e2e_flujo_madera_multiuso.py -v
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
    _pedido_con_etapa_en_proceso,
    crear_material_laminar,
    dar_stock,
    registrar_sobrantes_de_material,
    stock_actual,
)

from test_pedido_uso_material import (
    confirmar_uso,
    confirmar_usos,
    gasto_monto,
    pedir,
    usar_directo,
)

UNIDAD_M = 2
UNIDAD_M3 = 193

COSTO_LAMINAR = 180000.0
COSTO_SIMPLE = 1000.0
COSTO_MADERA = 5000.0

# Etiquetas esperadas de los usos mixtos (motor de unidades.py).
ETIQUETA_CM = "1500 cm (cuenta del taller)"
ETIQUETA_PIEZA_1 = "Pieza 2×10×5 × 2"
ETIQUETA_PIEZA_2 = "Pieza 3×20×4 × 1"


# ---------------------------------------------------------------------------
# Helpers locales (solo registro en cleaner + lecturas; nada de infra nueva)
# ---------------------------------------------------------------------------

def _gastos_de_consumo(db, consumo_id):
    """Todos los gastos automáticos marcados con [consumo {id}]."""
    rows = db.execute(
        text("SELECT monto FROM gasto WHERE observaciones LIKE :p"),
        {"p": f"%[consumo {consumo_id}]%"},
    ).fetchall()
    return [Decimal(str(r[0])) for r in rows]


def _registrar_consumo(cleaner, db, consumo_id, material_id):
    """Registra un consumo, su gasto automático y todo el rastro de inventario
    del material (los hermanos del multi-uso se registran aparte)."""
    cleaner.registrar("consumo_material", consumo_id)
    cleaner.registrar_gastos_like(db, f"[consumo {consumo_id}]")
    registrar_inventario_de_material(db, cleaner, material_id)


def _registrar_todo_de_etapa(cleaner, db, etapa_id):
    """Registra TODOS los consumos de la etapa (cabeza + hermanos del multi-uso)
    con sus gastos automáticos."""
    rows = db.execute(
        text("SELECT id FROM consumo_material WHERE etapa_produccion_id = :e"),
        {"e": etapa_id},
    ).fetchall()
    for (cid,) in rows:
        cleaner.registrar("consumo_material", cid)
        cleaner.registrar_gastos_like(db, f"[consumo {cid}]")


def _material_con_stock(client, cleaner, db, *, costo, unidad_medida_id, stock, laminar=False):
    """Crea el material (laminar o simple) con stock inicial y lo registra."""
    if laminar:
        mat = crear_material_laminar(client, cleaner, costo=costo)
        dar_stock(client, cleaner, mat["id"], stock)
        registrar_sobrantes_de_material(db, cleaner, mat["id"])
    else:
        mat = crear_material(client, cleaner, costo_base=costo, unidad_medida_id=unidad_medida_id)
        crear_movimiento(client, cleaner, mat["id"], "ENTRADA", stock)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    return mat


def _consumos_de_etapa(db, etapa_id):
    """Filas crudas de consumo_material de la etapa (para verificar en BD)."""
    return db.execute(
        text(
            "SELECT id, material_id, cantidad, estado, detalle_uso, cantidad_pedida"
            " FROM consumo_material WHERE etapa_produccion_id = :e ORDER BY id"
        ),
        {"e": etapa_id},
    ).fetchall()


def _insumos_en_vivo(client, orden_id):
    r = client.get(
        f"/api/v1/produccion/orden/{orden_id}/costos-en-vivo", headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, f"costos-en-vivo → {r.status_code}: {r.text}"
    return [i for s in r.json()["secciones"] for i in s["insumos"]]


# ============================================================================
# 1-2-4. Flujo E2E: directos + pedido abierto confirmado con usos mixtos
# ============================================================================

def test_e2e_flujo_madera_multiuso(client, cleaner, db):
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)

    lam = _material_con_stock(
        client, cleaner, db,
        costo=COSTO_LAMINAR, unidad_medida_id=UNIDAD_M, stock=10, laminar=True,
    )
    simple = _material_con_stock(
        client, cleaner, db,
        costo=COSTO_SIMPLE, unidad_medida_id=UNIDAD_M, stock=20,
    )
    mad = _material_con_stock(
        client, cleaner, db,
        costo=COSTO_MADERA, unidad_medida_id=UNIDAD_M3, stock=5,
    )

    # --- 1a. Consumo DIRECTO: lámina por corte (2 cortes 75×70 → 1 lámina) ---
    r = client.post("/api/v1/produccion/consumo/", json={
        "etapa_produccion_id": etapa,
        "material_id": lam["id"],
        "cantidad": 2,
        "ancho_corte_cm": 75,
        "largo_corte_cm": 70,
        "solicitante_empleado_id": 3,
        "fecha": datetime.utcnow().isoformat(),
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"consumo lámina por corte → {r.status_code}: {r.text}"
    consumo_lam = r.json()
    _registrar_consumo(cleaner, db, consumo_lam["id"], lam["id"])
    registrar_sobrantes_de_material(db, cleaner, lam["id"])
    db.expire_all()
    assert consumo_lam["estado"] == "CONFIRMADO"
    assert consumo_lam["cantidad_pedida"] is None
    assert stock_actual(db, lam["id"]) == Decimal("9"), "10 − 1 lámina abierta"
    assert gasto_monto(db, consumo_lam["id"]) == Decimal("157500.00")

    # --- 1b. Consumo DIRECTO: material simple (3 m) ---
    r = usar_directo(client, etapa, simple["id"], 3)
    assert r.status_code == 201, f"uso directo simple → {r.status_code}: {r.text}"
    consumo_simple = r.json()
    _registrar_consumo(cleaner, db, consumo_simple["id"], simple["id"])
    db.expire_all()
    assert consumo_simple["estado"] == "CONFIRMADO"
    assert stock_actual(db, simple["id"]) == Decimal("17"), "20 − 3"
    assert gasto_monto(db, consumo_simple["id"]) == Decimal("3000.00")

    # --- 1c. Pedido ABIERTO de madera: es_pedido sin cantidad ---
    r = pedir(client, etapa, mad["id"], None)
    assert r.status_code == 201, f"pedido abierto → {r.status_code}: {r.text}"
    pedido_madera = r.json()
    _registrar_consumo(cleaner, db, pedido_madera["id"], mad["id"])
    db.expire_all()
    assert pedido_madera["estado"] == "PENDIENTE"
    assert float(pedido_madera["cantidad"]) == 0.0
    assert pedido_madera["cantidad_pedida"] is None, "abierto: sin cantidad pedida"
    assert stock_actual(db, mad["id"]) == Decimal("5"), "abierto no toca stock"
    assert gasto_monto(db, pedido_madera["id"]) is None, "abierto no genera gasto"

    # --- 2. Confirmar con usos MIXTOS: cm + dos piezas de distinto tamaño ---
    r = confirmar_usos(client, pedido_madera["id"], [
        {"cantidad": 1500, "unidad_captura": "CM"},                                # 1500 ÷ 10000 = 0.15
        {"cantidad": 2, "pieza_largo": 2, "pieza_ancho": 10, "pieza_espesor": 5},  # 0.02
        {"cantidad": 1, "pieza_largo": 3, "pieza_ancho": 20, "pieza_espesor": 4},  # 0.024
    ])
    assert r.status_code == 200, f"confirmar usos mixtos → {r.status_code}: {r.text}"
    conf = r.json()
    _registrar_todo_de_etapa(cleaner, db, etapa)
    registrar_inventario_de_material(db, cleaner, mad["id"])
    db.expire_all()

    # 4. La cabeza (pedido abierto) queda con la base del uso 1 y pedida NULL.
    assert conf["estado"] == "CONFIRMADO"
    assert abs(float(conf["cantidad"]) - 0.15) < 1e-6, conf["cantidad"]
    assert conf["cantidad_pedida"] is None
    assert conf["detalle_uso"] == ETIQUETA_CM
    assert conf["unidad_captura"] == "CM"

    # Tres filas CONFIRMADO en BD, cada uso con su etiqueta y su cantidad base.
    filas_mad = [f for f in _consumos_de_etapa(db, etapa) if f[1] == mad["id"]]
    assert len(filas_mad) == 3, filas_mad
    assert {f[3] for f in filas_mad} == {"CONFIRMADO"}
    assert {f[4] for f in filas_mad} == {ETIQUETA_CM, ETIQUETA_PIEZA_1, ETIQUETA_PIEZA_2}
    assert {float(f[2]) for f in filas_mad} == {0.15, 0.02, 0.024}
    assert all(f[5] is None for f in filas_mad), "pedido abierto: pedida NULL en todos"

    # Cada uso tiene SU PROPIO movimiento de inventario (SALIDA ligada al consumo).
    for f in filas_mad:
        movs = db.execute(
            text(
                "SELECT tipo, cantidad FROM movimiento_inventario"
                " WHERE material_id = :m AND referencia_tipo = 'produccion'"
                " AND referencia_id = :r"
            ),
            {"m": mad["id"], "r": f[0]},
        ).fetchall()
        assert len(movs) == 1 and movs[0][0] == "SALIDA", (f, movs)
        assert abs(float(movs[0][1]) - float(f[2])) < 1e-6, (f, movs)

    # Stock exacto: 5 − (0.15 + 0.02 + 0.024) = 4.806.
    assert stock_actual(db, mad["id"]) == Decimal("4.806"), stock_actual(db, mad["id"])

    # Gastos: exactamente uno por uso, suman exactamente total × costo_base.
    gasto_por_etiqueta = {}
    for f in filas_mad:
        montos = _gastos_de_consumo(db, f[0])
        assert len(montos) == 1, (f, montos)
        gasto_por_etiqueta[f[4]] = montos[0]
    assert gasto_por_etiqueta[ETIQUETA_CM] == Decimal("750.00")
    assert gasto_por_etiqueta[ETIQUETA_PIEZA_1] == Decimal("100.00")
    assert gasto_por_etiqueta[ETIQUETA_PIEZA_2] == Decimal("120.00")
    assert sum(gasto_por_etiqueta.values()) == Decimal("970.00"), gasto_por_etiqueta

    # Costos en vivo: 3 renglones para la madera, cada uno con su captura.
    insumos = _insumos_en_vivo(client, orden["id"])
    mad_vivo = [i for i in insumos if i["nombre"] == mad["nombre"]]
    assert len(mad_vivo) == 3, mad_vivo
    assert {i["captura"] for i in mad_vivo} == {ETIQUETA_CM, ETIQUETA_PIEZA_1, ETIQUETA_PIEZA_2}
    assert {i["unidad"] for i in mad_vivo} == {"m³"}
    assert {i["v_unit"] for i in mad_vivo} == {5000.0}
    assert all(i["es_pendiente"] is False for i in mad_vivo)
    assert all(i["cantidad_pedida"] is None for i in mad_vivo)
    assert abs(sum(i["total"] for i in mad_vivo) - 970.0) < 0.01, mad_vivo
    assert abs(
        sum(i["cantidad"] * i["v_unit"] for i in mad_vivo) - sum(i["total"] for i in mad_vivo)
    ) < 0.01

    # Los otros dos materiales también aparecen correctamente en costos.
    lam_vivo = [i for i in insumos if i["nombre"] == lam["nombre"]]
    assert len(lam_vivo) == 1, lam_vivo
    assert lam_vivo[0]["unidad"] == "m"
    assert abs(lam_vivo[0]["cantidad"] - 2.0) < 1e-6, "cantidad = n.º de cortes"
    assert abs(lam_vivo[0]["v_unit"] - 78750.0) < 0.01, "costo por corte proporcional"
    assert abs(lam_vivo[0]["total"] - 157500.0) < 0.01

    simple_vivo = [i for i in insumos if i["nombre"] == simple["nombre"]]
    assert len(simple_vivo) == 1, simple_vivo
    assert simple_vivo[0]["unidad"] == "m"
    assert abs(simple_vivo[0]["cantidad"] - 3.0) < 1e-6
    assert abs(simple_vivo[0]["total"] - 3000.0) < 0.01


# ============================================================================
# 3. Retrocompatibilidad: confirmación individual legacy (cantidad_usada)
# ============================================================================

def test_e2e_retrocompat_confirmacion_individual_pieza(client, cleaner, db):
    """El formato legacy de una sola línea (`cantidad_usada` + medidas de
    pieza) sigue funcionando y deja UN solo consumo confirmado con captura."""
    _, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mad = _material_con_stock(
        client, cleaner, db,
        costo=COSTO_MADERA, unidad_medida_id=UNIDAD_M3, stock=5,
    )

    r = pedir(client, etapa, mad["id"], None)
    assert r.status_code == 201, f"pedido abierto → {r.status_code}: {r.text}"
    pedido_madera = r.json()
    _registrar_consumo(cleaner, db, pedido_madera["id"], mad["id"])

    r = confirmar_uso(client, pedido_madera["id"], 2, extra={
        "pieza_largo": 2, "pieza_ancho": 10, "pieza_espesor": 5,
    })
    assert r.status_code == 200, f"confirmar legacy → {r.status_code}: {r.text}"
    conf = r.json()
    _registrar_consumo(cleaner, db, conf["id"], mad["id"])
    registrar_inventario_de_material(db, cleaner, mad["id"])
    db.expire_all()

    # (2×10×5) × 2 ÷ 10000 = 0.02 m³.
    assert conf["estado"] == "CONFIRMADO"
    assert abs(float(conf["cantidad"]) - 0.02) < 1e-6, conf["cantidad"]
    assert conf["cantidad_pedida"] is None
    assert conf["detalle_uso"] == ETIQUETA_PIEZA_1
    assert float(conf["pieza_largo"]) == 2.0
    assert float(conf["pieza_ancho"]) == 10.0
    assert float(conf["pieza_espesor"]) == 5.0

    filas_mad = [f for f in _consumos_de_etapa(db, etapa) if f[1] == mad["id"]]
    assert len(filas_mad) == 1, filas_mad
    assert filas_mad[0][3] == "CONFIRMADO"
    assert filas_mad[0][4] == ETIQUETA_PIEZA_1

    assert stock_actual(db, mad["id"]) == Decimal("4.98"), "5 − 0.02"
    assert gasto_monto(db, conf["id"]) == Decimal("100.00")

    insumos = _insumos_en_vivo(client, orden["id"])
    mad_vivo = [i for i in insumos if i["nombre"] == mad["nombre"]]
    assert len(mad_vivo) == 1, mad_vivo
    assert mad_vivo[0]["captura"] == ETIQUETA_PIEZA_1
    assert mad_vivo[0]["es_pendiente"] is False
    assert abs(mad_vivo[0]["total"] - 100.0) < 0.01
