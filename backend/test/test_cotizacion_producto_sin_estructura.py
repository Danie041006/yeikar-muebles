"""
test_cotizacion_producto_sin_estructura.py
==========================================
Fix: un producto SIN estructura de costes (solo las secciones vacías que crea
el sistema por defecto) se cotizaba en $0 y el frontend bloqueaba guardar
("Hay un renglón sin precio calculado"). Ahora cae al fallback de
precio_venta_base → fuente_precio="estimado_sin_estructura" y la cotización
se guarda. El ciclo queda: sin estructura → cotiza con estimado → producción
→ al finalizar se genera la estructura real.

Ejecutar:  pytest test/test_cotizacion_producto_sin_estructura.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente, crear_material, crear_receta
from helpers_e2e import (
    area_id,
    cargos,
    convertir_cotizacion,
    crear_cotizacion_multidetalle,
    crear_empleado,
    crear_etapa,
    crear_producto_fabricado,
    entrar_stock_material,
)


def _crear_producto_con_secciones_vacias(client, cleaner, precio_venta_base):
    """Simula el producto creado desde la UI: 5 secciones vacías + precio base."""
    r = client.post("/api/v1/producto/", json={
        "nombre": "cama sin estructura de costes",
        "tipo_producto_id": 1,
        "es_reventa": False,
        "ancho_base": 1.60,
        "largo_base": 1.90,
        "precio_venta_base": precio_venta_base,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    producto = r.json()
    cleaner.registrar("producto", producto["id"])
    for nombre, orden in (("EBANISTERÍA", 1), ("PINTURA", 2), ("TAPICERÍA", 3),
                          ("TENDIDO", 4), ("TERMINACIÓN", 5)):
        r = client.post("/api/v1/seccion/", json={
            "producto_id": producto["id"], "nombre": nombre, "orden": orden,
        }, headers=ADMIN_HEADERS)
        assert r.status_code == 201, r.text
        cleaner.registrar("seccion_producto", r.json()["id"])
    return producto


def test_producto_sin_estructura_cotiza_con_precio_estimado(client, cleaner):
    """El caso exacto del reporte: secciones vacías + precio_venta_base → la
    cotización se guarda con el precio base (antes: $0 y bloqueada)."""
    producto = _crear_producto_con_secciones_vacias(client, cleaner, 3400000)

    r = client.get(f"/api/v1/producto/{producto['id']}/calcular-precio",
                   params={"ancho": 1.0, "largo": 1.0}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["fuente_precio"] == "estimado_sin_estructura", res["fuente_precio"]
    assert res["precio_venta"] == 3400000.0
    assert res["costo_total"] > 0

    # La cotización ahora se guarda (antes la UI bloqueaba con precio 0).
    cliente_obj = crear_cliente(client, cleaner)
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente_obj["id"], [
        {"producto_id": producto["id"], "tipo_item": "FABRICADO", "cantidad": 1, "precio": 3400000},
    ])
    assert cot["total_estimado"] == 3400000.0


def test_producto_con_estructura_real_sigue_jerarquico(client, cleaner, db):
    """Regresión: con elementos reales, la rama jerárquica sigue mandando."""
    producto = _crear_producto_con_secciones_vacias(client, cleaner, 9999999)
    madera = crear_material(client, cleaner, unidad_medida_id=2, costo_base=10000.0)
    entrar_stock_material(client, cleaner, madera["id"], 50)

    # Llenar EBANISTERÍA con un elemento (simula estructura generada o manual).
    secciones = client.get(f"/api/v1/producto/{producto['id']}/receta-estructurada",
                           headers=ADMIN_HEADERS).json()
    sec_eb = next(s for s in secciones if s["nombre"] == "EBANISTERÍA")
    r = client.post(f"/api/v1/seccion/{sec_eb['id']}/elemento", json={
        "seccion_id": sec_eb["id"],
        "nombre_insumo_original": madera["nombre"],
        "material_id_normalizado": madera["id"],
        "cantidad": 2.0,
        "unidad_medida": "m",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cleaner.registrar("elemento_seccion", r.json()["id"])

    r = client.get(f"/api/v1/producto/{producto['id']}/calcular-precio",
                   params={"ancho": 1.6, "largo": 1.9}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    res = r.json()
    # La estructura gana: fuente jerárquica, costo por elementos (2 m × 10000)
    # + 10% gastos de sección = 22000; NO el precio_venta_base.
    assert res["fuente_precio"] == "estructura_de_costos", res["fuente_precio"]
    assert res["costo_total"] == 22000.0


def test_producto_sin_estructura_sin_precio_sigue_sin_definir(client, cleaner):
    """Sin estructura NI precio base → sin_definir (la UI avisa 'Sin precio')."""
    r = client.post("/api/v1/producto/", json={
        "nombre": "mueble sin nada",
        "tipo_producto_id": 1,
        "es_reventa": False,
        "ancho_base": 1.60,
        "largo_base": 1.90,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    producto = r.json()
    cleaner.registrar("producto", producto["id"])

    r = client.get(f"/api/v1/producto/{producto['id']}/calcular-precio",
                   params={"ancho": 1.6, "largo": 1.9}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["fuente_precio"] == "sin_definir"
    assert res["precio_venta"] == 0.0


def test_ciclo_completo_estimado_a_estructura(client, cleaner, db):
    """El ciclo que soñó el dueño: cotiza con estimado → produce → finaliza →
    la estructura se genera y el precio pasa a estructura_de_costos."""
    producto = _crear_producto_con_secciones_vacias(client, cleaner, 3400000)
    madera = crear_material(client, cleaner, unidad_medida_id=2, costo_base=10000.0)
    entrar_stock_material(client, cleaner, madera["id"], 50)
    emp = crear_empleado(client, cleaner, cargo_id=cargos(db)["ebanista"], en_nomina=True)
    cliente_obj = crear_cliente(client, cleaner)

    # 1) Cotiza con el estimado (funciona tras el fix).
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente_obj["id"], [
        {"producto_id": producto["id"], "tipo_item": "FABRICADO", "cantidad": 1, "precio": 3400000},
    ])
    assert cot["total_estimado"] == 3400000.0

    # 2) Produce (orden + etapa + consumo) y finaliza → estructura generada.
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [
        {"producto_id": producto["id"], "tipo_item": "FABRICADO", "cantidad": 1, "precio": 3400000},
    ])
    assert r.status_code == 201, r.text
    detalle_id = pedido["detalles"][0]["id"]
    r = client.post(f"/api/v1/produccion/orden/desde-pedido/{detalle_id}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    orden = r.json()
    cleaner.registrar("orden_produccion", orden["id"])

    etapa = crear_etapa(client, cleaner, orden["id"], area_id(db, "Ebanistería"), emp["id"])
    r = client.put(f"/api/v1/produccion/etapa/{etapa['id']}/estado",
                   params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/produccion/consumo/", json={
        "etapa_produccion_id": etapa["id"],
        "material_id": madera["id"],
        "cantidad": 5,
        "fecha": "2026-08-31T12:00:00",
        "solicitante_empleado_id": emp["id"],
        "observaciones": "ciclo completo",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    consumo = r.json()
    cleaner.registrar("consumo_material", consumo["id"])
    for (gid,) in db.execute(text(
        "SELECT id FROM gasto WHERE observaciones LIKE :pat"
    ), {"pat": f"%[consumo {consumo['id']}]%"}).fetchall():
        cleaner.registrar("gasto", gid)
    r = client.put(f"/api/v1/produccion/etapa/{etapa['id']}/estado",
                   params={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    r = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado",
                   params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json().get("estructura_generada") is True

    # 3) Ahora el precio sale de la estructura real, no del estimado.
    r = client.get(f"/api/v1/producto/{producto['id']}/calcular-precio",
                   params={"ancho": 1.6, "largo": 1.9}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["fuente_precio"] == "estructura_de_costos", res["fuente_precio"]
    # 5 m × 10000 = 50000 + 10% gastos sección = 55000.
    assert res["costo_total"] == 55000.0
    print("[ciclo] estimado 3.400.000 → estructura real:", res["costo_total"])