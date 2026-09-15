"""
test_exhibicion_simple.py — Exhibición simple (sin entradas manuales).

  1. Venta de pieza de exhibición SIN stock: no falla (antes exigía una
     entrada); el costo de la venta es el del producto (precio_costo_base) y
     la utilidad = precio - costo. La pieza se da de baja (activo=False).
  2. Venta de pieza CON stock (fabricada): descuenta normal, reporta el costo
     real y al agotarse se da de baja sola.
  3. Kardex de crudo: ENTRADA/SALIDA/AJUSTE/DAÑO/DEVOLUCION manuales con la
     misma semántica del kardex de productos; SALIDA sin stock → 400.

Ejecutar:  pytest test/test_exhibicion_simple.py -v
"""
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente
from helpers_e2e import (
    crear_cotizacion_multidetalle,
    convertir_cotizacion,
    venta_de_pedido,
)
from test_produccion_exhibicion import (
    crear_producto_exhibicion,
    registrar_inventario_producto,
)


def _vender_pieza(client, cleaner, db, pieza, precio=100000.0):
    cliente = crear_cliente(client, cleaner)
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        {"producto_id": pieza["id"], "tipo_item": "REVENTA",
         "cantidad": 1, "precio": precio, "ancho": 1.6, "largo": 1.9},
    ])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [
        {"producto_id": pieza["id"], "tipo_item": "REVENTA",
         "cantidad": 1, "precio": precio, "ancho": 1.6, "largo": 1.9},
    ])
    assert r.status_code in (200, 201), f"convertir → {r.status_code}: {r.text}"
    venta = venta_de_pedido(client, db, pedido["id"])
    assert venta is not None, "la venta debe auto-generarse al convertir"
    registrar_inventario_producto(db, cleaner, pieza["id"])
    return client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()


def _activo(db, producto_id) -> bool:
    db.expire_all()
    row = db.execute(
        text("SELECT activo FROM producto WHERE id = :p"), {"p": producto_id}
    ).fetchone()
    return bool(row[0])


def test_venta_exhibicion_sin_stock_usa_costo_y_da_de_baja(client, db, cleaner):
    """Pieza de alta simple (sin entradas): se vende con el costo del producto
    (30.000), utilidad 70.000, y desaparece del listado (activo=False)."""
    pieza = crear_producto_exhibicion(client, cleaner, moneda_id=1,
                                      costo_estimado=30000.0, precio_venta=100000.0)
    venta = _vender_pieza(client, cleaner, db, pieza)
    linea = next(d for d in venta["detalles"] if d["producto_id"] == pieza["id"])
    assert abs(float(linea["costo_unitario"]) - 30000.0) < 0.01
    assert abs(float(linea["utilidad"]) - 70000.0) < 0.01
    assert _activo(db, pieza["id"]) is False


def test_venta_exhibicion_con_stock_da_de_baja_al_agotarse(client, db, cleaner):
    """Pieza fabricada (1 und en showroom a costo real 80.000): se descuenta,
    reporta el costo real y al quedar en cero se da de baja sola."""
    from test_produccion_exhibicion import ubicacion_exhibicion_id
    pieza = crear_producto_exhibicion(client, cleaner, moneda_id=1,
                                      costo_estimado=30000.0, precio_venta=100000.0)
    ubi = ubicacion_exhibicion_id(db, cleaner)
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": pieza["id"], "ubicacion_id": ubi,
        "tipo": "ENTRADA", "cantidad": 1, "costo_unitario": 80000.0,
        "observaciones": "Entrada de exhibición (test)",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    cleaner.registrar("movimiento_producto_inventario", r.json()["id"])
    cleaner.registrar("producto_inventario", db.execute(text(
        "SELECT id FROM producto_inventario WHERE producto_id = :p AND ubicacion_id = :u"
    ), {"p": pieza["id"], "u": ubi}).scalar())

    venta = _vender_pieza(client, cleaner, db, pieza)
    linea = next(d for d in venta["detalles"] if d["producto_id"] == pieza["id"])
    assert abs(float(linea["costo_unitario"]) - 80000.0) < 0.01
    assert _activo(db, pieza["id"]) is False


# ---------------------------------------------------------------------------
# Kardex de crudo
# ---------------------------------------------------------------------------

