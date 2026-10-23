"""Fecha real de las entradas/salidas de inventario.

El formulario trae la fecha de hoy por defecto y permite registrar un
movimiento de un día anterior (compras capturadas tarde). La fecha elegida
se guarda en el kardex y, cuando la entrada genera gasto o deuda, también
rige esos documentos.

Ejecutar:  pytest test/test_fecha_movimiento_inventario.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import timedelta

import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_material,
    registrar_inventario_de_material,
)
from app.core.hora_ve import hoy_ve


def _cuenta_id(db):
    row = db.execute(text("SELECT id FROM metodo_caja ORDER BY id LIMIT 1")).fetchone()
    return int(row[0]) if row else None


def test_movimiento_material_con_fecha_anterior(client, cleaner, db):
    mat = crear_material(client, cleaner)
    ayer = hoy_ve() - timedelta(days=3)

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 1500,
        "fecha": ayer.isoformat(),
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    registrar_inventario_de_material(db, cleaner, mat["id"])

    # Se guardó el día elegido, anclado al mediodía (convención de fechas
    # retroactivas: el día no se corre por zona horaria).
    assert mov["fecha"].startswith(f"{ayer.isoformat()}T12:00:00"), mov["fecha"]

    # El kardex también lo devuelve con esa fecha.
    r = client.get(
        f"/api/v1/inventario/movimientos/material/{mat['id']}",
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    kardex = r.json()
    assert any(m["id"] == mov["id"] and m["fecha"].startswith(ayer.isoformat()) for m in kardex)


def test_movimiento_material_sin_fecha_usa_hoy(client, cleaner, db):
    mat = crear_material(client, cleaner)

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 1,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    registrar_inventario_de_material(db, cleaner, mat["id"])
    assert mov["fecha"].startswith(hoy_ve().isoformat())


def test_movimiento_material_rechaza_fecha_futura(client, cleaner):
    mat = crear_material(client, cleaner)
    manana = hoy_ve() + timedelta(days=1)

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 1,
        "fecha": manana.isoformat(),
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "futura" in r.json()["detail"].lower()


def test_movimiento_producto_con_fecha_anterior(client, cleaner, db):
    prod = client.post("/api/v1/producto/", json={
        "nombre": _uniq("reventa_fecha"),
        "tipo_producto_id": 2,
        "es_reventa": True,
    }, headers=ADMIN_HEADERS).json()
    cleaner.registrar("producto", prod["id"])
    ayer = hoy_ve() - timedelta(days=1)

    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": prod["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 1,
        "costo_unitario": 100000,
        "fecha": ayer.isoformat(),
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    assert mov["fecha"].startswith(f"{ayer.isoformat()}T12:00:00"), mov["fecha"]

    # Limpieza de kardex/stock del producto.
    for (mid,) in db.execute(text(
        "SELECT id FROM movimiento_producto_inventario WHERE producto_id = :p"
    ), {"p": prod["id"]}).fetchall():
        cleaner.registrar("movimiento_producto_inventario", int(mid))
    for (iid,) in db.execute(text(
        "SELECT id FROM producto_inventario WHERE producto_id = :p"
    ), {"p": prod["id"]}).fetchall():
        cleaner.registrar("producto_inventario", int(iid))


def test_movimiento_crudo_con_fecha_anterior(client, cleaner):
    r = client.post(
        "/api/v1/produccion/crudo/",
        json={"nombre": _uniq("crudo_fecha")},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    crudo = r.json()
    cleaner.registrar("producto_crudo_inventario", crudo["id"])
    ayer = hoy_ve() - timedelta(days=2)

    r = client.post(
        f"/api/v1/produccion/crudo/{crudo['id']}/movimiento",
        json={"tipo": "ENTRADA", "cantidad": 3, "fecha": ayer.isoformat()},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    assert r.json()["fecha"].startswith(f"{ayer.isoformat()}T12:00:00")


def test_entrada_fiada_retroactiva_fecha_la_deuda(client, cleaner, db):
    from conftest import crear_proveedor

    proveedor = crear_proveedor(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=20000.0)
    ayer = hoy_ve() - timedelta(days=2)

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 1,
        "costo_unitario": 20000,
        "proveedor_id": proveedor["id"],
        "fiar": True,
        "fecha": ayer.isoformat(),
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    registrar_inventario_de_material(db, cleaner, mat["id"])

    r = client.get("/api/v1/cuentas-por-pagar/", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    cxp = next(
        (c for c in r.json()
         if c.get("origen_tipo") == "ENTRADA_INVENTARIO" and c.get("origen_id") == mov["id"]),
        None,
    )
    assert cxp is not None, "La entrada fiada debe crear su cuenta por pagar"
    cleaner.registrar("cuenta_por_pagar", cxp["id"])
    cleaner.registrar_gastos_like(db, f"Por Pagar #{cxp['id']}")
    assert str(cxp["fecha"])[:10] == ayer.isoformat(), cxp["fecha"]


def test_entrada_retroactiva_fecha_el_gasto_y_la_caja(client, cleaner, db):
    cuenta = _cuenta_id(db)
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")

    mat = crear_material(client, cleaner, costo_base=5000.0)
    ayer = hoy_ve() - timedelta(days=4)

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 5000,
        "pagado_desde_metodo_caja_id": cuenta,
        "fecha": ayer.isoformat(),
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    registrar_inventario_de_material(db, cleaner, mat["id"])

    gastos = db.execute(text(
        "SELECT id, fecha FROM gasto WHERE descripcion LIKE :pat"
    ), {"pat": f"%{mat['nombre']}%"}).fetchall()
    assert len(gastos) == 1, f"Se esperaba 1 gasto de compra, hay {len(gastos)}"
    gid, gfecha = gastos[0]
    assert str(gfecha)[:10] == ayer.isoformat(), f"gasto.fecha={gfecha}"
    cleaner.registrar("gasto", gid)
    cleaner.registrar_caja_ref(f"Gasto #{gid}")

    caja = db.execute(text(
        "SELECT fecha FROM movimiento_caja WHERE referencia = :r"
    ), {"r": f"Gasto #{gid}"}).fetchone()
    assert caja is not None, "La compra de contado debe mover la caja"
    assert str(caja[0])[:10] == ayer.isoformat(), f"movimiento_caja.fecha={caja[0]}"
