# -*- coding: utf-8 -*-
"""
test_juegos_piezas_produccion.py — Un renglón-juego con precio global que se
abre en órdenes internas por pieza.

Caso real: la dueña cotiza UN juego completo (mesa, sillas, sillones…) con un
solo precio porque fue gusto del cliente y no dio precios por separado. El
cliente ve un renglón; el taller ve una orden por pieza, cada una con su costo.

Cubre:
  1. Cotización con piezas → conversión crea una orden por pieza.
  2. Cantidades: pieza × juegos del renglón (6 sillas × 2 juegos = 12).
  3. Idempotencia del endpoint /produccion/orden/desde-pedido.
  4. Compatibilidad: un renglón sin piezas sigue creando UNA orden.
  5. Validaciones: duplicados, cantidad 0, piezas en REVENTA.
  6. Costos: cada pieza tiene su costo; el juego suma y el pedido cierra solo
     cuando TODAS las piezas están finalizadas.
  7. Hoja de Trabajo: la orden-pieza NO carga la receta del juego padre.

Ejecutar:
  cd backend && source venv/bin/activate && pytest test/test_juegos_piezas_produccion.py -v
"""
import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_material,
    crear_producto,
    crear_receta,
    registrar_inventario_de_material,
    _uniq,
)
from helpers_e2e import (
    area_id,
    avanzar_etapa,
    cargo_id,
    convertir_cotizacion,
    crear_cotizacion_multidetalle,
    crear_consumo,
    crear_empleado,
    crear_etapa,
    entrar_stock_material,
    envio_de_pedido,
    finalizar_orden,
    registrar_mano_obra,
)


PIEZAS_JUEGO = [
    {"nombre": "Mesa de comedor", "cantidad": 1},
    {"nombre": "Sillas", "cantidad": 6},
    {"nombre": "Sillones", "cantidad": 2},
    {"nombre": "Mesas auxiliares", "cantidad": 2},
]


FOTO_PIEZA = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII="
)


def _detalle_a_medida(piezas=PIEZAS_JUEGO, cantidad=2, precio=5000000):
    """Renglón-juego a medida tal como lo manda el frontend (sin precios por pieza)."""
    return {
        "producto_id": None,
        "material_id": None,
        "tipo_item": "FABRICADO",
        "cantidad": cantidad,
        "precio": precio,
        "ancho": 2.0,
        "largo": 1.0,
        "descripcion_especifica": "JUEGO COMPLETO DE COMEDOR SEGÚN GUSTO DEL CLIENTE",
        "piezas": piezas,
    }


def _detalle_para_conversion(detalle: dict) -> dict:
    """Copia del renglón para el body de conversión (sin piezas a propósito)."""
    return {
        key: value
        for key, value in detalle.items()
        if key not in ("piezas",)
    }


def _ordenes_de_detalle(db, detalle_pedido_id) -> list[dict]:
    rows = db.execute(text(
        "SELECT id, detalle_pieza_id, pieza_nombre, cantidad, producto_id, estado"
        " FROM orden_produccion WHERE detalle_pedido_id = :d ORDER BY id"
    ), {"d": detalle_pedido_id}).fetchall()
    return [dict(row._mapping) for row in rows]


def _estado_pedido(db, pedido_id) -> str:
    fila = db.execute(text(
        "SELECT estado FROM pedido WHERE id = :p"
    ), {"p": pedido_id}).fetchone()
    return fila[0]