def _crear_crudo(client, cleaner, nombre="TEST CRUDO KARDEX"):
    r = client.post("/api/v1/produccion/crudo/", json={"nombre": nombre}, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cleaner.registrar("producto_crudo_inventario", r.json()["id"])
    return r.json()


def _mov(client, cid, tipo, cantidad, obs=None):
    payload = {"tipo": tipo, "cantidad": cantidad}
    if obs:
        payload["observaciones"] = obs
    return client.post(f"/api/v1/produccion/crudo/{cid}/movimiento", json=payload, headers=ADMIN_HEADERS)


def _stock_crudo(db, cid) -> Decimal:
    db.expire_all()
    return Decimal(str(db.execute(
        text("SELECT cantidad FROM producto_crudo_inventario WHERE id = :i"), {"i": cid}
    ).scalar()))


def _rastrear_kardex(db, cleaner, cid):
    for (mid,) in db.execute(
        text("SELECT id FROM movimiento_crudo WHERE crudo_id = :c"), {"c": cid}
    ).fetchall():
        cleaner._ids.setdefault("movimiento_crudo", set()).add(int(mid))


def test_kardex_crudo_entradas_salidas_ajuste(client, db, cleaner):
    crudo = _crear_crudo(client, cleaner)
    cid = crudo["id"]

    assert _mov(client, cid, "ENTRADA", 10).status_code == 201
    assert _stock_crudo(db, cid) == Decimal("10")
    assert _mov(client, cid, "SALIDA", 4).status_code == 201
    assert _stock_crudo(db, cid) == Decimal("6")
    assert _mov(client, cid, "DAÑO", 1).status_code == 201
    assert _stock_crudo(db, cid) == Decimal("5")
    assert _mov(client, cid, "DEVOLUCION", 2).status_code == 201
    assert _stock_crudo(db, cid) == Decimal("7")
    assert _mov(client, cid, "AJUSTE", 3).status_code == 201
    assert _stock_crudo(db, cid) == Decimal("3")
    _rastrear_kardex(db, cleaner, cid)

    r = client.get(f"/api/v1/produccion/crudo/{cid}/kardex", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    tipos = [m["tipo"] for m in r.json()]
    assert tipos == ["AJUSTE", "DEVOLUCION", "DAÑO", "SALIDA", "ENTRADA"]
    assert all(m["crudo_id"] == cid for m in r.json())


def test_kardex_crudo_salida_sin_stock_rechazada(client, db, cleaner):
    crudo = _crear_crudo(client, cleaner)
    cid = crudo["id"]
    assert _mov(client, cid, "ENTRADA", 2).status_code == 201
    _rastrear_kardex(db, cleaner, cid)

    r = _mov(client, cid, "SALIDA", 5)
    assert r.status_code == 400, r.text
    assert _stock_crudo(db, cid) == Decimal("2")
    r = client.get(f"/api/v1/produccion/crudo/{cid}/kardex", headers=ADMIN_HEADERS)
    assert len(r.json()) == 1, "el movimiento rechazado no deja kardex"


def test_editar_crudo_nombre_y_estado(client, cleaner):
    crudo = _crear_crudo(client, cleaner, nombre="TEST CRUDO EDIT")
    cid = crudo["id"]
    r = client.put(f"/api/v1/produccion/crudo/{cid}", json={"nombre": "TEST CRUDO EDITADO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "TEST CRUDO EDITADO"
    r = client.put(f"/api/v1/produccion/crudo/{cid}", json={"nombre": "  "}, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    r = client.put("/api/v1/produccion/crudo/999999999", json={"nombre": "X"}, headers=ADMIN_HEADERS)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Fiar productos de reventa (igual que insumos)
# ---------------------------------------------------------------------------

def _crear_reventa(client, cleaner, nombre="TEST REVENTA FIAR"):
    r = client.post("/api/v1/producto/", json={
        "nombre": nombre, "tipo_producto_id": 1, "es_reventa": True,
        "moneda_id": 1, "precio_costo_base": 100.0, "activo": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cleaner.registrar("producto", r.json()["id"])
    return r.json()


def test_fiar_producto_crea_cuenta_por_pagar(client, db, cleaner):
    prod = _crear_reventa(client, cleaner)
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": prod["id"], "ubicacion_id": 1, "tipo": "ENTRADA",
        "cantidad": 2, "costo_unitario": 100.0, "fiar": True,
        "proveedor_nombre": "TEST PROV FIAR PROD",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cleaner.registrar("movimiento_producto_inventario", r.json()["id"])
    registrar_inventario_producto(db, cleaner, prod["id"])

    r = client.get("/api/v1/cuentas-por-pagar/", headers=ADMIN_HEADERS)
    cxp = next((x for x in r.json() if x.get("descripcion", "").startswith("Compra fiada: TEST REVENTA")), None)
    assert cxp is not None, "fiar debe crear la cuenta por pagar"
    assert float(cxp["monto"]) == 200.0
    # El proveedor de nombre libre se materializa en el catálogo.
    prov = db.execute(text("SELECT id FROM proveedor WHERE nombre = 'TEST PROV FIAR PROD'")).fetchone()
    assert prov is not None
    cleaner.registrar("proveedor", int(prov[0]))
    # Renglón de la deuda: el producto comprado.
    det = client.get(f"/api/v1/cuentas-por-pagar/", headers=ADMIN_HEADERS)
    assert det.status_code == 200
    # Limpieza por API: borra la deuda con su gasto (el cleaner no cubre CxP).
    assert client.delete(f"/api/v1/cuentas-por-pagar/{cxp['id']}", headers=ADMIN_HEADERS).status_code == 204


def test_fiar_producto_exige_proveedor_y_costo(client, cleaner):
    prod = _crear_reventa(client, cleaner)
    base = {"producto_id": prod["id"], "ubicacion_id": 1, "tipo": "ENTRADA", "cantidad": 1, "fiar": True}
    r = client.post("/api/v1/inventario/producto/movimiento", json={**base, "costo_unitario": 50}, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    r = client.post("/api/v1/inventario/producto/movimiento", json={**base, "proveedor_nombre": "X"}, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
