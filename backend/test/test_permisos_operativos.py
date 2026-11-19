"""Producción y cobros operativos sin abrir Cuentas ni el desglose de costos."""
import uuid

import pytest
from sqlalchemy import text

from app.core.hora_ve import hoy_ve
from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_movimiento,
    crear_producto,
    crear_proveedor,
    registrar_inventario_de_material,
    registrar_venta_de_pedido,
)
from test_alcance_produccion import _crear_etapa, _crear_usuario_con_modulos, _pedido_con_orden
from test_compra_inventario_multiple import _crear_segunda_cuenta_cop, _registrar_dependencias_compra


@pytest.fixture
def headers_operativos(db, cleaner):
    return _crear_usuario_con_modulos(db, cleaner, _uniq("operativo"), [
        (modulo, True)
        for modulo in ("produccion", "inventario", "gastos", "ventas", "cotizaciones", "pedidos")
    ])


@pytest.mark.parametrize(("metodo", "ruta"), [
    ("GET", "/orden/999999999/costos-en-vivo"),
    ("GET", "/costo/999999999"),
    ("POST", "/costo/calcular/999999999"),
])
def test_produccion_sin_costos_bloquea_el_desglose_financiero(client, headers_operativos, metodo, ruta):
    respuesta = client.request(metodo, f"/api/v1/produccion{ruta}", json={}, headers=headers_operativos)
    assert respuesta.status_code == 403, respuesta.text


@pytest.mark.parametrize("gestionar", [False, True])
def test_permiso_costos_conserva_lectura_y_controla_escritura(client, db, cleaner, gestionar):
    orden = _pedido_con_orden(client, cleaner)
    calculo = client.post(f"/api/v1/produccion/costo/calcular/{orden['id']}", json={}, headers=ADMIN_HEADERS)
    assert calculo.status_code == 200, calculo.text
    cleaner.registrar("costo_produccion", calculo.json()["id"])
    headers = _crear_usuario_con_modulos(db, cleaner, _uniq("costos"), [
        ("produccion", True), ("costos_produccion", gestionar),
    ])

    for ruta in (f"/orden/{orden['id']}/costos-en-vivo", f"/costo/{orden['id']}"):
        respuesta = client.get(f"/api/v1/produccion{ruta}", headers=headers)
        assert respuesta.status_code == 200, respuesta.text

    respuesta = client.post(f"/api/v1/produccion/costo/calcular/{orden['id']}", json={}, headers=headers)
    assert respuesta.status_code == (200 if gestionar else 403), respuesta.text


def test_produccion_gestiona_mano_obra_y_tarifas_sin_ver_costos(client, db, cleaner):
    """Paola: Producción con gestión registra MO y crea tarifas, pero no ve el
    desglose de costos ni puede consultar el costo guardado de la orden."""
    orden = _pedido_con_orden(client, cleaner)
    headers = _crear_usuario_con_modulos(db, cleaner, _uniq("mo_sin_costos"), [("produccion", True)])
    etapa = _crear_etapa(client, orden["id"], headers)
    assert etapa.status_code == 201, etapa.text
    etapa_id = etapa.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)
    estado = client.put(
        f"/api/v1/produccion/etapa/{etapa_id}/estado?estado=EN_PROCESO", headers=headers,
    )
    assert estado.status_code == 200, estado.text

    tarifario = client.get("/api/v1/produccion/opciones-costo-produccion", headers=headers)
    assert tarifario.status_code == 200, tarifario.text
    tarifa = client.post("/api/v1/produccion/opciones-costo-produccion", json={
        "area_id": 1, "descripcion": _uniq("tarifa_mo"), "precio": 2500,
    }, headers=headers)
    assert tarifa.status_code == 201, tarifa.text
    cleaner.registrar("precio_produccion", tarifa.json()["id"])

    mano = client.post("/api/v1/produccion/mano-obra/", json={
        "etapa_produccion_id": etapa_id,
        "empleado_id": 3,
        "monto": 2500,
        "porcentaje_recargo": 0,
        "precio_produccion_id": tarifa.json()["id"],
        "observaciones": "MO registrada por Producción sin acceso a Costos",
    }, headers=headers)
    assert mano.status_code == 201, mano.text
    cleaner.registrar("mano_obra", mano.json()["id"])

    for ruta in (f"/orden/{orden['id']}/costos-en-vivo", f"/costo/{orden['id']}"):
        respuesta = client.get(f"/api/v1/produccion{ruta}", headers=headers)
        assert respuesta.status_code == 403, respuesta.text


