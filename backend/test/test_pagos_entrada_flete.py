"""Regresión: importes explícitos por cuenta cubren mercancía + flete una vez.

Ejecutar únicamente contra una BD de pruebas, nunca contra caja real.
"""
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.modules.reports.model import MetodoCaja
from conftest import ADMIN_HEADERS, _uniq, crear_material, registrar_inventario_de_material


@pytest.fixture
def cuentas_pago(db, cleaner):
    cuentas = [
        MetodoCaja(nombre=_uniq("banco"), codigo=_uniq("banco"), moneda_id=1),
        MetodoCaja(nombre=_uniq("efectivo"), codigo=_uniq("efectivo"), moneda_id=1),
        MetodoCaja(nombre=_uniq("usd"), codigo=_uniq("usd"), moneda_id=2),
    ]
    db.add_all(cuentas)
    db.commit()
    for cuenta in cuentas:
        cleaner.registrar("metodo_caja", cuenta.id)
    return cuentas


def _pagos(cuentas, importes):
    return [
        {
            "metodo_caja_id": cuentas[indice].id,
            "moneda_id": cuentas[indice].moneda_id,
            "monto": monto,
            **({"tasa_pago": 4000} if cuentas[indice].moneda_id == 2 else {}),
        }
        for indice, monto in importes
    ]


def _entrada(client, db, cleaner, cuentas, importes, **cambios):
    material = crear_material(client, cleaner)
    payload = {
        "material_id": material["id"], "tipo": "ENTRADA", "cantidad": 4,
        "costo_unitario": 1000, "llevada": 800,
        "pagos_incluyen_llevada": True, "pagos": _pagos(cuentas, importes),
        **cambios,
    }
    respuesta = client.post("/api/v1/inventario/movimiento", json=payload, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 201, respuesta.text
    movimiento = respuesta.json()
    cleaner.registrar("movimiento_inventario", movimiento["id"])
    registrar_inventario_de_material(db, cleaner, material["id"])
    _registrar_gastos(db, cleaner, material["nombre"])
    return movimiento, material


def _registrar_gastos(db, cleaner, nombre):
    for gasto_id in db.execute(
        text("SELECT id FROM gasto WHERE descripcion LIKE :nombre"), {"nombre": f"%{nombre}%"},
    ).scalars():
        cleaner.registrar("gasto", gasto_id)
        cleaner.registrar_caja_ref(f"Gasto #{gasto_id}")


def _salidas(db, nombre):
    return db.execute(text(
        "SELECT metodo_caja_id, moneda_id, monto, monto_en_moneda_base, referencia "
        "FROM movimiento_caja WHERE concepto LIKE :nombre ORDER BY id"
    ), {"nombre": f"%{nombre}%"}).mappings().all()


@pytest.mark.parametrize("importes", [
    [(0, 4000), (1, 800)],
    [(2, 1), (1, 800)],
    [(2, 0.5), (0, 2000), (1, 800)],
    [(0, 4800)],
])
def test_compra_y_flete_descuentan_exactamente_cada_importe(
    client, db, cleaner, cuentas_pago, importes,
):
    mov, material = _entrada(client, db, cleaner, cuentas_pago, importes)
    salidas = _salidas(db, material["nombre"])
    assert len(salidas) == len(importes), "No debe aparecer un cargo extra por el flete"
    assert [(s["metodo_caja_id"], s["monto"]) for s in salidas] == [
        (cuentas_pago[indice].id, Decimal(str(monto))) for indice, monto in importes
    ]
    assert sum(s["monto_en_moneda_base"] for s in salidas) == Decimal("4800")
    assert mov["llevada_gasto_id"] is None
    assert mov["pagos_incluyen_llevada"] is True


def test_cuenta_unica_sin_lista_tambien_incluye_el_flete(client, db, cleaner, cuentas_pago):
    mov, material = _entrada(
        client, db, cleaner, cuentas_pago, [],
        pagos=None, pagado_desde_metodo_caja_id=cuentas_pago[0].id, moneda_pago_id=1,
    )
    assert [s["monto"] for s in _salidas(db, material["nombre"])] == [Decimal("4800")]
    assert mov["llevada_gasto_id"] is None


def test_entrada_sin_precio_puede_pagar_solo_el_flete(client, db, cleaner, cuentas_pago):
    _, material = _entrada(
        client, db, cleaner, cuentas_pago, [(0, 300), (1, 500)], costo_unitario=None,
    )
    assert [s["monto"] for s in _salidas(db, material["nombre"])] == [Decimal("300"), Decimal("500")]


def test_redondeo_de_divisa_no_exige_fracciones_de_centavo_al_editar(client, db, cleaner, cuentas_pago):
    mov, material = _entrada(client, db, cleaner, cuentas_pago, [(2, 1.2)], costo_unitario=1001)
    respuesta = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "observaciones": "Importe de caja intacto",
    }, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 200, respuesta.text
    _registrar_gastos(db, cleaner, material["nombre"])
    assert [s["monto"] for s in _salidas(db, material["nombre"])] == [Decimal("1.2")]
    assert [s["monto_en_moneda_base"] for s in _salidas(db, material["nombre"])] == [Decimal("4800")]


def test_tolerancia_de_divisa_no_permite_faltantes_mayores_al_redondeo(client, db, cleaner, cuentas_pago):
    material = crear_material(client, cleaner)
    respuesta = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"], "tipo": "ENTRADA", "cantidad": 4,
        "costo_unitario": 1020, "llevada": 800, "pagos_incluyen_llevada": True,
        "pagos": _pagos(cuentas_pago, [(2, 1.2)]),
    }, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 400, respuesta.text
    assert not _salidas(db, material["nombre"])


