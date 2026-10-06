"""Promo obsequio: por cada colchón REVENTA con promo activa se agrega 1
plástico de regalo a precio 0 al convertir cotización → pedido. El descuento
de stock del obsequio es el flujo normal de REVENTA al facturar."""
from datetime import datetime, timezone

from app.modules.productos.model import PromocionObsequio, Producto
from conftest import (
    ADMIN_HEADERS,
    crear_cotizacion,
    crear_cliente,
    crear_producto,
)


def _crear_reventa(client, cleaner, nombre, costo, venta, moneda_id=1):
    payload = {
        "nombre": nombre,
        "tipo_producto_id": 2,
        "es_reventa": True,
        "moneda_id": moneda_id,
        "precio_costo_base": costo,
        "precio_venta_base": venta,
        "activo": True,
    }
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear reventa {nombre} → {r.status_code}: {r.text}"
    body = r.json()
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


def _registrar_artefactos_stock(db, cleaner, *producto_ids):
    """Registra en el cleaner los movimientos y filas de inventario generados
    por la venta/descuento de stock (no se conocen de antemano); sin esto el
    borrado del producto choca con FKs RESTRICT."""
    from sqlalchemy import text
    for pid in producto_ids:
        for (mid,) in db.execute(
            text("SELECT id FROM movimiento_producto_inventario WHERE producto_id = :p"), {"p": pid}
        ).fetchall():
            cleaner.registrar("movimiento_producto_inventario", mid)
        for (iid,) in db.execute(
            text("SELECT id FROM producto_inventario WHERE producto_id = :p"), {"p": pid}
        ).fetchall():
            cleaner.registrar("producto_inventario", iid)


def _venta_del_pedido(client, cleaner, cliente_nombre, pedido_id):
    """La conversión cotización → pedido crea la factura automáticamente:
    la localiza por cliente y la registra para el teardown."""
    r = client.get("/api/v1/venta/", params={"buscar": cliente_nombre, "limite": 1000}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET /api/v1/venta/ → {r.status_code}: {r.text}"
    ventas = [v for v in r.json() if v["pedido_id"] == pedido_id]
    assert len(ventas) == 1, f"ventas para pedido {pedido_id}: {ventas}"
    cleaner.registrar("venta", ventas[0]["id"])
    return ventas[0]


def _registrar_detalles(client, cleaner, venta_id):
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()
    for d in det.get("detalles", []):
        cleaner.registrar("detalle_venta", d["id"])
    return det


def _crear_cotizacion_reventa(client, cleaner, cliente_id, producto_id, precio, cantidad=1):
    payload = {
        "cliente_id": cliente_id,
        "fecha": str(datetime.today().date()),
        "estado": "BORRADOR",
        "total_estimado": round(precio * cantidad, 2),
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": "test promo obsequio",
        "detalles": [
            {
                "producto_id": producto_id,
                "tipo_item": "REVENTA",
                "cantidad": cantidad,
                "precio": precio,
            }
        ],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear cotización reventa → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("cotizacion", body["id"])
    return body


def test_promo_agrega_obsequio_al_convertir(client, db, cleaner):
    """Colchón con promo activa: al convertir la cotización (que SOLO trae el
    colchón) el pedido obtiene el plástico de regalo a precio 0, con la misma
    cantidad y es_obsequio=True. Dos colchones → dos obsequios."""
    colchon = _crear_reventa(client, cleaner, "COLCHON PROMO TEST", 200.0, 260.0)
    plastico = _crear_reventa(client, cleaner, "PLASTICO PROMO TEST", 10.0, 15.0)
    db.add(PromocionObsequio(colchon_id=colchon["id"], obsequio_id=plastico["id"], activo=True))
    db.commit()
    _stock_inicial(client, cleaner, colchon["id"], 5, 200.0)
    _stock_inicial(client, cleaner, plastico["id"], 5, 10.0)

    cliente = crear_cliente(client, cleaner)
    cot = _crear_cotizacion_reventa(client, cleaner, cliente["id"], colchon["id"], 260.0, cantidad=2)

    body = {
        "cotizacion_id": cot["id"],
        "cliente_id": cliente["id"],
        "fecha": str(datetime.today().date()),
        "estado": "PRODUCCION",
        "detalles": [
            {
                "producto_id": colchon["id"],
                "tipo_item": "REVENTA",
                "cantidad": 2.0,
                "precio": 260.0,
            }
        ],
    }
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json=body, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])

    assert len(pedido["detalles"]) == 2
    obsequios = [d for d in pedido["detalles"] if d.get("es_obsequio")]
    assert len(obsequios) == 1, f"debe haber 1 renglón de obsequio: {pedido['detalles']}"
    obq = obsequios[0]
    assert obq["producto_id"] == plastico["id"]
    assert float(obq["precio"]) == 0.0
    assert float(obq["cantidad"]) == 2.0  # proporcional a los 2 colchones
    # El total del pedido no cambia por el regalo
    detalles = pedido["detalles"]
    assert sum(float(d["precio"]) * float(d["cantidad"]) for d in detalles) == 520.0

    _venta_del_pedido(client, cleaner, cliente["nombre"], pedido["id"])
    _registrar_artefactos_stock(db, cleaner, colchon["id"], plastico["id"])