def test_produccion_lectura_ve_tarifario_pero_no_crea_mo_ni_tarifas(client, db, cleaner):
    headers = _crear_usuario_con_modulos(db, cleaner, _uniq("prod_lectura"), [("produccion", False)])
    tarifario = client.get("/api/v1/produccion/opciones-costo-produccion", headers=headers)
    assert tarifario.status_code == 200, tarifario.text
    tarifa = client.post("/api/v1/produccion/opciones-costo-produccion", json={
        "area_id": 1, "descripcion": _uniq("tarifa_lectura"), "precio": 1000,
    }, headers=headers)
    assert tarifa.status_code == 403, tarifa.text
    mano = client.post("/api/v1/produccion/mano-obra/", json={
        "etapa_produccion_id": 1, "empleado_id": 3, "monto": 1000,
    }, headers=headers)
    assert mano.status_code == 403, mano.text


def test_permiso_costos_no_sustituye_el_permiso_produccion(client, db, cleaner):
    headers = _crear_usuario_con_modulos(db, cleaner, _uniq("solo_costos"), [("costos_produccion", True)])
    respuesta = client.get("/api/v1/produccion/opciones-costo-produccion", headers=headers)
    assert respuesta.status_code == 403, respuesta.text


@pytest.mark.parametrize("ruta", ["/cuenta/", "/cuenta/resumen", "/cuenta/movimientos", "/cuenta/libro", "/prestamo/resumen"])
def test_operativo_no_consulta_cuentas_saldos_ni_libros(client, headers_operativos, ruta):
    respuesta = client.get(f"/api/v1{ruta}", headers=headers_operativos)
    assert respuesta.status_code == 403, respuesta.text


def test_selector_de_cuentas_sigue_disponible_sin_saldos(client, db, cleaner, headers_operativos):
    cuenta_id = _crear_segunda_cuenta_cop(db, cleaner)
    respuesta = client.get("/api/v1/cuenta/operativas", headers=headers_operativos)
    assert respuesta.status_code == 200, respuesta.text
    cuenta = next(cuenta for cuenta in respuesta.json() if cuenta["id"] == cuenta_id)
    assert cuenta["moneda_codigo"] == "COP"
    campos_permitidos = {"id", "nombre", "codigo", "activo", "orden", "moneda_id", "moneda_codigo", "moneda_simbolo"}
    assert all(set(item) <= campos_permitidos for item in respuesta.json())
    assert all(item["activo"] for item in respuesta.json())
    for ruta in ("/reports/metodos-caja", "/cuentas-por-pagar/", "/cuentas-por-pagar/resumen"):
        respuesta = client.get(f"/api/v1{ruta}", headers=headers_operativos)
        assert respuesta.status_code == 200, respuesta.text


