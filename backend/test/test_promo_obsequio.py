"""
test_regalo_plastico.py (antes test_promo_obsequio.py) — Regalo manual de plástico.

La promo automática (1 plástico por colchón) ya NO existe. Ahora:
  - El regalo se agrega manualmente como una línea REVENTA a precio 0.
  - Solo se permite si hay un colchón (`producto.es_colchon=True`).
  - Máximo 1 plástico por unidad de colchón.
  - El producto debe estar en la variedad curada (promocion_obsequio).
  - Al facturar descuenta stock y su utilidad es 0.

Ejecutar: pytest test/test_promo_obsequio.py -v
"""
from datetime import datetime

from sqlalchemy import text

from app.modules.productos.model import PromocionObsequio
from conftest import ADMIN_HEADERS, crear_cliente


def _crear_reventa(client, cleaner, nombre, costo, venta, es_colchon=False, moneda_id=1):
    payload = {
        "nombre": nombre,
        "tipo_producto_id": 2,
        "es_reventa": True,
        "es_colchon": es_colchon,
        "moneda_id": moneda_id,
        "precio_costo_base": costo,
        "precio_venta_base": venta,
        "activo": True,
    }
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear reventa {nombre} → {r.status_code}: {r.text}"
    body = r.json()
    assert bool(body.get("es_colchon")) is bool(es_colchon)
    cleaner.registrar("producto", body["id"])
    return body


def _stock_inicial(client, cleaner, producto_id, cantidad, costo):
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": producto_id,
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": cantidad,
        "costo_unitario": costo,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"entrada stock → {r.status_code}: {r.text}"
    if r.json().get("id"):
        cleaner.registrar("movimiento_producto_inventario", r.json()["id"])


def _crear_promo(db, cleaner, colchon_id, obsequio_id):
    promo = PromocionObsequio(colchon_id=colchon_id, obsequio_id=obsequio_id, activo=True)
    db.add(promo)
    db.commit()
    cleaner.registrar("promocion_obsequio", promo.id)
    return promo