# ===========================================================================
# 1. Conversión: la venta es un renglón; la producción son cuatro órdenes
# ===========================================================================
def test_conversion_crea_una_orden_por_pieza(client, db, cleaner):
    cliente = crear_cliente(client, cleaner)
    detalle_cot = _detalle_a_medida()

    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle_cot])
    # El renglón cotizado conserva las piezas declaradas (sin precio propio).
    assert len(cot["detalles"][0]["piezas"]) == 4

    # La conversión NO reenvía las piezas: el backend las copia de la cotización.
    r, pedido = convertir_cotizacion(
        client, cleaner, cot["id"], [_detalle_para_conversion(detalle_cot)]
    )
    assert r.status_code == 201, r.text
    assert len(pedido["detalles"]) == 1, "El juego debe seguir siendo UN renglón de venta"
    detalle = pedido["detalles"][0]
    assert [p["nombre"] for p in detalle["piezas"]] == [p["nombre"] for p in PIEZAS_JUEGO]
    assert float(detalle["precio"]) == 5000000.0
    assert float(detalle["cantidad"]) == 2

    ordenes = _ordenes_de_detalle(db, detalle["id"])
    assert len(ordenes) == 4, ordenes
    por_nombre = {o["pieza_nombre"]: o for o in ordenes}
    assert set(por_nombre) == {"Mesa de comedor", "Sillas", "Sillones", "Mesas auxiliares"}
    assert por_nombre["Mesa de comedor"]["cantidad"] == 2       # 1 × 2 juegos
    assert por_nombre["Sillas"]["cantidad"] == 12                # 6 × 2 juegos
    assert por_nombre["Sillones"]["cantidad"] == 4               # 2 × 2 juegos
    assert por_nombre["Mesas auxiliares"]["cantidad"] == 4       # 2 × 2 juegos
    assert all(o["detalle_pieza_id"] is not None for o in ordenes), ordenes
    assert all(o["producto_id"] is None for o in ordenes), "La pieza no carga el producto padre"
    assert all(o["estado"] == "PENDIENTE" for o in ordenes)

    for orden in ordenes:
        cleaner.registrar("orden_produccion", orden["id"])

    # Idempotencia: pedir otra vez las órdenes del detalle no duplica nada.
    r = client.post(
        f"/api/v1/produccion/orden/desde-pedido/{detalle['id']}", headers=ADMIN_HEADERS
    )
    assert r.status_code in (200, 201), r.text
    assert len(_ordenes_de_detalle(db, detalle["id"])) == 4


# ===========================================================================
# 1b. Foto opcional de cada pieza: cotización → pedido → hoja de trabajo
# ===========================================================================
def test_pieza_conserva_foto_en_cotizacion_pedido_y_hoja(client, db, cleaner):
    cliente = crear_cliente(client, cleaner)
    piezas = [
        {"nombre": "Mesa de comedor", "cantidad": 1, "foto": FOTO_PIEZA},
        {"nombre": "Sillas", "cantidad": 2},
    ]
    detalle_cot = _detalle_a_medida(piezas=piezas, cantidad=1)

    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle_cot])
    pieza_cot = cot["detalles"][0]["piezas"]
    assert pieza_cot[0]["foto"] == FOTO_PIEZA
    assert pieza_cot[1].get("foto") is None

    # El listado no lleva la foto (el JSON se mantiene liviano); el detalle sí.
    r = client.get("/api/v1/cotizacion/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    fila = next(c for c in r.json() if c["id"] == cot["id"])
    assert "foto" not in fila["detalles"][0]["piezas"][0]

    r = client.get(f"/api/v1/cotizacion/{cot['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["detalles"][0]["piezas"][0]["foto"] == FOTO_PIEZA

    # La conversión copia la foto a la pieza del pedido.
    r, pedido = convertir_cotizacion(
        client, cleaner, cot["id"], [_detalle_para_conversion(detalle_cot)]
    )
    assert r.status_code == 201, r.text
    piezas_pedido = pedido["detalles"][0]["piezas"]
    assert piezas_pedido[0]["foto"] == FOTO_PIEZA
    assert piezas_pedido[1].get("foto") is None

    # Y la Hoja de Trabajo de la orden-pieza la usa como foto de referencia.
    orden = _ordenes_de_detalle(db, pedido["detalles"][0]["id"])[0]
    cleaner.registrar("orden_produccion", orden["id"])
    empleado = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "EBANISTA"))
    etapa = crear_etapa(
        client, cleaner, orden["id"], area_id(db, "Ebanistería"), empleado["id"]
    )
    r = client.get(
        f"/api/v1/produccion/etapa/{etapa['id']}/referencia-receta",
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pieza_foto"] == FOTO_PIEZA


# ===========================================================================
# 2. Compatibilidad: sin piezas, una sola orden (comportamiento histórico)
# ===========================================================================
def test_renglon_sin_piezas_crea_una_sola_orden(client, db, cleaner):
    cliente = crear_cliente(client, cleaner)
    detalle = {
        "producto_id": None,
        "material_id": None,
        "tipo_item": "FABRICADO",
        "cantidad": 1,
        "precio": 900000,
        "ancho": 1.0,
        "largo": 1.0,
        "descripcion_especifica": "MUEBLE SUELTO SIN JUEGO",
    }
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [detalle])
    assert r.status_code == 201, r.text
    detalle_pedido = pedido["detalles"][0]
    assert detalle_pedido["piezas"] == []
    ordenes = _ordenes_de_detalle(db, detalle_pedido["id"])
    assert len(ordenes) == 1
    assert ordenes[0]["pieza_nombre"] is None
    assert ordenes[0]["detalle_pieza_id"] is None
    assert ordenes[0]["cantidad"] == 1
    cleaner.registrar("orden_produccion", ordenes[0]["id"])