def test_promo_no_duplica_si_ya_trae_obsequio(client, db, cleaner):
    """Si la cotización ya incluye el renglón de obsequio (carga manual), la
    conversión no lo duplica."""
    colchon = _crear_reventa(client, cleaner, "COLCHON PROMO DUP TEST", 200.0, 260.0)
    plastico = _crear_reventa(client, cleaner, "PLASTICO PROMO DUP TEST", 10.0, 15.0)
    db.add(PromocionObsequio(colchon_id=colchon["id"], obsequio_id=plastico["id"], activo=True))
    db.commit()
    _stock_inicial(client, cleaner, colchon["id"], 2, 200.0)
    _stock_inicial(client, cleaner, plastico["id"], 2, 10.0)

    cliente = crear_cliente(client, cleaner)
    # Cotización con colchón + obsequio ya cotizado a $0
    payload = {
        "cliente_id": cliente["id"],
        "fecha": str(datetime.today().date()),
        "estado": "BORRADOR",
        "total_estimado": 260.0,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": "test promo dup",
        "detalles": [
            {
                "producto_id": colchon["id"],
                "tipo_item": "REVENTA",
                "cantidad": 1.0,
                "precio": 260.0,
            },
            {
                "producto_id": plastico["id"],
                "tipo_item": "REVENTA",
                "cantidad": 1.0,
                "precio": 0.0,
                "es_obsequio": True,
            },
        ],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear cotización → {r.status_code}: {r.text}"
    cot = r.json()
    cleaner.registrar("cotizacion", cot["id"])

    body = {
        "cotizacion_id": cot["id"],
        "cliente_id": cliente["id"],
        "fecha": str(datetime.today().date()),
        "estado": "APROBADO",
        "detalles": [
            {"producto_id": colchon["id"], "tipo_item": "REVENTA", "cantidad": 1.0, "precio": 260.0},
            {"producto_id": plastico["id"], "tipo_item": "REVENTA", "cantidad": 1.0, "precio": 0.0, "es_obsequio": True},
        ],
    }
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json=body, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])

    obsequios = [d for d in pedido["detalles"] if d.get("es_obsequio")]
    assert len(obsequios) == 1, "el obsequio ya venía cotizado: no debe duplicarse"
    assert len(pedido["detalles"]) == 2

    _venta_del_pedido(client, cleaner, cliente["nombre"], pedido["id"])
    _registrar_artefactos_stock(db, cleaner, colchon["id"], plastico["id"])


