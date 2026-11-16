"""Correcciones atómicas: importes explícitos, captura fiel y deuda sin duplicados."""
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.hora_ve import hoy_ve
from conftest import ADMIN_HEADERS, _uniq, crear_material, crear_proveedor
from test_compra_inventario_multiple import (
    _cuenta_cop, _crear_segunda_cuenta_cop, _registrar_dependencias_compra,
    _catalogos_para_compra, _registrar_catalogos_nuevos,
)


@pytest.fixture
def entrada(client, cleaner, db):
    material = crear_material(client, cleaner, costo_base=500)
    proveedor = crear_proveedor(client, cleaner)
    cuenta = _cuenta_cop(db)
    tipos = _catalogos_para_compra(db)
    payload = {"operacion_id": str(uuid4()), "fecha": str(hoy_ve()),
        "proveedor_id": proveedor["id"], "recibido_por": "test_transportista",
        "lineas": [{"tipo_item": "MATERIAL", "material_id": material["id"], "cantidad": 10,
            "precio_unitario": 1000, "moneda_precio_id": 1, "llevada_unitaria": 100,
            "descuento_porcentaje": 10, "cliente_nombre": "test_destino", "departamento": "TAPICERIA"}],
        "pagos": [{"metodo_caja_id": cuenta, "monto": 2000, "observacion": "test_abono inicial"}]}
    respuesta = client.post("/api/v1/inventario/compra-multiple", json=payload, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 201, respuesta.text
    compra = respuesta.json()
    _registrar_dependencias_compra(db, cleaner, compra["compra_id"], compra["cuenta_por_pagar_id"])
    _registrar_catalogos_nuevos(db, cleaner, tipos)
    yield compra
    db.rollback()
    _registrar_dependencias_compra(db, cleaner, compra["compra_id"], compra["cuenta_por_pagar_id"])


def _detalle(client, compra):
    respuesta = client.get(f"/api/v1/inventario/entradas/{compra['compra_id']}", headers=ADMIN_HEADERS)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _solicitud(detalle):
    return {"operacion_id": str(uuid4()), "version": detalle["version"],
        "motivo": "test_corrección de captura", "entrada": deepcopy(detalle["datos"])}


def _corregir(client, compra, solicitud):
    return client.put(f"/api/v1/inventario/entradas/{compra['compra_id']}", json=solicitud, headers=ADMIN_HEADERS)


def test_precarga_guarda_precio_bruto_pasada_cliente_y_pago(client, entrada):
    detalle = _detalle(client, entrada)
    linea, pago = detalle["datos"]["lineas"][0], detalle["datos"]["pagos"][0]
    assert Decimal(linea["precio_unitario"]) == 1000
    assert Decimal(linea["descuento_porcentaje"]) == 10
    assert Decimal(linea["llevada_unitaria"]) == 100
    assert linea["cliente_nombre"] == "test_destino"
    assert Decimal(pago["monto"]) == 2000
    assert pago["observacion"] == "test_abono inicial"
    assert Decimal(detalle["saldo_actual"]) == 8000


def test_corrige_cantidad_precio_pasada_y_cuenta_sin_duplicar(client, cleaner, db, entrada):
    detalle = _detalle(client, entrada)
    solicitud = _solicitud(detalle)
    nueva_cuenta = _crear_segunda_cuenta_cop(db, cleaner)
    solicitud["entrada"]["lineas"][0].update(cantidad=8, precio_unitario=2000, llevada_unitaria=200)
    solicitud["entrada"]["pagos"][0].update(metodo_caja_id=nueva_cuenta, monto=6000)
    respuesta = _corregir(client, entrada, solicitud)
    assert respuesta.status_code == 200, respuesta.text
    vigente = _detalle(client, entrada)
    assert Decimal(vigente["total_en_moneda_base"]) == 16000
    assert Decimal(vigente["saldo_actual"]) == 10000
    movimiento_id = detalle["datos"]["lineas"][0]["movimiento_id"]
    assert vigente["datos"]["lineas"][0]["movimiento_id"] == movimiento_id
    caja = db.execute(text("SELECT monto, metodo_caja_id FROM movimiento_caja WHERE id = :id"),
        {"id": detalle["datos"]["pagos"][0]["movimiento_caja_id"]}).one()
    assert caja == (Decimal("6000"), nueva_cuenta)
    assert Decimal(vigente["original"]["lineas"][0]["cantidad"]) == 10
    assert len(vigente["historial"]) == 1
    reintento = _corregir(client, entrada, solicitud)
    assert reintento.status_code == 200, reintento.text
    assert reintento.json() == respuesta.json()
    assert len(_detalle(client, entrada)["historial"]) == 1


@pytest.mark.parametrize("montos,saldo", [([], 10000), ([1000], 9000), ([2000, 3000], 5000), ([10000], 0)])
def test_correccion_admite_cero_uno_varios_pagos_y_fiado(client, entrada, montos, saldo):
    detalle = _detalle(client, entrada)
    solicitud = _solicitud(detalle)
    pago = detalle["datos"]["pagos"][0]
    solicitud["entrada"]["pagos"] = [{**pago, "pago_id": str(uuid4()), "monto": monto} for monto in montos]
    respuesta = _corregir(client, entrada, solicitud)
    assert respuesta.status_code == 200, respuesta.text
    vigente = _detalle(client, entrada)
    assert Decimal(vigente["saldo_actual"]) == saldo
    assert len(vigente["datos"]["pagos"]) == len(montos)


def test_preserva_abonos_desde_gastos_y_rechaza_saldo_negativo(client, cleaner, db, entrada):
    cxp = entrada["cuenta_por_pagar_id"]
    abono = client.post(f"/api/v1/cuentas-por-pagar/{cxp}/abonos", json={
        "fecha": str(hoy_ve()), "metodo_caja_id": _cuenta_cop(db), "monto": 3000,
    }, headers=ADMIN_HEADERS)
    assert abono.status_code == 201, abono.text
    cleaner.registrar_caja_ref(f"CxP #{cxp} abono #{abono.json()['id']}")
    detalle = _detalle(client, entrada)
    solicitud = _solicitud(detalle)
    solicitud["entrada"]["pagos"][0]["monto"] = 8000
    respuesta = _corregir(client, entrada, solicitud)
    assert respuesta.status_code == 400, respuesta.text
    assert "abonos" in respuesta.json()["detail"]
    solicitud["entrada"]["pagos"][0]["monto"] = 1000
    respuesta = _corregir(client, entrada, solicitud)
    assert respuesta.status_code == 200, respuesta.text
    vigente = _detalle(client, entrada)
    assert Decimal(vigente["abonado_posterior"]) == 3000
    assert Decimal(vigente["saldo_actual"]) == 6000


def test_movimiento_posterior_bloquea_cantidad_pero_no_cliente(client, cleaner, db, entrada):
    detalle = _detalle(client, entrada)
    linea = detalle["datos"]["lineas"][0]
    salida = client.post("/api/v1/inventario/movimiento", json={
        "tipo": "SALIDA", "material_id": linea["material_id"], "cantidad": 1,
    }, headers=ADMIN_HEADERS)
    assert salida.status_code == 201, salida.text
    cleaner.registrar("movimiento_inventario", salida.json()["id"])
    solicitud = _solicitud(detalle)
    solicitud["entrada"]["lineas"][0]["cantidad"] = 9
    respuesta = _corregir(client, entrada, solicitud)
    assert respuesta.status_code == 400, respuesta.text
    assert "posterior" in respuesta.json()["detail"]
    solicitud["entrada"]["lineas"][0]["cantidad"] = 10
    solicitud["entrada"]["lineas"][0]["cliente_nombre"] = "test_destino corregido"
    assert _corregir(client, entrada, solicitud).status_code == 200


def test_bloquea_editar_o_borrar_pago_por_caja_y_gastos(client, entrada):
    pago = _detalle(client, entrada)["datos"]["pagos"][0]
    operaciones = [
        ("put", f"/api/v1/gasto/gastos/{pago['gasto_id']}", {"monto": 1}),
        ("delete", f"/api/v1/gasto/gastos/{pago['gasto_id']}", None),
        ("put", f"/api/v1/cuenta/movimiento/{pago['movimiento_caja_id']}", {"monto": 1}),
        ("delete", f"/api/v1/cuenta/movimiento/{pago['movimiento_caja_id']}", None),
    ]
    for metodo, ruta, payload in operaciones:
        respuesta = client.request(metodo, ruta, json=payload, headers=ADMIN_HEADERS)
        assert respuesta.status_code == (409 if "/cuenta/" in ruta else 400), (ruta, respuesta.text)
        assert "entrada" in respuesta.json()["detail"]


def test_version_antigua_no_pisa_otra_correccion(client, entrada):
    solicitud = _solicitud(_detalle(client, entrada))
    assert _corregir(client, entrada, solicitud).status_code == 200
    solicitud["operacion_id"] = str(uuid4())
    respuesta = _corregir(client, entrada, solicitud)
    assert respuesta.status_code == 409, respuesta.text


def test_producto_nuevo_con_pasada_total_y_stock_minimo(client, cleaner, db):
    ubicacion_id = db.execute(text("SELECT id FROM ubicacion WHERE activo = true ORDER BY id LIMIT 1")).scalar()
    tipo_producto_id = db.execute(text("SELECT id FROM tipo_producto ORDER BY id LIMIT 1")).scalar()
    tipos = _catalogos_para_compra(db)
    nombre = _uniq("reventa_pasada")
    nombre_proveedor = _uniq("proveedor_reventa")
    respuesta = client.post("/api/v1/inventario/compra-multiple", json={
        "operacion_id": str(uuid4()), "fecha": str(hoy_ve()), "proveedor_nombre": nombre_proveedor,
        "lineas": [{"tipo_item": "PRODUCTO", "cantidad": 2, "precio_unitario": 100,
            "moneda_precio_id": 1, "llevada_total": 50, "ubicacion_id": int(ubicacion_id),
            "nuevo_producto": {"nombre": nombre, "tipo_producto_id": int(tipo_producto_id),
                "moneda_id": 1, "stock_minimo": 3}}],
        "pagos": [],
    }, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 201, respuesta.text
    compra = respuesta.json()
    assert Decimal(str(compra["total_en_moneda_base"])) == Decimal("250.00")
    _registrar_dependencias_compra(db, cleaner, compra["compra_id"], compra["cuenta_por_pagar_id"])
    _registrar_catalogos_nuevos(db, cleaner, tipos)
    proveedor_id = db.execute(text("SELECT id FROM proveedor WHERE lower(nombre) = lower(:n)"), {"n": nombre_proveedor}).scalar()
    if proveedor_id:
        cleaner.registrar("proveedor", int(proveedor_id))
    producto = db.execute(text(
        "SELECT stock_minimo, precio_costo_base FROM producto WHERE lower(nombre) = lower(:n)"
    ), {"n": nombre}).one()
    assert Decimal(str(producto[0])) == Decimal("3")
    assert Decimal(str(producto[1])) == Decimal("100.00")
