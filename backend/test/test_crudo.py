# -*- coding: utf-8 -*-
"""
test_crudo.py — Productos en Crudo (ítem libre de inventario).

El rediseño convierte al "producto en crudo" en un ítem independiente con nombre
libre (no ligado al catálogo de productos). Cubre:

  - Crear un ítem en crudo con solo un nombre (+ foto de referencia opcional).
  - Listar ítems en crudo.
  - Producción de crudo: crear una producción, registrar un consumo de material
    (con solicitante), finalizarla → suma stock al ítem en crudo.
  - Asignar una pieza de crudo a un detalle de pedido: SOLO descuenta stock y
    deja trazabilidad (NO pre-marca etapas, NO descuenta materiales de nuevo).

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_crudo.py -v
"""
from decimal import Decimal

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_movimiento,
    crear_producto,
    registrar_inventario_de_material,
    registrar_venta_de_pedido,
)
from helpers_e2e import (
    area_id,
    avanzar_etapa,
    cargos,
    crear_consumo,
    crear_empleado,
    crear_etapa,
    finalizar_orden,
    registrar_mano_obra,
)


def _crear_crudo(client, cleaner, nombre=None):
    """Crea un ítem en crudo con el nombre dado (o uno único). Devuelve el crudo."""
    r = client.post("/api/v1/produccion/crudo/", json={
        "nombre": nombre or "Marco de madera - Ebanisteria",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear crudo → {r.status_code}: {r.text}"
    crudo = r.json()
    cleaner.registrar("producto_crudo_inventario", crudo["id"])
    return crudo


def _crear_detalle_pedido(client, cleaner):
    """Crea producto+cliente+cotización+pedido con un detalle. Devuelve el id del detalle."""
    producto = crear_producto(client, cleaner)
    cliente = crear_cliente(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    r_conv = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"],
                            "cantidad": 1, "precio": 100000, "costo_unitario": 1000,
                            "porcentaje_ganancia": 40}],
              "adelanto": None},
        headers=ADMIN_HEADERS,
    )
    assert r_conv.status_code == 201, f"convertir → {r_conv.status_code}: {r_conv.text}"
    pedido = r_conv.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    return pedido["detalles"][0]["id"]


# ---------------------------------------------------------------------------
# Crear ítem en crudo
# ---------------------------------------------------------------------------
def test_crear_crudo_solo_nombre(client, cleaner, db):
    crudo = _crear_crudo(client, cleaner, "Tablero de nogal")
    assert crudo["nombre"] == "Tablero de nogal"
    assert "foto_url" in crudo, "Debe exponer foto_url (público)"

    cantidad = db.execute(text(
        "SELECT cantidad FROM producto_crudo_inventario WHERE id=:i"),
        {"i": crudo["id"]},
    ).scalar()
    assert float(cantidad) == 0.0, "Un crudo recién creado empieza con stock 0"


def test_crear_crudo_requiere_nombre(client, cleaner):
    r = client.post("/api/v1/produccion/crudo/", json={}, headers=ADMIN_HEADERS)
    assert r.status_code == 422, (
        f"Crudo sin nombre debió rechazarse (422), fue {r.status_code}: {r.text}"
    )