def test_promo_obsequio_descuenta_stock_y_utilidad_cero(client, db, cleaner):
    """Facturar el pedido: el plástico de regalo sale del stock (SALIDA) y su
    renglón NO genera utilidad negativa (el regalo ya se cobró en el colchón)."""
    colchon = _crear_reventa(client, cleaner, "COLCHON PROMO STOCK TEST", 200.0, 260.0)
    plastico = _crear_reventa(client, cleaner, "PLASTICO PROMO STOCK TEST", 10.0, 15.0)
    db.add(PromocionObsequio(colchon_id=colchon["id"], obsequio_id=plastico["id"], activo=True))
    db.commit()
    _stock_inicial(client, cleaner, colchon["id"], 5, 200.0)
    _stock_inicial(client, cleaner, plastico["id"], 5, 10.0)

    cliente = crear_cliente(client, cleaner)
    cot = _crear_cotizacion_reventa(client, cleaner, cliente["id"], colchon["id"], 260.0, cantidad=1)

    body = {
        "cotizacion_id": cot["id"],
        "cliente_id": cliente["id"],
        "fecha": str(datetime.today().date()),
        "estado": "APROBADO",
        "detalles": [
            {"producto_id": colchon["id"], "tipo_item": "REVENTA", "cantidad": 1.0, "precio": 260.0},
        ],
    }
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json=body, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])

    # La conversión crea la factura automáticamente y descuenta el stock de
    # colchón Y del plástico de regalo (incluida la SALIDA trazable).
    venta_row = _venta_del_pedido(client, cleaner, cliente["nombre"], pedido["id"])
    venta = _registrar_detalles(client, cleaner, venta_row["id"])

    obsequios = [d for d in venta["detalles"] if d.get("es_obsequio")]
    assert len(obsequios) == 1
    obq = obsequios[0]
    assert float(obq["precio"]) == 0.0
    # Utilidad cero (no negativa), aunque el plástico costó algo
    assert float(obq["utilidad"]) == 0.0
    # El total de la venta no incluye el regalo
    assert float(venta["total"]) == 260.0

    _registrar_artefactos_stock(db, cleaner, colchon["id"], plastico["id"])


def test_promo_acumula_mismo_plastico_en_una_linea(client, db, cleaner):
    """Dos colchones distintos que comparten el mismo plástico de regalo
    producen UNA sola línea de obsequio con la cantidad sumada."""
    colchon_a = _crear_reventa(client, cleaner, "COLCHON PROMO A TEST", 200.0, 260.0)
    colchon_b = _crear_reventa(client, cleaner, "COLCHON PROMO B TEST", 300.0, 380.0)
    plastico = _crear_reventa(client, cleaner, "PLASTICO PROMO COMPARTIDO TEST", 10.0, 15.0)
    db.add(PromocionObsequio(colchon_id=colchon_a["id"], obsequio_id=plastico["id"], activo=True))
    db.add(PromocionObsequio(colchon_id=colchon_b["id"], obsequio_id=plastico["id"], activo=True))
    db.commit()
    _stock_inicial(client, cleaner, colchon_a["id"], 2, 200.0)
    _stock_inicial(client, cleaner, colchon_b["id"], 2, 300.0)
    _stock_inicial(client, cleaner, plastico["id"], 5, 10.0)

    cliente = crear_cliente(client, cleaner)
    payload = {
        "cliente_id": cliente["id"],
        "fecha": str(datetime.today().date()),
        "estado": "BORRADOR",
        "total_estimado": 260.0 + 380.0,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": "test promo acumula",
        "detalles": [
            {"producto_id": colchon_a["id"], "tipo_item": "REVENTA", "cantidad": 1.0, "precio": 260.0},
            {"producto_id": colchon_b["id"], "tipo_item": "REVENTA", "cantidad": 1.0, "precio": 380.0},
        ],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear cotización → {r.status_code}: {r.text}"
    cot = r.json()
    cleaner.registrar("cotizacion", cot["id"])

    body = {
        "cotizacion_id": cot["id"],
        "cliente_id": cliente["id"],
        "fecha": str(datetime.today().date()),
        "estado": "APROBADO",
        "detalles": payload["detalles"],
    }
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json=body, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido["detalles"]:
        cleaner.registrar("detalle_pedido", d["id"])

    obsequios = [d for d in pedido["detalles"] if d.get("es_obsequio")]
    assert len(obsequios) == 1, f"una sola línea de obsequio: {pedido['detalles']}"
    assert obsequios[0]["producto_id"] == plastico["id"]
    assert float(obsequios[0]["cantidad"]) == 2.0

    _venta_del_pedido(client, cleaner, cliente["nombre"], pedido["id"])
    _registrar_artefactos_stock(db, cleaner, colchon_a["id"], colchon_b["id"], plastico["id"])
