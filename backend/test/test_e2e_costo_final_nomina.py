"""
test_e2e_costo_final_nomina.py
==============================
E2E del COSTO FINAL de producción cuando la madera se pide ABIERTA (sin
cantidad) y se confirma con VARIOS usos (cm + piezas de tamaños distintos), y
del tramo de ese costo que alimenta la NÓMINA (mano de obra de la etapa).

Flujo real simulado, TODO por API + SQL de verificación:
  1. pedido → orden → etapa EN_PROCESO con madera m³ (unidad 193, $5000/m³).
  2. Mano de obra de la etapa: $10.000 con recargo 8% (=> $10.800).
  3. Pedido ABIERTO de madera → confirmación multi-uso:
       1500 cm (cuenta del taller)  = 0.150 m³
       Pieza 2×10×5 × 2             = 0.020 m³
       Pieza 3×20×4 × 1             = 0.024 m³
       TOTAL                        = 0.194 m³ → 0.194 × 5000 = $970
  4. costos-en-vivo: un renglón aislado por uso + MO con recargo, sumas exactas.
  5. FINALIZADA: costo guardado = 970 + 10.800 = 11.770 (costo_gastos 0) y
     estructura generada (ElementoSeccion 0.194 @5000, CostoProduccionSeccion
     10.000 @8%). El snapshot del producto aplica además el 10% de gastos de
     la sección (12.947), igual que la vista en vivo.
  6. Nómina: la MISMA fila de ManoObra que costea la orden alimenta el destajo
     (nomina/service._obtener_manos_obra_periodo): la línea del preview debe
     valer EXACTAMENTE lo mismo que costo_mano_obra ($10.800).

Ejecutar:  pytest test/test_e2e_costo_final_nomina.py -v
"""
import os
import sys
from datetime import timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_material,
    crear_movimiento,
    registrar_inventario_de_material,
)
from helpers_e2e import (
    cargos,
    crear_empleado,
    hoy,
    preview_nomina,
    semana_actual,
)
from test_cortes_laminas import (
    _pedido_con_etapa_en_proceso,
    stock_actual,
)
from test_pedido_uso_material import (
    confirmar_usos,
    gasto_monto,
    pedir,
)

# ── Escenario ────────────────────────────────────────────────────────────────
COSTO_BASE_M3 = 5000.0
STOCK_M3 = 5
MO_MONTO = 10000.0
MO_RECARGO = 8.0
MO_TOTAL = 10800.0                # 10.000 × (1 + 8/100)
USOS = [
    {"cantidad": 1500, "unidad_captura": "CM"},                                # 0.150 m³
    {"cantidad": 2, "pieza_largo": 2, "pieza_ancho": 10, "pieza_espesor": 5},  # 0.020 m³
    {"cantidad": 1, "pieza_largo": 3, "pieza_ancho": 20, "pieza_espesor": 4},  # 0.024 m³
]
MADERA_M3 = Decimal("0.194")
COSTO_MADERA = 970.0              # 0.194 × 5000
COSTO_TOTAL_FLAT = 11770.0        # 970 + 10.800 (sin gastos de sección)
GASTO_SECCION_10 = 1177.0         # 10% de 11.770 (regla EBANISTERIA)
TOTAL_CON_GASTOS = 12947.0        # 11.770 × 1.10 (vista en vivo / snapshot)


def _consumos_de_etapa(db, etapa_id):
    return db.execute(
        text(
            "SELECT id, cantidad, estado, detalle_uso, cantidad_pedida"
            " FROM consumo_material WHERE etapa_produccion_id = :e ORDER BY id"
        ),
        {"e": etapa_id},
    ).fetchall()


def _registrar_rastro_etapa(db, cleaner, etapa_id):
    """Registra consumos (cabeza + hermanos) y sus gastos automáticos en el
    cleaner. Se llama tras CADA mutación para que el teardown limpie incluso si
    un assert posterior falla."""
    ids = []
    for (cid,) in db.execute(
        text("SELECT id FROM consumo_material WHERE etapa_produccion_id = :e"),
        {"e": etapa_id},
    ).fetchall():
        ids.append(int(cid))
        cleaner.registrar("consumo_material", cid)
        cleaner.registrar_gastos_like(db, f"[consumo {cid}]")
    return ids