def _crear_cotizacion(client, cleaner, cliente_id, detalles, estado="BORRADOR"):
    total = round(sum(float(d["precio"]) * float(d["cantidad"]) for d in detalles), 2)
    payload = {
        "cliente_id": cliente_id,
        "fecha": str(datetime.today().date()),
        "estado": estado,
        "total_estimado": total,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": "test regalo plástico",
        "detalles": detalles,
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    if r.status_code == 201:
        body = r.json()
        cleaner.registrar("cotizacion", body["id"])
        for d in body.get("detalles", []):
            cleaner.registrar("detalle_cotizacion", d["id"])
        return r, body
    return r, None


def _convertir(client, cleaner, cliente_id, cot_id, detalles, estado="APROBADO"):
    body = {
        "cotizacion_id": cot_id,
        "cliente_id": cliente_id,
        "fecha": str(datetime.today().date()),
        "estado": estado,
        "detalles": detalles,
    }
    r = client.post(f"/api/v1/pedido/convertir/{cot_id}", json=body, headers=ADMIN_HEADERS)
    if r.status_code == 201:
        pedido = r.json()
        cleaner.registrar("pedido", pedido["id"])
        for d in pedido["detalles"]:
            cleaner.registrar("detalle_pedido", d["id"])
        return r, pedido
    return r, None


def _venta_del_pedido(client, cleaner, cliente_nombre, pedido_id):
    r = client.get("/api/v1/venta/", params={"buscar": cliente_nombre, "limite": 1000}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET /venta/ → {r.status_code}: {r.text}"
    ventas = [v for v in r.json() if v["pedido_id"] == pedido_id]
    assert len(ventas) == 1, f"ventas para pedido {pedido_id}: {ventas}"
    cleaner.registrar("venta", ventas[0]["id"])
    return ventas[0]


def _registrar_detalles(client, cleaner, venta_id):
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    for d in det.get("detalles", []):
        cleaner.registrar("detalle_venta", d["id"])
    return det


def _registrar_artefactos_stock(db, cleaner, *producto_ids):
    for pid in producto_ids:
        for (mid,) in db.execute(
            text("SELECT id FROM movimiento_producto_inventario WHERE producto_id = :p"), {"p": pid}
        ).fetchall():
            cleaner.registrar("movimiento_producto_inventario", mid)
        for (iid,) in db.execute(
            text("SELECT id FROM producto_inventario WHERE producto_id = :p"), {"p": pid}
        ).fetchall():
            cleaner.registrar("producto_inventario", iid)


def _detalle(pid, cantidad, precio, es_obsequio=False):
    return {
        "producto_id": pid,
        "tipo_item": "REVENTA",
        "cantidad": cantidad,
        "precio": precio,
        **({"es_obsequio": True} if es_obsequio else {}),
    }


def test_conversion_no_agrega_obsequio_automatico(client, cleaner, db):
    """Un colchón solo ya NO recibe plástico automático."""
    colchon = _crear_reventa(client, cleaner, "COLCHON SIN REGALO TEST", 200.0, 260.0, es_colchon=True)
    plastico = _crear_reventa(client, cleaner, "PLASTICO NO AUTO TEST", 10.0, 15.0)
    _crear_promo(db, cleaner, colchon["id"], plastico["id"])
    _stock_inicial(client, cleaner, colchon["id"], 3, 200.0)
    _stock_inicial(client, cleaner, plastico["id"], 3, 10.0)

    cliente = crear_cliente(client, cleaner)
    r, cot = _crear_cotizacion(client, cleaner, cliente["id"], [
        _detalle(colchon["id"], 1.0, 260.0),
    ])
    assert r.status_code == 201, r.text

    r, pedido = _convertir(client, cleaner, cliente["id"], cot["id"], [
        _detalle(colchon["id"], 1.0, 260.0),
    ])
    assert r.status_code == 201, r.text
    assert len(pedido["detalles"]) == 1
    assert not any(d.get("es_obsequio") for d in pedido["detalles"])

    venta = _venta_del_pedido(client, cleaner, cliente["nombre"], pedido["id"])
    _registrar_detalles(client, cleaner, venta["id"])
    _registrar_artefactos_stock(db, cleaner, colchon["id"], plastico["id"])


def test_regalo_manual_descuenta_stock_y_utilidad_cero(client, cleaner, db):
    """El regalo agregado a mano se copia una vez, descuenta stock y no genera utilidad."""
    colchon = _crear_reventa(client, cleaner, "COLCHON REGALO MANUAL TEST", 200.0, 260.0, es_colchon=True)
    plastico = _crear_reventa(client, cleaner, "PLASTICO REGALO MANUAL TEST", 10.0, 15.0)
    _crear_promo(db, cleaner, colchon["id"], plastico["id"])
    _stock_inicial(client, cleaner, colchon["id"], 3, 200.0)
    _stock_inicial(client, cleaner, plastico["id"], 3, 10.0)

    cliente = crear_cliente(client, cleaner)
    detalles = [
        _detalle(colchon["id"], 1.0, 260.0),
        _detalle(plastico["id"], 1.0, 0.0, es_obsequio=True),
    ]
    r, cot = _crear_cotizacion(client, cleaner, cliente["id"], detalles)
    assert r.status_code == 201, r.text

    r, pedido = _convertir(client, cleaner, cliente["id"], cot["id"], detalles)
    assert r.status_code == 201, r.text
    assert len(pedido["detalles"]) == 2
    obsequios = [d for d in pedido["detalles"] if d.get("es_obsequio")]
    assert len(obsequios) == 1
    assert obsequios[0]["producto_id"] == plastico["id"]
    assert float(obsequios[0]["precio"]) == 0.0

    venta_row = _venta_del_pedido(client, cleaner, cliente["nombre"], pedido["id"])
    venta = _registrar_detalles(client, cleaner, venta_row["id"])
    obsequios_venta = [d for d in venta["detalles"] if d.get("es_obsequio")]
    assert len(obsequios_venta) == 1
    assert float(obsequios_venta[0]["utilidad"]) == 0.0
    assert float(venta["total"]) == 260.0
    _registrar_artefactos_stock(db, cleaner, colchon["id"], plastico["id"])


def test_regalo_no_puede_superar_colchones(client, cleaner, db):
    """1 colchón + 2 plásticos → 400 desde la creación de la cotización."""
    colchon = _crear_reventa(client, cleaner, "COLCHON MAX UNO TEST", 200.0, 260.0, es_colchon=True)
    plastico = _crear_reventa(client, cleaner, "PLASTICO MAX UNO TEST", 10.0, 15.0)
    _crear_promo(db, cleaner, colchon["id"], plastico["id"])

    cliente = crear_cliente(client, cleaner)
    r, _ = _crear_cotizacion(client, cleaner, cliente["id"], [
        _detalle(colchon["id"], 1.0, 260.0),
        _detalle(plastico["id"], 2.0, 0.0, es_obsequio=True),
    ])
    assert r.status_code == 400, f"debía rechazar → {r.status_code}: {r.text}"
    assert "no pueden superar" in r.json()["detail"].lower()


def test_dos_colchones_pueden_llevar_dos_regalos(client, cleaner, db):
    """2 colchones + 2 plásticos → permitido (máximo 1 por colchón)."""
    colchon = _crear_reventa(client, cleaner, "COLCHON DOS REGALOS TEST", 200.0, 260.0, es_colchon=True)
    plastico = _crear_reventa(client, cleaner, "PLASTICO DOS REGALOS TEST", 10.0, 15.0)
    _crear_promo(db, cleaner, colchon["id"], plastico["id"])
    _stock_inicial(client, cleaner, colchon["id"], 2, 200.0)
    _stock_inicial(client, cleaner, plastico["id"], 2, 10.0)

    cliente = crear_cliente(client, cleaner)
    detalles = [
        _detalle(colchon["id"], 2.0, 260.0),
        _detalle(plastico["id"], 2.0, 0.0, es_obsequio=True),
    ]
    r, cot = _crear_cotizacion(client, cleaner, cliente["id"], detalles)
    assert r.status_code == 201, r.text
    r, pedido = _convertir(client, cleaner, cliente["id"], cot["id"], detalles)
    assert r.status_code == 201, r.text
    obsequios = [d for d in pedido["detalles"] if d.get("es_obsequio")]
    assert len(obsequios) == 1
    assert float(obsequios[0]["cantidad"]) == 2.0

    venta = _venta_del_pedido(client, cleaner, cliente["nombre"], pedido["id"])
    _registrar_detalles(client, cleaner, venta["id"])
    _registrar_artefactos_stock(db, cleaner, colchon["id"], plastico["id"])


def test_regalo_sin_colchon_rechazado(client, cleaner, db):
    """Un plástico de regalo sin ningún colchón en la cotización → 400."""
    no_colchon = _crear_reventa(client, cleaner, "NEVERA SIN COLCHON TEST", 100.0, 180.0)
    plastico = _crear_reventa(client, cleaner, "PLASTICO SIN COLCHON TEST", 10.0, 15.0)
    _crear_promo(db, cleaner, no_colchon["id"], plastico["id"])  # solo para que el plástico esté en la lista

    cliente = crear_cliente(client, cleaner)
    r, _ = _crear_cotizacion(client, cleaner, cliente["id"], [
        _detalle(no_colchon["id"], 1.0, 180.0),
        _detalle(plastico["id"], 1.0, 0.0, es_obsequio=True),
    ])
    assert r.status_code == 400, f"debía rechazar → {r.status_code}: {r.text}"
    assert "no pueden superar" in r.json()["detail"].lower()


def test_regalo_producto_fuera_de_la_variedad_rechazado(client, cleaner, db):
    """El regalo debe ser uno de los plásticos de la lista curada."""
    colchon = _crear_reventa(client, cleaner, "COLCHON VARIEDAD TEST", 200.0, 260.0, es_colchon=True)
    plastico_ok = _crear_reventa(client, cleaner, "PLASTICO VARIEDAD OK TEST", 10.0, 15.0)
    plastico_malo = _crear_reventa(client, cleaner, "PLASTICO VARIEDAD MALO TEST", 12.0, 18.0)
    _crear_promo(db, cleaner, colchon["id"], plastico_ok["id"])

    cliente = crear_cliente(client, cleaner)
    r, _ = _crear_cotizacion(client, cleaner, cliente["id"], [
        _detalle(colchon["id"], 1.0, 260.0),
        _detalle(plastico_malo["id"], 1.0, 0.0, es_obsequio=True),
    ])
    assert r.status_code == 400, f"debía rechazar → {r.status_code}: {r.text}"
    assert "variedad" in r.json()["detail"].lower()


def test_regalo_con_precio_rechazado(client, cleaner, db):
    """Un regalo no puede tener precio > 0."""
    colchon = _crear_reventa(client, cleaner, "COLCHON PRECIO REGALO TEST", 200.0, 260.0, es_colchon=True)
    plastico = _crear_reventa(client, cleaner, "PLASTICO PRECIO REGALO TEST", 10.0, 15.0)
    _crear_promo(db, cleaner, colchon["id"], plastico["id"])

    cliente = crear_cliente(client, cleaner)
    r, _ = _crear_cotizacion(client, cleaner, cliente["id"], [
        _detalle(colchon["id"], 1.0, 260.0),
        _detalle(plastico["id"], 1.0, 15.0, es_obsequio=True),
    ])
    assert r.status_code == 400, f"debía rechazar → {r.status_code}: {r.text}"
    assert "precio 0" in r.json()["detail"].lower()


def test_promocion_devuelve_stock_y_precio(client, cleaner, db):
    """La variedad del cotizador trae nombre, stock y precio de referencia."""
    colchon = _crear_reventa(client, cleaner, "COLCHON VARIEDAD STOCK TEST", 200.0, 260.0, es_colchon=True)
    plastico = _crear_reventa(client, cleaner, "PLASTICO VARIEDAD STOCK TEST", 10.0, 15.0)
    _crear_promo(db, cleaner, colchon["id"], plastico["id"])
    _stock_inicial(client, cleaner, plastico["id"], 4, 10.0)

    r = client.get(
        "/api/v1/promocion-obsequio",
        params={"solo_activas": True},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    fila = next(p for p in r.json() if p["colchon_id"] == colchon["id"])
    assert fila["obsequio_id"] == plastico["id"]
    assert fila["obsequio_nombre"] == plastico["nombre"]
    assert float(fila["obsequio_stock"]) == 4.0
    assert float(fila["obsequio_precio"]) == 15.0

    _registrar_artefactos_stock(db, cleaner, plastico["id"])