def test_operativo_registra_abono_inicial_y_cobro_sin_modulo_cuentas(client, db, cleaner, headers_operativos):
    cuenta_id = _crear_segunda_cuenta_cop(db, cleaner)
    codigo_cuenta = db.execute(text("SELECT codigo FROM metodo_caja WHERE id = :id"), {"id": cuenta_id}).scalar_one()
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cotizacion = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], 10000, headers=headers_operativos)
    respuesta = client.post(f"/api/v1/pedido/convertir/{cotizacion['id']}", json={
        "detalles": [{"producto_id": producto["id"], "cantidad": 1, "precio": 10000}],
        "adelanto": 1000, "metodo_pago": codigo_cuenta, "fecha_adelanto": str(hoy_ve()),
    }, headers=headers_operativos)
    assert respuesta.status_code == 201, respuesta.text
    pedido = respuesta.json()
    cleaner.registrar("pedido", pedido["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    venta_id = db.execute(text("SELECT id FROM venta WHERE pedido_id = :id"), {"id": pedido["id"]}).scalar_one()
    cobro = client.post("/api/v1/pago/", json={
        "venta_id": venta_id, "moneda_id": 1, "monto": 2000,
        "metodo_pago": codigo_cuenta, "fecha": f"{hoy_ve()}T12:00:00",
    }, headers=headers_operativos)
    assert cobro.status_code == 201, cobro.text
    pagos = db.execute(text("SELECT id FROM pago WHERE venta_id = :id"), {"id": venta_id}).scalars().all()
    cleaner.registrar_muchos("pago", pagos)
    movimientos = db.execute(text(
        "SELECT id, metodo_caja_id, monto FROM movimiento_caja WHERE pago_id = ANY(:ids) ORDER BY id"
    ), {"ids": pagos}).all()
    cleaner.registrar_muchos("movimiento_caja", [fila.id for fila in movimientos])
    assert len(movimientos) == 2
    assert all(fila.metodo_caja_id == cuenta_id for fila in movimientos)
    assert sum(fila.monto for fila in movimientos) == 3000


def test_operativo_compra_y_paga_deuda_sin_abrir_cuentas(client, db, cleaner, headers_operativos):
    cuenta_id = _crear_segunda_cuenta_cop(db, cleaner)
    material = crear_material(client, cleaner)
    proveedor = crear_proveedor(client, cleaner)
    respuesta = client.post("/api/v1/inventario/compra-multiple", json={
        "operacion_id": str(uuid.uuid4()), "fecha": str(hoy_ve()),
        "proveedor_id": proveedor["id"],
        "lineas": [{"tipo_item": "MATERIAL", "material_id": material["id"], "cantidad": 10, "precio_unitario": 1000}],
        "pagos": [{"metodo_caja_id": cuenta_id, "monto": 2000}],
    }, headers=headers_operativos)
    assert respuesta.status_code == 201, respuesta.text
    compra = respuesta.json()
    cxp_id = compra["cuenta_por_pagar_id"]
    _registrar_dependencias_compra(db, cleaner, compra["compra_id"], cxp_id)
    assert float(compra["saldo_en_moneda_base"]) == 8000
    respuesta = client.post(f"/api/v1/cuentas-por-pagar/{cxp_id}/abonos", json={
        "fecha": str(hoy_ve()), "monto": 3000, "metodo_caja_id": cuenta_id,
    }, headers=headers_operativos)
    assert respuesta.status_code == 201, respuesta.text
    cleaner.registrar_caja_ref(f"CxP #{cxp_id} abono #{respuesta.json()['id']}")
    deuda = db.execute(text(
        "SELECT moneda_id, monto - monto_pagado AS saldo FROM cuenta_por_pagar WHERE id = :id"
    ), {"id": cxp_id}).one()
    assert deuda.moneda_id == 1  # La deuda de inventario permanece en COP.
    assert float(deuda.saldo) == 5000


def test_operativo_consume_y_finaliza_sin_acceso_al_desglose(client, db, cleaner, headers_operativos):
    orden = _pedido_con_orden(client, cleaner)
    material = crear_material(client, cleaner, costo_base=1000)
    respuesta, _ = crear_movimiento(client, cleaner, material["id"], "ENTRADA", 10)
    assert respuesta.status_code in (200, 201), respuesta.text
    registrar_inventario_de_material(db, cleaner, material["id"])
    respuesta = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1, "estado": "ASIGNADA", "empleado_responsable_id": 3,
    }, headers=headers_operativos)
    assert respuesta.status_code == 201, respuesta.text
    etapa_id = respuesta.json()["id"]
    cleaner.registrar("etapa_produccion", etapa_id)
    respuesta = client.put(f"/api/v1/produccion/etapa/{etapa_id}/estado?estado=EN_PROCESO", headers=headers_operativos)
    assert respuesta.status_code == 200, respuesta.text
    respuesta = client.post("/api/v1/produccion/consumo/", json={
        "etapa_produccion_id": etapa_id, "material_id": material["id"], "cantidad": 2,
        "solicitante_empleado_id": 3, "fecha": f"{hoy_ve()}T12:00:00",
    }, headers=headers_operativos)
    assert respuesta.status_code == 201, respuesta.text
    consumo_id = respuesta.json()["id"]
    cleaner.registrar("consumo_material", consumo_id)
    cleaner.registrar_gastos_like(db, f"[consumo {consumo_id}]")
    registrar_inventario_de_material(db, cleaner, material["id"])
    respuesta = client.get(f"/api/v1/produccion/etapa/{etapa_id}/referencia-receta", headers=headers_operativos)
    assert respuesta.status_code == 200, respuesta.text
    respuesta = client.put(f"/api/v1/produccion/etapa/{etapa_id}/estado?estado=COMPLETADA", headers=headers_operativos)
    assert respuesta.status_code == 200, respuesta.text
    respuesta = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado?estado=FINALIZADA", headers=headers_operativos)
    assert respuesta.status_code == 200, respuesta.text
    costo = client.get(f"/api/v1/produccion/costo/{orden['id']}", headers=ADMIN_HEADERS)
    assert costo.status_code == 200, costo.text
    cleaner.registrar("costo_produccion", costo.json()["id"])
    assert costo.json()["costo_material"] == 2000
    respuesta = client.get(f"/api/v1/produccion/costo/{orden['id']}", headers=headers_operativos)
    assert respuesta.status_code == 403, respuesta.text
    envios = db.execute(text("SELECT id FROM envio WHERE pedido_id = :id"), {
        "id": orden["detalle_pedido"]["pedido"]["id"],
    }).scalars().all()
    cleaner.registrar_muchos("envio", envios)