# ===========================================================================
# 3. Validaciones del contrato de piezas
# ===========================================================================
@pytest.mark.parametrize("piezas,esperado", [
    ([{"nombre": "Sillas", "cantidad": 2}, {"nombre": "sillas", "cantidad": 3}], 422),
    ([{"nombre": "Sillas", "cantidad": 0}], 422),
    ([{"nombre": "Sillas", "cantidad": 2}, {"nombre": "SILLON", "cantidad": 1}, {"nombre": "Sillón", "cantidad": 1}], 422),
])
def test_piezas_invalidas_se_rechazan(client, cleaner, piezas, esperado):
    cliente = crear_cliente(client, cleaner)
    detalle = _detalle_a_medida(piezas=piezas, cantidad=1)
    r = client.post("/api/v1/cotizacion/", json={
        "cliente_id": cliente["id"],
        "fecha": "2026-01-15",
        "estado": "BORRADOR",
        "total_estimado": detalle["precio"],
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "detalles": [detalle],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == esperado, r.text


def test_piezas_solo_aplican_a_fabricado(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    detalle = {
        "producto_id": None,
        "material_id": None,
        "tipo_item": "REPARACION",
        "cantidad": 1,
        "precio": 100000,
        "descripcion_especifica": "REPARAR SOFA",
        "piezas": [{"nombre": "Silla", "cantidad": 1}],
    }
    r = client.post("/api/v1/cotizacion/", json={
        "cliente_id": cliente["id"],
        "fecha": "2026-01-15",
        "estado": "BORRADOR",
        "total_estimado": 100000,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "detalles": [detalle],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 422, r.text


def test_juego_con_piezas_no_se_divide_sin_asignar_piezas(client, cleaner):
    """Dividir un renglón-juego en dos líneas del pedido sin repartir las piezas
    duplicaría la producción: el backend lo rechaza."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    detalle = {
        "producto_id": producto["id"],
        "material_id": None,
        "tipo_item": "FABRICADO",
        "cantidad": 1,
        "precio": 1000000,
        "ancho": 2.0,
        "largo": 1.0,
        "piezas": [{"nombre": "Mesa", "cantidad": 1}],
    }
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle])

    sin_piezas = {key: value for key, value in detalle.items() if key != "piezas"}
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [sin_piezas, sin_piezas])
    assert pedido is None
    assert r.status_code == 400, r.text
    assert "no se puede dividir" in r.json()["detail"]


def test_editar_cotizacion_reemplaza_piezas(client, cleaner):
    """El reemplazo completo de renglones también reemplaza sus piezas."""
    cliente = crear_cliente(client, cleaner)
    detalle = _detalle_a_medida(
        piezas=[{"nombre": "Mesa", "cantidad": 1}, {"nombre": "Sillas", "cantidad": 4}],
        cantidad=1,
    )
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle])

    detalle["piezas"] = [{"nombre": "Mesa", "cantidad": 1, "notas": "con vidrio"}]
    r = client.put(f"/api/v1/cotizacion/{cot['id']}", json={
        "total_estimado": detalle["precio"],
        "detalles": [detalle],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    piezas = r.json()["detalles"][0]["piezas"]
    assert [(p["nombre"], float(p["cantidad"]), p["notas"]) for p in piezas] == [
        ("Mesa", 1.0, "con vidrio")
    ]
    cleaner.registrar("detalle_cotizacion", r.json()["detalles"][0]["id"])


# ===========================================================================
# 4. Costos reales por pieza, cierre del pedido y Hoja de Trabajo
# ===========================================================================
def test_costos_por_pieza_y_cierre_del_pedido(client, db, cleaner):
    # Producto de catálogo CON receta: se usa como juego padre. La orden-pieza
    # NO debe cargar su receta ni generar estructura sobre él.
    material = crear_material(client, cleaner, costo_base=10000.0)
    producto = crear_producto(client, cleaner)
    crear_receta(client, cleaner, producto["id"], material["id"], cantidad_base=1, seccion="EBANISTERIA")
    entrar_stock_material(client, cleaner, material["id"], 100)
    registrar_inventario_de_material(db, cleaner, material["id"])

    cliente = crear_cliente(client, cleaner)
    piezas = [
        {"nombre": "Mesa", "cantidad": 1},
        {"nombre": "Sillas", "cantidad": 2},
    ]
    detalle_cot = {
        "producto_id": producto["id"],
        "material_id": None,
        "tipo_item": "FABRICADO",
        "cantidad": 2,
        "precio": 1000000,
        "ancho": 2.0,
        "largo": 1.0,
        "piezas": piezas,
    }
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [detalle_cot])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [detalle_cot])
    assert r.status_code == 201, r.text
    detalle_pedido = pedido["detalles"][0]
    ordenes = _ordenes_de_detalle(db, detalle_pedido["id"])
    assert len(ordenes) == 2, ordenes
    por_nombre = {o["pieza_nombre"]: o for o in ordenes}
    assert por_nombre["Mesa"]["cantidad"] == 2
    assert por_nombre["Sillas"]["cantidad"] == 4

    empleado = crear_empleado(client, cleaner, cargo_id=cargo_id(db, "EBANISTA"))
    costos = {}
    etapa_por_orden = {}
    for nombre, orden in por_nombre.items():
        cleaner.registrar("orden_produccion", orden["id"])
        # La pieza se fabrica en su propia orden (etapas independientes).
        etapa = crear_etapa(client, cleaner, orden["id"], area_id(db, "Ebanistería"), empleado["id"])
        etapa_por_orden[nombre] = etapa
        avanzar_etapa(client, etapa["id"], "EN_PROCESO")
        cantidad_consumo = 2 if nombre == "Mesa" else 4
        r_consumo, consumo = crear_consumo(
            client, cleaner, db, etapa["id"], material["id"], cantidad_consumo, empleado["id"]
        )
        assert r_consumo.status_code in (200, 201), r_consumo.text
        registrar_mano_obra(
            client, cleaner, etapa["id"], empleado["id"],
            10000 if nombre == "Mesa" else 20000,
            porcentaje_recargo=8.0,
        )
        avanzar_etapa(client, etapa["id"], "COMPLETADA")

        # Hoja de Trabajo: la orden-pieza no carga la receta del juego padre.
        rr = client.get(
            f"/api/v1/produccion/etapa/{etapa['id']}/referencia-receta",
            headers=ADMIN_HEADERS,
        )
        assert rr.status_code == 200, rr.text
        hoja = rr.json()
        assert hoja["producto_id"] is None
        assert hoja["pieza_nombre"] == nombre
        assert hoja["juego_nombre"] == producto["nombre"]
        assert hoja["materiales"] == [], "La pieza no debe heredar la receta del juego padre"
        assert hoja["piezas_mueble"] == [], "El checklist vive en el renglón, no dentro de la pieza"

        # Costos en vivo de la pieza: sus propias unidades e insumos, sin estimado.
        rc = client.get(
            f"/api/v1/produccion/orden/{orden['id']}/costos-en-vivo", headers=ADMIN_HEADERS
        )
        assert rc.status_code == 200, rc.text
        vivo = rc.json()
        assert vivo["producto_nombre"] == nombre
        assert vivo["unidades"] == cantidad_consumo
        assert vivo["estimado"] is None
        assert vivo["total_produccion"] > 0
        costos[nombre] = vivo["total_produccion"]

    # Con UNA pieza finalizada el pedido NO cierra todavía.
    finalizar_orden(client, por_nombre["Mesa"]["id"])
    assert _estado_pedido(db, pedido["id"]) == "PRODUCCION"
    assert envio_de_pedido(db, pedido["id"]) is None
    # La estructura del producto padre NO se generó desde una pieza.
    secciones = db.execute(text(
        "SELECT COUNT(*) FROM seccion_producto WHERE producto_id = :p"
    ), {"p": producto["id"]}).scalar()
    assert secciones == 0, "La pieza no debe generar la estructura del juego padre"

    # Con TODAS las piezas finalizadas: pedido TERMINADO + un envío.
    finalizar_orden(client, por_nombre["Sillas"]["id"])
    assert _estado_pedido(db, pedido["id"]) == "TERMINADO"
    assert envio_de_pedido(db, pedido["id"]) is not None

    # El costo final por orden quedó guardado y sin estimado (el precio es del juego).
    for nombre, orden in por_nombre.items():
        rcosto = client.get(
            f"/api/v1/produccion/costo/{orden['id']}", headers=ADMIN_HEADERS
        )
        assert rcosto.status_code == 200, rcosto.text
        costo = rcosto.json()
        cleaner.registrar("costo_produccion", costo["id"])
        assert costo["costo_total"] > 0
        assert costo["costo_estimado"] is None

    # Rentabilidad del pedido: la suma de las piezas + desglose por pieza.
    rr = client.get(f"/api/v1/pedido/{pedido['id']}/rentabilidad", headers=ADMIN_HEADERS)
    assert rr.status_code == 200, rr.text
    rent = rr.json()
    assert rent["tiene_produccion"] is True
    assert rent["costo_real_produccion"] == pytest.approx(sum(costos.values()), abs=1.0)
    assert {p["pieza_nombre"] for p in rent["por_pieza"]} == {"Mesa", "Sillas"}
    assert all(p["costo_real"] > 0 for p in rent["por_pieza"])