@pytest.mark.parametrize("total_extra", [0.01, 700, 900])
def test_pagos_que_no_cubren_el_total_rechazan_sin_stock_ni_caja(
    client, db, cleaner, cuentas_pago, total_extra,
):
    material = crear_material(client, cleaner)
    respuesta = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"], "tipo": "ENTRADA", "cantidad": 4,
        "costo_unitario": 1000, "llevada": 800, "pagos_incluyen_llevada": True,
        "pagos": _pagos(cuentas_pago, [(0, 4000), (1, total_extra)]),
    }, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 400, respuesta.text
    assert not _salidas(db, material["nombre"])
    assert db.execute(text(
        "SELECT count(*) FROM movimiento_inventario WHERE material_id=:id"
    ), {"id": material["id"]}).scalar() == 0
    assert db.execute(text(
        "SELECT COALESCE(sum(cantidad), 0) FROM inventario WHERE material_id=:id"
    ), {"id": material["id"]}).scalar() == 0


def test_editar_y_anular_respetan_los_pagos_con_flete(client, db, cleaner, cuentas_pago):
    mov, material = _entrada(client, db, cleaner, cuentas_pago, [(2, 1), (1, 800)])
    respuesta = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "llevada": 1200, "pagos_incluyen_llevada": True,
        "pagos": _pagos(cuentas_pago, [(2, 1), (1, 1200)]),
    }, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 200, respuesta.text
    _registrar_gastos(db, cleaner, material["nombre"])
    assert [s["monto"] for s in _salidas(db, material["nombre"])] == [Decimal("1"), Decimal("1200")]
    detalle = client.get(f"/api/v1/inventario/movimiento/{mov['id']}", headers=ADMIN_HEADERS)
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["pago_llevada"] is None
    assert [Decimal(p["monto"]) for p in detalle.json()["pagos"]] == [Decimal("1"), Decimal("1200")]
    respuesta = client.delete(f"/api/v1/inventario/movimiento/{mov['id']}", headers=ADMIN_HEADERS)
    assert respuesta.status_code == 204, respuesta.text
    assert not _salidas(db, material["nombre"])


def test_corregir_observaciones_no_redistribuye_y_cambiar_total_exige_importes(
    client, db, cleaner, cuentas_pago,
):
    mov, material = _entrada(client, db, cleaner, cuentas_pago, [(2, 1), (1, 800)])
    ruta = f"/api/v1/inventario/movimiento/{mov['id']}"
    respuesta = client.put(ruta, json={"observaciones": "Solo una nota"}, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 200, respuesta.text
    _registrar_gastos(db, cleaner, material["nombre"])
    antes = _salidas(db, material["nombre"])
    assert [s["monto"] for s in antes] == [Decimal("1"), Decimal("800")]
    respuesta = client.put(ruta, json={"llevada": 1200}, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 400, respuesta.text
    assert _salidas(db, material["nombre"]) == antes, "El rechazo debe ser atómico"


@pytest.mark.parametrize("principal", [0, 2])
def test_entrada_antigua_precarga_y_convierte_su_flete_sin_cobrarlo_dos_veces(
    client, db, cleaner, cuentas_pago, principal,
):
    monto_compra = 4000 if principal == 0 else 1
    monto_total = 4800 if principal == 0 else 1.2
    mov, material = _entrada(
        client, db, cleaner, cuentas_pago, [(principal, monto_compra)],
        pagos_incluyen_llevada=False,
    )
    ruta = f"/api/v1/inventario/movimiento/{mov['id']}"
    detalle = client.get(ruta, headers=ADMIN_HEADERS)
    assert detalle.status_code == 200, detalle.text
    cuerpo = detalle.json()
    assert cuerpo["pago_llevada"] is not None
    assert sum(Decimal(p["monto_en_moneda_base"]) for p in cuerpo["pagos"]) == Decimal("4000")
    assert Decimal(cuerpo["pago_llevada"]["monto_en_moneda_base"]) == Decimal("800")
    respuesta = client.put(ruta, json={
        "pagos_incluyen_llevada": True, "pagos": _pagos(cuentas_pago, [(principal, monto_total)]),
    }, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 200, respuesta.text
    _registrar_gastos(db, cleaner, material["nombre"])
    assert [s["monto"] for s in _salidas(db, material["nombre"])] == [Decimal(str(monto_total))]
    assert client.delete(ruta, headers=ADMIN_HEADERS).status_code == 204
    assert not _salidas(db, material["nombre"])


def test_producto_en_usd_no_reconvierte_importes_explicitos_en_cop(client, db, cleaner, cuentas_pago):
    nombre = _uniq("producto_usd")
    respuesta = client.post("/api/v1/producto/", json={
        "nombre": nombre, "tipo_producto_id": 2, "es_reventa": True, "moneda_id": 2,
    }, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 201, respuesta.text
    producto_id = respuesta.json()["id"]
    cleaner.registrar("producto", producto_id)
    respuesta = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": producto_id, "ubicacion_id": 1, "tipo": "ENTRADA",
        "cantidad": 1, "costo_unitario": 3, "llevada": 0.5, "pagos_incluyen_llevada": True,
        "pagos": [
            {"metodo_caja_id": cuentas_pago[0].id, "moneda_id": 1, "monto": 10101, "tasa_pago": 4000},
            {"metodo_caja_id": cuentas_pago[1].id, "moneda_id": 1, "monto": 3899, "tasa_pago": 4000},
        ],
    }, headers=ADMIN_HEADERS)
    assert respuesta.status_code == 201, respuesta.text
    _registrar_gastos(db, cleaner, nombre)
    salidas = _salidas(db, nombre)
    assert [s["monto"] for s in salidas] == [Decimal("10101"), Decimal("3899")]
    assert sum(s["monto_en_moneda_base"] for s in salidas) == Decimal("14000")