def test_importar_crudo_ya_hecho_con_stock_y_costo(client, cleaner, db):
    """Lo YA HECHO se importa con stock + costo sin producción: entra por
    kardex (STOCK INICIAL) sin descontar materiales ni generar nómina."""
    material = crear_material(client, cleaner, costo_base=500.0)
    crear_movimiento(client, cleaner, material["id"], "ENTRADA", 10)

    r = client.post("/api/v1/produccion/crudo/", json={
        "nombre": "Silla en crudo (importada)",
        "cantidad": 5,
        "costo_unitario": 120000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"importar crudo → {r.status_code}: {r.text}"
    crudo = r.json()
    cleaner.registrar("producto_crudo_inventario", crudo["id"])
    assert float(crudo["cantidad"]) == 5.0
    assert float(crudo["costo_unitario"]) == 120000.0

    # Kardex trazable: la entrada inicial queda en el historial.
    r_kardex = client.get(
        f"/api/v1/produccion/crudo/{crudo['id']}/kardex", headers=ADMIN_HEADERS)
    assert r_kardex.status_code == 200
    movimientos = r_kardex.json()
    assert any(m["tipo"] == "ENTRADA" and float(m["cantidad"]) == 5.0
               for m in movimientos), "Falta la ENTRADA de STOCK INICIAL en kardex"
    for m in movimientos:
        cleaner.registrar("movimiento_crudo", m["id"])

    # No descontó materiales ni generó gastos/nómina: importación pura.
    stock_mat = db.execute(text(
        "SELECT i.cantidad FROM inventario i WHERE i.material_id=:m"),
        {"m": material["id"]},
    ).scalar()
    assert float(stock_mat) == 10.0, f"Importar no debe descontar material, quedó {stock_mat}"


def test_listar_crudos(client, cleaner):
    _crear_crudo(client, cleaner, "Pieza A")
    _crear_crudo(client, cleaner, "Pieza B")
    r = client.get("/api/v1/produccion/crudo/", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"listar crudos → {r.status_code}: {r.text}"
    nombres = [c["nombre"] for c in r.json()]
    assert "Pieza A" in nombres and "Pieza B" in nombres


# ---------------------------------------------------------------------------
# Producción de crudo + consumo → finalizar suma stock
# ---------------------------------------------------------------------------
def test_produccion_crudo_consumo_y_finalizar_suma_stock(client, cleaner, db):
    crudo = _crear_crudo(client, cleaner, "Marco de madera")
    material = crear_material(client, cleaner, costo_base=500.0)
    crear_movimiento(client, cleaner, material["id"], "ENTRADA", 10)

    r = client.post("/api/v1/produccion/crudo-produccion/", json={
        "crudo_id": crudo["id"], "cantidad": 1, "observaciones": "Lote 1",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear producción → {r.status_code}: {r.text}"
    prod = r.json()
    cleaner.registrar("produccion_crudo", prod["id"])
    assert prod["estado"] == "PENDIENTE"

    # Registrar un consumo de material (solicitante = empleado 1).
    r_cons = client.post(f"/api/v1/produccion/crudo-produccion/{prod['id']}/consumo/", json={
        "material_id": material["id"], "cantidad": 3, "solicitante_empleado_id": 1,
        "seccion": "EBANISTERIA", "observaciones": "marcos",
    }, headers=ADMIN_HEADERS)
    assert r_cons.status_code == 201, f"registrar consumo → {r_cons.status_code}: {r_cons.text}"
    consumo = r_cons.json()
    cleaner.registrar("produccion_crudo_consumo", consumo["id"])
    registrar_inventario_de_material(db, cleaner, material["id"])

    # El material debe haberse descontado (entrada 10 → 7).
    stock_mat = db.execute(text(
        "SELECT i.cantidad FROM inventario i WHERE i.material_id=:m"),
        {"m": material["id"]},
    ).scalar()
    assert float(stock_mat) == 7.0, f"Stock de material debió quedar 7, quedó {stock_mat}"

    # Finalizar la producción → suma stock al crudo.
    r_fin = client.put(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}/estado",
        json={"estado": "COMPLETADA", "observaciones": "lista"},
        headers=ADMIN_HEADERS,
    )
    assert r_fin.status_code == 200, f"finalizar producción → {r_fin.status_code}: {r_fin.text}"

    stock_crudo = db.execute(text(
        "SELECT cantidad FROM producto_crudo_inventario WHERE id=:i"),
        {"i": crudo["id"]},
    ).scalar()
    assert float(stock_crudo) == 1.0, f"Finalizar producción debió sumar 1, quedó {stock_crudo}"

    # El gasto generado por el consumo debe existir.
    gastos = db.execute(text("SELECT id FROM gasto")).scalars().all()
    assert gastos, "Finalizar una producción con consumo debió generar un gasto"
    for g in gastos:
        cleaner.registrar("gasto", g)


# ---------------------------------------------------------------------------
# Asignar crudo a detalle → SOLO descuenta stock (sin marcar etapas)
# ---------------------------------------------------------------------------
def test_asignar_crudo_descuenta_stock_sin_marcar_etapas(client, cleaner, db):
    crudo = _crear_crudo(client, cleaner, "Pieza lista")
    # Subimos stock fabricando una producción.
    r = client.post("/api/v1/produccion/crudo-produccion/", json={
        "crudo_id": crudo["id"], "cantidad": 1,
    }, headers=ADMIN_HEADERS)
    prod = r.json()
    cleaner.registrar("produccion_crudo", prod["id"])
    client.put(f"/api/v1/produccion/crudo-produccion/{prod['id']}/estado",
               json={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS)

    detalle_id = _crear_detalle_pedido(client, cleaner)

    r_asig = client.post(
        f"/api/v1/produccion/crudo/{crudo['id']}/asignar/{detalle_id}",
        json={"cantidad": 1}, headers=ADMIN_HEADERS,
    )
    assert r_asig.status_code == 201, f"asignar crudo → {r_asig.status_code}: {r_asig.text}"
    uso = r_asig.json()
    cleaner.registrar("produccion_crudo_uso", uso["id"])

    stock_crudo = db.execute(text(
        "SELECT cantidad FROM producto_crudo_inventario WHERE id=:i"),
        {"i": crudo["id"]},
    ).scalar()
    assert float(stock_crudo) == 0.0, f"Asignar debió descontar a 0, quedó {stock_crudo}"

    # La conversión cotización→pedido ya creó la orden de producción de la
    # línea FABRICADO (el pedido nace en PRODUCCION). La ASIGNACIÓN del crudo
    # no debe crear una orden adicional ni marcar etapas: sigue con 1 sola.
    n_ligadas = db.execute(text(
        "SELECT COUNT(*) FROM orden_produccion WHERE detalle_pedido_id=:d"),
        {"d": detalle_id},
    ).scalar()
    assert n_ligadas == 1, (
        "La asignación del crudo NO debe duplicar la orden de producción "
        f"(la única es la de la conversión), hay {n_ligadas}"
    )
    n_etapas = db.execute(text(
        "SELECT COUNT(*) FROM etapa_produccion ep "
        "JOIN orden_produccion op ON op.id = ep.orden_produccion_id "
        "WHERE op.detalle_pedido_id=:d"),
        {"d": detalle_id},
    ).scalar()
    assert n_etapas == 0, "Asignar crudo NO debe auto-marcar etapas de producción"


def test_asignar_crudo_sin_stock_rechaza(client, cleaner):
    crudo = _crear_crudo(client, cleaner, "Sin stock")
    detalle_id = _crear_detalle_pedido(client, cleaner)
    r = client.post(
        f"/api/v1/produccion/crudo/{crudo['id']}/asignar/{detalle_id}",
        json={"cantidad": 1}, headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, (
        f"Asignar crudo sin stock debió rechazarse (400), fue {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# Mano de obra en producción de crudo
# ---------------------------------------------------------------------------
def _crear_produccion_crudo(client, cleaner, crudo_id, cantidad=1):
    r = client.post("/api/v1/produccion/crudo-produccion/", json={
        "crudo_id": crudo_id, "cantidad": cantidad,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear producción → {r.status_code}: {r.text}"
    prod = r.json()
    cleaner.registrar("produccion_crudo", prod["id"])
    return prod


def test_mano_obra_crudo_se_registra_y_calcula_costo(client, cleaner):
    crudo = _crear_crudo(client, cleaner, "Pieza con MO")
    prod = _crear_produccion_crudo(client, cleaner, crudo["id"])

    # Empleado inactivo debe rechazarse (empleados de prueba: 1 activo).
    r_bad = client.post(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}/mano-obra/",
        json={"empleado_id": 99999, "monto": 10000}, headers=ADMIN_HEADERS,
    )
    assert r_bad.status_code == 400, f"empleado inexistente debió rechazarse: {r_bad.text}"

    r = client.post(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}/mano-obra/",
        json={"empleado_id": 1, "monto": 10000, "porcentaje_recargo": 10, "listo_nomina": True},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, f"crear MO → {r.status_code}: {r.text}"
    mo = r.json()
    cleaner.registrar("produccion_crudo_mano_obra", mo["id"])
    assert mo["empleado_id"] == 1
    assert mo["pagado"] is False

    # El costo_mano_obra incluye el recargo: 10000 * 1.10 = 11000
    r_det = client.get(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}", headers=ADMIN_HEADERS
    )
    assert r_det.status_code == 200
    det = r_det.json()
    assert det["costo_mano_obra"] == 11000.0, (
        f"costo_mano_obra debió ser 11000, fue {det['costo_mano_obra']}"
    )


def test_mano_obra_crudo_no_se_elimina_si_pagada_y_genera_egreso(client, cleaner, db):
    crudo = _crear_crudo(client, cleaner, "Pieza MO pagada")
    prod = _crear_produccion_crudo(client, cleaner, crudo["id"])

    r = client.post(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}/mano-obra/",
        json={"empleado_id": 1, "monto": 5000}, headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201
    mo = r.json()
    cleaner.registrar("produccion_crudo_mano_obra", mo["id"])

    # Finalizar: suma stock al crudo y materializa el egreso de la MO sin pagar.
    r_fin = client.put(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}/estado",
        json={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS,
    )
    assert r_fin.status_code == 200, f"finalizar → {r_fin.status_code}: {r_fin.text}"
    assert r_fin.json()["estado"] == "COMPLETADA"

    # Debe existir un egreso de "Mano de Obra de Producción" por el monto.
    monto_gasto = db.execute(text(
        """
        SELECT g.monto FROM gasto g
        JOIN tipo_gasto tg ON tg.id = g.tipo_gasto_id
        WHERE tg.nombre = 'Mano de Obra de Producción'
          AND g.observaciones LIKE :marcador
        """
    ), {"marcador": f"%[mano_obra_crudo {mo['id']}]%"}).scalar()
    assert monto_gasto is not None, "Finalizar con MO debió generar el egreso"
    assert float(monto_gasto) == 5000.0, f"egreso debió ser 5000, fue {monto_gasto}"

    # Ya pagada → no se puede eliminar.
    r_del = client.delete(
        f"/api/v1/produccion/crudo-produccion/mano-obra/{mo['id']}", headers=ADMIN_HEADERS
    )
    assert r_del.status_code == 400, (
        f"eliminar MO pagada debió rechazarse (400), fue {r_del.status_code}: {r_del.text}"
    )


def test_mano_obra_crudo_se_bloquea_en_produccion_completada(client, cleaner):
    crudo = _crear_crudo(client, cleaner, "Pieza cerrada")
    prod = _crear_produccion_crudo(client, cleaner, crudo["id"])
    r = client.put(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}/estado",
        json={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200

    r_mo = client.post(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}/mano-obra/",
        json={"empleado_id": 1, "monto": 2000}, headers=ADMIN_HEADERS,
    )
    assert r_mo.status_code == 400, (
        f"registrar MO en producción COMPLETADA debió rechazarse (400), fue {r_mo.status_code}: {r_mo.text}"
    )


# ===========================================================================
# Costo del crudo en el pedido: el crudo asignado cuenta como costo del mueble
# (materiales + mano de obra de su fabricación), UNA sola vez y sin duplicar
# los materiales internos del crudo al pasar al producto real.
# ===========================================================================
def _producir_crudo(client, cleaner, db, crudo, material, cantidad_material, mano_obra=0.0):
    """Fabrica 1 pieza del crudo con un consumo (y MO opcional) y la finaliza.
    Deja el crudo con stock y su `costo_unitario` real actualizado."""
    r = client.post("/api/v1/produccion/crudo-produccion/", json={
        "crudo_id": crudo["id"], "cantidad": 1,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear producción crudo → {r.status_code}: {r.text}"
    prod = r.json()
    cleaner.registrar("produccion_crudo", prod["id"])

    r_cons = client.post(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}/consumo/",
        json={"material_id": material["id"], "cantidad": cantidad_material,
              "solicitante_empleado_id": 1, "seccion": "EBANISTERIA"},
        headers=ADMIN_HEADERS,
    )
    assert r_cons.status_code == 201, f"consumo crudo → {r_cons.status_code}: {r_cons.text}"
    cleaner.registrar("produccion_crudo_consumo", r_cons.json()["id"])
    registrar_inventario_de_material(db, cleaner, material["id"])

    if mano_obra > 0:
        r_mo = client.post(
            f"/api/v1/produccion/crudo-produccion/{prod['id']}/mano-obra/",
            json={"empleado_id": 1, "monto": mano_obra},
            headers=ADMIN_HEADERS,
        )
        assert r_mo.status_code == 201, f"MO crudo → {r_mo.status_code}: {r_mo.text}"
        cleaner.registrar("produccion_crudo_mano_obra", r_mo.json()["id"])

    r_fin = client.put(
        f"/api/v1/produccion/crudo-produccion/{prod['id']}/estado",
        json={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS,
    )
    assert r_fin.status_code == 200, f"finalizar crudo → {r_fin.status_code}: {r_fin.text}"
    # Gastos generados (consumo + MO) por esta producción: registrarlos.
    for (gid,) in db.execute(text(
        "SELECT id FROM gasto WHERE descripcion LIKE :p OR observaciones LIKE :p"
    ), {"p": f"%Crudo #{prod['id']}%"}).fetchall():
        cleaner.registrar("gasto", gid)
    return prod


def _orden_de_detalle(db, detalle_id) -> int:
    return int(db.execute(text(
        "SELECT id FROM orden_produccion WHERE detalle_pedido_id=:d"
    ), {"d": detalle_id}).scalar())


def _preparar_orden(client, cleaner, db, detalle_id, material, cantidad, mano_obra,
                    recargo=10.0):
    """Crea la etapa de Ebanistería de la orden del detalle, registra consumo +
    MO (con recargo explícito, para que la tablita en vivo y el costo guardado
    cuadren) y la completa."""
    orden_id = _orden_de_detalle(db, detalle_id)
    emp = crear_empleado(client, cleaner, cargo_id=cargos(db)["ebanista"], en_nomina=True)
    etapa = crear_etapa(client, cleaner, orden_id, area_id(db, "Ebanistería"), emp["id"])
    avanzar_etapa(client, etapa["id"], "EN_PROCESO")
    r, _ = crear_consumo(
        client, cleaner, db, etapa["id"], material["id"], cantidad, emp["id"],
        seccion="EBANISTERIA",
    )
    assert r.status_code in (200, 201), f"consumo orden → {r.status_code}: {r.text}"
    registrar_mano_obra(
        client, cleaner, etapa["id"], emp["id"], monto=mano_obra,
        porcentaje_recargo=recargo,
    )
    avanzar_etapa(client, etapa["id"], "COMPLETADA")
    return orden_id


def _costo_orden(client, orden_id) -> dict:
    r = client.get(f"/api/v1/produccion/costo/{orden_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"ver costo orden → {r.status_code}: {r.text}"
    return r.json()


def test_crudo_asignado_cuenta_en_el_costo_del_mueble(client, cleaner, db):
    """El crudo asignado al pedido suma su costo real al mueble, exactamente una
    vez: materiales + crudo + mano de obra + gastos de sección."""
    material_crudo = crear_material(client, cleaner, costo_base=500.0)
    crear_movimiento(client, cleaner, material_crudo["id"], "ENTRADA", 100)
    crudo = _crear_crudo(client, cleaner, "Esqueleto de cama")

    # Fabricar el crudo: materiales 4×500 = 2000 + MO 1000 → costo unitario 3000.
    _producir_crudo(client, cleaner, db, crudo, material_crudo, cantidad_material=4, mano_obra=1000)
    costo_crudo_u = db.execute(text(
        "SELECT costo_unitario FROM producto_crudo_inventario WHERE id=:i"),
        {"i": crudo["id"]},
    ).scalar()
    assert float(costo_crudo_u) == 3000.0, f"costo del crudo debió ser 3000, fue {costo_crudo_u}"

    # Pedido real con su propia producción (otro material): 2×700 = 1400 + MO 2000.
    detalle_id = _crear_detalle_pedido(client, cleaner)
    material_mueble = crear_material(client, cleaner, costo_base=700.0)
    crear_movimiento(client, cleaner, material_mueble["id"], "ENTRADA", 100)
    orden_id = _preparar_orden(client, cleaner, db, detalle_id, material_mueble, 2, 2000)

    # Asignar el crudo al detalle ANTES de finalizar la orden.
    r_asig = client.post(
        f"/api/v1/produccion/crudo/{crudo['id']}/asignar/{detalle_id}",
        json={"cantidad": 1}, headers=ADMIN_HEADERS,
    )
    assert r_asig.status_code == 201, f"asignar crudo → {r_asig.status_code}: {r_asig.text}"
    uso = r_asig.json()
    cleaner.registrar("produccion_crudo_uso", uso["id"])
    assert uso["costo_unitario"] == 3000.0, f"el uso debió congelar 3000, fue {uso['costo_unitario']}"
    assert uso["costo_total"] == 3000.0
    assert uso["seccion"] == "EBANISTERIA"

    finalizar_orden(client, orden_id)

    # MO con recargo 10%: 2000 × 1.10 = 2200. Gastos EBANISTERÍA:
    # (1400 + 2200 + 3000) × 10% = 660. Total = 6600 + 660 = 7260.
    costo = _costo_orden(client, orden_id)
    assert costo["costo_material"] == 1400.0, f"materiales: {costo['costo_material']}"
    assert costo["costo_crudo"] == 3000.0, f"crudo: {costo['costo_crudo']}"
    assert costo["costo_mano_obra"] == 2200.0, f"MO: {costo['costo_mano_obra']}"
    assert costo["costo_gastos"] == 660.0, f"gastos: {costo['costo_gastos']}"
    assert costo["costo_total"] == 7260.0, f"total: {costo['costo_total']}"

    # Idempotente: recalcular el costo no duplica el crudo.
    r_recalc = client.post(
        f"/api/v1/produccion/costo/calcular/{orden_id}", json={}, headers=ADMIN_HEADERS
    )
    assert r_recalc.status_code == 200, f"recalcular → {r_recalc.status_code}: {r_recalc.text}"
    assert r_recalc.json()["costo_crudo"] == 3000.0
    assert r_recalc.json()["costo_total"] == 7260.0

    # La tablita en vivo muestra el crudo como insumo y cuadra con el total.
    vivo = client.get(
        f"/api/v1/produccion/orden/{orden_id}/costos-en-vivo", headers=ADMIN_HEADERS
    ).json()
    assert vivo["total_produccion"] == 7260.0, f"en vivo: {vivo['total_produccion']}"
    filas_crudo = [i for s in vivo["secciones"] for i in s["insumos"] if i.get("es_crudo")]
    assert len(filas_crudo) == 1, f"debe haber 1 renglón de crudo, hay {len(filas_crudo)}"
    assert filas_crudo[0]["total"] == 3000.0

    # La estructura del producto recibió el crudo UNA vez (con su marcador).
    elem = db.execute(text(
        "SELECT cantidad, precio_unitario FROM elemento_seccion "
        "WHERE observaciones LIKE :p"
    ), {"p": f"%[crudo_uso {uso['id']}]%"}).fetchone()
    assert elem is not None, "la estructura del producto no incluyó el crudo"
    assert float(elem[0]) == 1.0
    assert float(elem[1]) == 3000.0

    # SIN DOBLE CONTEO: la orden NO volvió a descontar/registrar el material del
    # crudo (solo tiene su propio consumo).
    consumos_orden = db.execute(text(
        "SELECT cm.material_id FROM consumo_material cm "
        "JOIN etapa_produccion ep ON ep.id = cm.etapa_produccion_id "
        "WHERE ep.orden_produccion_id = :o"
    ), {"o": orden_id}).fetchall()
    assert [int(c[0]) for c in consumos_orden] == [material_mueble["id"]], (
        "el material interno del crudo no debe aparecer como consumo de la orden "
        f"(consumos: {consumos_orden})"
    )


def test_crudo_asignado_despues_de_finalizar_actualiza_el_costo(client, cleaner, db):
    """Asignar crudo a un pedido ya finalizado recalcula el costo guardado y
    agrega el crudo a la estructura generada, sin duplicar."""
    detalle_id = _crear_detalle_pedido(client, cleaner)
    material_mueble = crear_material(client, cleaner, costo_base=700.0)
    crear_movimiento(client, cleaner, material_mueble["id"], "ENTRADA", 100)
    orden_id = _preparar_orden(client, cleaner, db, detalle_id, material_mueble, 2, 2000)
    finalizar_orden(client, orden_id)

    costo_inicial = _costo_orden(client, orden_id)
    assert costo_inicial["costo_crudo"] == 0.0
    # Sin crudo: (1400 + 2200) + 10% = 3960.
    assert costo_inicial["costo_total"] == 3960.0

    # Crudo importado (ya hecho) con costo conocido: 5000.
    r_crudo = client.post("/api/v1/produccion/crudo/", json={
        "nombre": "Pieza ya hecha", "cantidad": 1, "costo_unitario": 5000,
    }, headers=ADMIN_HEADERS)
    crudo = r_crudo.json()
    cleaner.registrar("producto_crudo_inventario", crudo["id"])

    r_asig = client.post(
        f"/api/v1/produccion/crudo/{crudo['id']}/asignar/{detalle_id}",
        json={"cantidad": 1}, headers=ADMIN_HEADERS,
    )
    assert r_asig.status_code == 201, f"asignar crudo → {r_asig.status_code}: {r_asig.text}"
    uso = r_asig.json()
    cleaner.registrar("produccion_crudo_uso", uso["id"])

    # El costo guardado ya refleja el crudo: (1400 + 5000 + 2200) + 10% = 9460.
    costo = _costo_orden(client, orden_id)
    assert costo["costo_crudo"] == 5000.0, f"crudo: {costo['costo_crudo']}"
    assert costo["costo_total"] == 9460.0, f"total: {costo['costo_total']}"

    # Y quedó en la estructura generada (una sola fila por uso).
    n = db.execute(text(
        "SELECT COUNT(*) FROM elemento_seccion WHERE observaciones LIKE :p"
    ), {"p": f"%[crudo_uso {uso['id']}]%"}).scalar()
    assert n == 1, f"la estructura debe tener 1 fila de crudo, tiene {n}"


def test_costo_crudo_es_promedio_ponderado_por_stock(client, cleaner, db):
    """Dos producciones con costos distintos → el costo del crudo es el promedio
    ponderado por las piezas en stock (no el de la última producción)."""
    material = crear_material(client, cleaner, costo_base=500.0)
    crear_movimiento(client, cleaner, material["id"], "ENTRADA", 100)
    crudo = _crear_crudo(client, cleaner, "Base de mesa")

    # Lote 1: 2×500 = 1000 → costo unitario 1000.
    _producir_crudo(client, cleaner, db, crudo, material, cantidad_material=2)
    # Lote 2: 6×500 = 3000 → promedio (1×1000 + 1×3000)/2 = 2000.
    _producir_crudo(client, cleaner, db, crudo, material, cantidad_material=6)

    fila = db.execute(text(
        "SELECT cantidad, costo_unitario FROM producto_crudo_inventario WHERE id=:i"),
        {"i": crudo["id"]},
    ).fetchone()
    assert float(fila[0]) == 2.0, f"stock: {fila[0]}"
    assert float(fila[1]) == 2000.0, f"costo promedio debió ser 2000, fue {fila[1]}"


def test_crudo_sin_costo_no_infla_el_pedido(client, cleaner, db):
    """Un crudo importado sin costo (costo 0) no rompe ni infla el costo del
    mueble: aporta 0 y la orden sigue siendo calculable."""
    detalle_id = _crear_detalle_pedido(client, cleaner)
    material_mueble = crear_material(client, cleaner, costo_base=700.0)
    crear_movimiento(client, cleaner, material_mueble["id"], "ENTRADA", 100)
    orden_id = _preparar_orden(client, cleaner, db, detalle_id, material_mueble, 2, 2000)

    # Crudo importado SIN costo (0).
    r_crudo = client.post("/api/v1/produccion/crudo/", json={
        "nombre": "Crudo sin costo", "cantidad": 1,
    }, headers=ADMIN_HEADERS)
    crudo = r_crudo.json()
    cleaner.registrar("producto_crudo_inventario", crudo["id"])
    r_asig = client.post(
        f"/api/v1/produccion/crudo/{crudo['id']}/asignar/{detalle_id}",
        json={"cantidad": 1}, headers=ADMIN_HEADERS,
    )
    assert r_asig.status_code == 201
    uso = r_asig.json()
    cleaner.registrar("produccion_crudo_uso", uso["id"])
    assert uso["costo_unitario"] == 0.0

    finalizar_orden(client, orden_id)
    costo = _costo_orden(client, orden_id)
    assert costo["costo_crudo"] == 0.0
    # (1400 + 2200) + 10% = 3960, sin inflarse por el crudo sin costo.
    assert costo["costo_total"] == 3960.0, f"total: {costo['costo_total']}"