def _registrar_envio_y_costo(db, cleaner, pedido_id, orden_id):
    row = db.execute(
        text("SELECT id FROM envio WHERE pedido_id = :p"), {"p": pedido_id}
    ).fetchone()
    if row:
        cleaner.registrar("envio", row[0])
    row = db.execute(
        text("SELECT id FROM costo_produccion WHERE orden_produccion_id = :o"),
        {"o": orden_id},
    ).fetchone()
    if row:
        cleaner.registrar("costo_produccion", row[0])


def test_costo_final_multi_uso_madera_alimenta_nomina(client, cleaner, db):
    # ── 1. Montaje: pedido → orden → etapa EN_PROCESO + madera m³ con stock ──
    ped, orden, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=COSTO_BASE_M3, unidad_medida_id=193)
    r, _ = crear_movimiento(client, cleaner, mat["id"], "ENTRADA", STOCK_M3)
    assert r.status_code in (200, 201), r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])
    assert stock_actual(db, mat["id"]) == Decimal(str(STOCK_M3)), "stock inicial"

    # ── 2. Mano de obra de la etapa (empleado DESTAJO/en nómina) ──
    emp = crear_empleado(
        client, cleaner,
        cargo_id=cargos(db)["ebanista"],
        en_nomina=True, tipo_pago="DESTAJO",
    )
    r = client.post("/api/v1/produccion/mano-obra/", json={
        "etapa_produccion_id": etapa,
        "empleado_id": emp["id"],
        "monto": MO_MONTO,
        "porcentaje_recargo": MO_RECARGO,
        "listo_nomina": True,
        "observaciones": "MO e2e costo final",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"MO → {r.status_code}: {r.text}"
    mo = r.json()
    cleaner.registrar("mano_obra", mo["id"])

    # ── 3. Pedido ABIERTO de madera + confirmación multi-uso ──
    r = pedir(client, etapa, mat["id"], None)
    assert r.status_code == 201, f"pedido abierto → {r.status_code}: {r.text}"
    consumo = r.json()
    _registrar_rastro_etapa(db, cleaner, etapa)
    assert consumo["estado"] == "PENDIENTE"
    assert float(consumo["cantidad"]) == 0.0
    assert stock_actual(db, mat["id"]) == Decimal(str(STOCK_M3)), "0: el abierto no descuenta"

    r = confirmar_usos(client, consumo["id"], USOS)
    ids = _registrar_rastro_etapa(db, cleaner, etapa)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    assert r.status_code == 200, f"confirmar multi-uso → {r.status_code}: {r.text}"
    assert len(ids) == 3, f"deben nacer 3 consumos (cabeza + 2 hermanos): {ids}"
    db.expire_all()

    filas = _consumos_de_etapa(db, etapa)
    assert len(filas) == 3
    assert all(f[2] == "CONFIRMADO" for f in filas), filas
    assert sum(Decimal(str(f[1])) for f in filas) == MADERA_M3, filas
    cantidades = sorted(Decimal(str(f[1])) for f in filas)
    assert cantidades == [Decimal("0.0200"), Decimal("0.0240"), Decimal("0.1500")], cantidades
    assert {f[3] for f in filas} == {
        "1500 cm (cuenta del taller)",
        "Pieza 2×10×5 × 2",
        "Pieza 3×20×4 × 1",
    }, filas

    # Stock: 5 − 0.194 = 4.806. Gastos: 750 + 100 + 120 = 970.
    assert stock_actual(db, mat["id"]) == Decimal("4.806")
    total_gastos = sum((gasto_monto(db, cid) or Decimal("0")) for cid in ids)
    assert total_gastos == Decimal("970.00"), total_gastos

    # ── 4. costos-en-vivo: renglones aislados y suma exacta materiales + MO ──
    rv = client.get(f"/api/v1/produccion/orden/{orden['id']}/costos-en-vivo",
                    headers=ADMIN_HEADERS)
    assert rv.status_code == 200, rv.text
    vivo = rv.json()
    insumos = [
        i for s in vivo["secciones"] for i in s["insumos"] if i["nombre"] == mat["nombre"]
    ]
    assert len(insumos) == 3, insumos
    assert {i["captura"] for i in insumos} == {
        "1500 cm (cuenta del taller)",
        "Pieza 2×10×5 × 2",
        "Pieza 3×20×4 × 1",
    }, insumos
    assert all(i["es_pendiente"] is False for i in insumos)
    assert all(i["unidad"] == "m³" for i in insumos), insumos
    assert sum(i["total"] for i in insumos) == COSTO_MADERA, insumos

    produccion = [p for s in vivo["secciones"] for p in s["produccion"]]
    assert len(produccion) == 1, produccion
    assert produccion[0]["base"] == MO_MONTO
    assert produccion[0]["porcentaje"] == MO_RECARGO
    assert produccion[0]["total"] == MO_TOTAL

    assert vivo["totales"]["materiales"] == COSTO_MADERA
    assert vivo["totales"]["mano_obra"] == MO_TOTAL
    assert vivo["totales"]["gastos"] == GASTO_SECCION_10
    assert vivo["total_produccion"] == TOTAL_CON_GASTOS

    # ── 5. Finalizar la orden y verificar el COSTO FINAL guardado ──
    r = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado",
                   params={"estado": "EN_PRODUCCION"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"EN_PRODUCCION → {r.status_code}: {r.text}"
    r = client.put(f"/api/v1/produccion/etapa/{etapa}/estado",
                   params={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"COMPLETADA → {r.status_code}: {r.text}"
    r = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado",
                   params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    _registrar_envio_y_costo(db, cleaner, ped["id"], orden["id"])
    assert r.status_code == 200, f"FINALIZADA → {r.status_code}: {r.text}"
    assert r.json().get("estructura_generada") is True, "debe generar la estructura"

    rc = client.get(f"/api/v1/produccion/costo/{orden['id']}", headers=ADMIN_HEADERS)
    assert rc.status_code == 200, rc.text
    costo = rc.json()
    cleaner.registrar("costo_produccion", costo["id"])
    # El costo guardado al finalizar YA incluye los gastos por sección (misma
    # fórmula de la tablita): materiales + MO con recargo + 10% de EBANISTERÍA.
    assert costo["costo_material"] == COSTO_MADERA
    assert costo["costo_mano_obra"] == MO_TOTAL
    assert costo["costo_gastos"] == GASTO_SECCION_10
    assert costo["costo_total"] == TOTAL_CON_GASTOS
    assert costo["precio_venta_calculado"] == TOTAL_CON_GASTOS  # ganancia 0%

    # La fila SQL del costo confirma el mismo número (no solo el response).
    fila_costo = db.execute(text(
        "SELECT costo_material, costo_mano_obra, costo_total FROM costo_produccion"
        " WHERE orden_produccion_id = :o"
    ), {"o": orden["id"]}).fetchone()
    assert fila_costo is not None
    assert Decimal(str(fila_costo[0])) == Decimal("970.00")
    assert Decimal(str(fila_costo[1])) == Decimal("10800.00")
    assert Decimal(str(fila_costo[2])) == Decimal("12947.00")

    # El endpoint de cálculo manual re-calcula con gastos y ganancia explícitos.
    r = client.post(f"/api/v1/produccion/costo/calcular/{orden['id']}", json={
        "ganancia_porcentaje": 30, "costo_gastos": 1000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    recalc = r.json()
    assert recalc["costo_material"] == COSTO_MADERA
    assert recalc["costo_mano_obra"] == MO_TOTAL
    assert recalc["costo_total"] == 12770.0        # 970 + 10.800 + 1.000
    assert recalc["precio_venta_calculado"] == 16601.0  # 12.770 × 1.30

    # ── 5b. Estructura generada (ElementoSeccion / CostoProduccionSeccion) ──
    producto_id = db.execute(
        text("SELECT producto_id FROM detalle_pedido WHERE id = :d"),
        {"d": orden["detalle_pedido_id"]},
    ).scalar()
    assert producto_id is not None

    r = client.get(f"/api/v1/producto/{producto_id}/receta-estructurada",
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    secciones = {s["nombre"]: s for s in r.json()}
    sec = secciones.get("EBANISTERÍA")
    assert sec is not None, list(secciones)
    elems = [e for e in sec["elementos"] if e["material_id_normalizado"] == mat["id"]]
    assert len(elems) == 1, elems
    assert abs(elems[0]["cantidad"] - 0.194) < 1e-9, elems[0]
    assert elems[0]["precio_unitario"] == COSTO_BASE_M3, elems[0]
    cps = [c for c in sec["costos_produccion"]
           if c["costo_base"] == MO_MONTO and c["porcentaje"] == MO_RECARGO]
    assert cps, sec["costos_produccion"]

    fila_el = db.execute(text(
        """
        SELECT e.cantidad, e.precio_unitario
        FROM elemento_seccion e
        JOIN seccion_producto s ON s.id = e.seccion_id
        WHERE s.producto_id = :p AND e.material_id_normalizado = :m
        """
    ), {"p": producto_id, "m": mat["id"]}).fetchone()
    assert fila_el is not None
    assert Decimal(str(fila_el[0])) == Decimal("0.1940")
    assert Decimal(str(fila_el[1])) == Decimal("5000.00")
    fila_cp = db.execute(text(
        """
        SELECT c.costo_base, c.porcentaje
        FROM costo_produccion_seccion c
        JOIN seccion_producto s ON s.id = c.seccion_id
        WHERE s.producto_id = :p
        """
    ), {"p": producto_id}).fetchone()
    assert fila_cp is not None
    assert Decimal(str(fila_cp[0])) == Decimal("10000.00")
    assert Decimal(str(fila_cp[1])) == Decimal("8.00")

    # El snapshot del producto (costo del taller) SÍ aplica el 10% de gastos de
    # la sección: (0.194×5000 + 10.000×1.08) × 1.10 = 12.947.
    prod = client.get(f"/api/v1/producto/{producto_id}", headers=ADMIN_HEADERS).json()
    assert prod["precio_costo_base"] == TOTAL_CON_GASTOS, (
        f"snapshot {prod['precio_costo_base']} != {TOTAL_CON_GASTOS}"
    )

    # ── 6. Nómina: la MISMA ManoObra alimenta el destajo ──
    # La nómina no lee CostoProduccion: lee `mano_obra` (created_at en el
    # período, listo_nomina=True) y aplica el MISMO recargo que el costo de la
    # orden (nomina/service.generar_nomina). El assert es la igualdad exacta.
    # Periodos candidatos que SIEMPRE contienen hoy (la MO usa now()): la
    # semana actual y dos rangos alternativos por si el borde de semana/UTC
    # dejara el registro fuera de la semana.
    d = hoy()
    candidatos = [
        semana_actual(),
        (d - timedelta(days=2), d + timedelta(days=4)),
        (d - timedelta(days=1), d + timedelta(days=5)),
    ]
    det = linea = None
    for d0, d1 in candidatos:
        preview = preview_nomina(client, d0, d1)
        det = next((x for x in preview["detalles"] if x["empleado_id"] == emp["id"]), None)
        if det:
            linea = next((l for l in det["lineas"] if l["etapa_id"] == etapa), None)
            if linea:
                break
    assert linea is not None, "la MO de la etapa no aparece en la nómina"
    assert linea["origen"] == "ETAPA", linea
    assert float(linea["total"]) == MO_TOTAL, linea
    assert float(det["total_produccion"]) == MO_TOTAL, det
    assert float(det["monto_a_pagar"]) == MO_TOTAL, det
    # El eslabón E2E: el costo de MO de la orden finalizada == línea de nómina.
    assert float(linea["total"]) == float(costo["costo_mano_obra"])
