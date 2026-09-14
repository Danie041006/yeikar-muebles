"""
Piezas de EXHIBICIÓN: tipo de orden explícito, entrada al showroom con el
costo real en la moneda del producto, y venta que reporta el costo real (no
el estimado de la cotización).

Flujo cubierto (el que el dueño pidió explícito):
  producción (Kanban, orden EXHIBICION) → costos + nómina destajo → la pieza
  entra al stock del showroom → se vende de stock → utilidad = precio - costo
  real de fabricación.
"""
from decimal import Decimal
from datetime import date

from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente, crear_producto
from helpers_e2e import (
    area_id,
    cargos,
    crear_empleado,
    crear_etapa,
    crear_cotizacion_multidetalle,
    convertir_cotizacion,
    avanzar_etapa,
    registrar_mano_obra,
    finalizar_orden,
    venta_de_pedido,
    _uniq,
)


def crear_producto_exhibicion(client, cleaner, nombre=None, moneda_id=1,
                              costo_estimado=30000.0, precio_venta=100000.0) -> dict:
    payload = {
        "nombre": nombre or _uniq("exh"),
        "tipo_producto_id": 2,
        "es_reventa": False,
        "es_exhibicion": True,
        "moneda_id": moneda_id,
        "precio_costo_base": costo_estimado,
        "precio_venta_base": precio_venta,
        "activo": True,
    }
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_producto_exhibicion → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("producto", body["id"])
    return body


def crear_orden(client, cleaner, payload) -> dict:
    r = client.post("/api/v1/produccion/orden/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_orden → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("orden_produccion", body["id"])
    return body


def ubicacion_exhibicion_id(db, cleaner) -> int:
    row = db.execute(text("SELECT id FROM ubicacion WHERE nombre = 'EXHIBICIÓN'")).fetchone()
    if row:
        return int(row[0])
    ubi_id = db.execute(text(
        "INSERT INTO ubicacion (nombre, descripcion, tipo, activo) "
        "VALUES ('EXHIBICIÓN', 'Showroom (test)', 'PUNTO_VENTA', TRUE) RETURNING id"
    )).scalar()
    db.commit()
    cleaner.registrar("ubicacion", ubi_id)
    return int(ubi_id)


def tasa_usd_cop(db, cleaner) -> Decimal:
    """Tasa USD→COP vigente; si la BD no tiene ninguna, registra 3900.
    Debe llamarse ANTES de cualquier conversión (sin tasa, el ERP no convierte)."""
    row = db.execute(text(
        "SELECT valor FROM tasa_cambio "
        "WHERE moneda_origen_id = 2 AND moneda_destino_id = 1 "
        "ORDER BY fecha DESC LIMIT 1"
    )).fetchone()
    if row:
        return Decimal(str(row[0]))
    db.execute(text(
        "INSERT INTO tasa_cambio (moneda_origen_id, moneda_destino_id, valor, fecha) "
        "VALUES (2, 1, 3900, :f)"
    ), {"f": date.today()})
    db.commit()
    cleaner.registrar("tasa_cambio", db.execute(text(
        "SELECT id FROM tasa_cambio WHERE moneda_origen_id = 2 "
        "AND moneda_destino_id = 1 ORDER BY fecha DESC LIMIT 1"
    )).scalar())
    return Decimal("3900")


def registrar_inventario_producto(db, cleaner, producto_id):
    """Registra en el cleaner todos los movimientos y filas de inventario de
    un producto (incluye los creados por la venta o por la producción)."""
    for (mid,) in db.execute(text(
        "SELECT id FROM movimiento_producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchall():
        cleaner.registrar("movimiento_producto_inventario", mid)
    for (iid,) in db.execute(text(
        "SELECT id FROM producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchall():
        cleaner.registrar("producto_inventario", iid)


# ---------------------------------------------------------------------------
# 1. El tipo de la orden lo determina el destino (producto), no el cliente
# ---------------------------------------------------------------------------
def test_tipo_de_orden_se_deriva_del_destino(client, db, cleaner):
    producto = crear_producto(client, cleaner)

    orden_stock = crear_orden(client, cleaner, {
        "estado": "PENDIENTE", "es_stock": True, "producto_id": producto["id"],
    })
    assert orden_stock["tipo"] == "STOCK"
    assert orden_stock["es_stock"] is True

    pieza = crear_producto_exhibicion(client, cleaner)
    orden_exh = crear_orden(client, cleaner, {
        "estado": "PENDIENTE", "es_stock": True, "producto_id": pieza["id"],
    })
    assert orden_exh["tipo"] == "EXHIBICION"


def test_tipo_exhibicion_no_se_puede_etiquetar_mal(client, cleaner):
    """Un tipo explícito que contradice el destino real se rechaza (400)."""
    pieza = crear_producto_exhibicion(client, cleaner)
    r = client.post("/api/v1/produccion/orden/", json={
        "estado": "PENDIENTE", "es_stock": True,
        "producto_id": pieza["id"], "tipo": "STOCK",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400
    assert "EXHIBICION" in r.json()["detail"]

    r = client.post("/api/v1/produccion/orden/", json={
        "estado": "PENDIENTE", "es_stock": True,
        "producto_id": pieza["id"], "tipo": "INVENTO",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 2. Finalizar una EXHIBICION: entrada al showroom con el costo real,
#    convertido a la moneda del producto
# ---------------------------------------------------------------------------
def test_finalizar_exhibicion_entrada_showroom_moneda_producto(client, db, cleaner):
    pieza = crear_producto_exhibicion(client, cleaner, moneda_id=2, precio_venta=500.0)
    tasa = tasa_usd_cop(db, cleaner)  # ANTES de finalizar: sin tasa no hay costo
    orden = crear_orden(client, cleaner, {
        "estado": "PENDIENTE", "es_stock": True, "producto_id": pieza["id"],
    })

    emp = crear_empleado(client, cleaner, cargo_id=cargos(db)["ebanista"], en_nomina=True)
    etapa = crear_etapa(client, cleaner, orden["id"], area_id(db, "Ebanistería"), emp["id"])
    avanzar_etapa(client, etapa["id"], "EN_PROCESO")
    registrar_mano_obra(client, cleaner, etapa["id"], emp["id"], monto=50000.0)
    avanzar_etapa(client, etapa["id"], "COMPLETADA")
    finalizada = finalizar_orden(client, orden["id"])
    assert finalizada["tipo"] == "EXHIBICION"
    registrar_inventario_producto(db, cleaner, pieza["id"])

    costo_esperado_usd = round(50000.0 / float(tasa), 2)
    ubi = ubicacion_exhibicion_id(db, cleaner)

    fila = db.execute(text(
        "SELECT cantidad, costo_promedio FROM producto_inventario "
        "WHERE producto_id = :p AND ubicacion_id = :u"
    ), {"p": pieza["id"], "u": ubi}).fetchone()
    assert fila is not None, "la pieza no entró al stock del showroom"
    assert float(fila[0]) == 1.0
    assert abs(float(fila[1]) - costo_esperado_usd) < 0.01

    mov = db.execute(text(
        "SELECT id FROM movimiento_producto_inventario "
        "WHERE producto_id = :p AND tipo = 'ENTRADA' "
        "AND referencia_tipo = 'PRODUCCION_EXHIBICION' AND referencia_id = :o"
    ), {"p": pieza["id"], "o": orden["id"]}).fetchone()
    assert mov is not None, "falta el movimiento de entrada por producción"


# ---------------------------------------------------------------------------
# 3. Vender la pieza: el costo de la venta es el real del inventario
# ---------------------------------------------------------------------------
def test_venta_exhibicion_reporta_costo_real(client, db, cleaner):
    # Costo estimado 30.000 (lo que pondría el alta manual); costo REAL 80.000.
    pieza = crear_producto_exhibicion(client, cleaner, moneda_id=1,
                                      costo_estimado=30000.0, precio_venta=100000.0)
    ubi = ubicacion_exhibicion_id(db, cleaner)
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": pieza["id"], "ubicacion_id": ubi,
        "tipo": "ENTRADA", "cantidad": 1, "costo_unitario": 80000.0,
        "observaciones": "Entrada de exhibición (test)",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"entrada showroom → {r.status_code}: {r.text}"
    cleaner.registrar("movimiento_producto_inventario", r.json()["id"])
    cleaner.registrar("producto_inventario", db.execute(text(
        "SELECT id FROM producto_inventario WHERE producto_id = :p AND ubicacion_id = :u"
    ), {"p": pieza["id"], "u": ubi}).scalar())
    cliente = crear_cliente(client, cleaner)
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        {"producto_id": pieza["id"], "tipo_item": "REVENTA",
         "cantidad": 1, "precio": 100000.0, "ancho": 1.6, "largo": 1.9},
    ])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [
        {"producto_id": pieza["id"], "tipo_item": "REVENTA",
         "cantidad": 1, "precio": 100000.0, "ancho": 1.6, "largo": 1.9},
    ])
    assert r.status_code in (200, 201), f"convertir → {r.status_code}: {r.text}"
    assert pedido["estado"] == "APROBADO", "una pieza de exhibición no pasa por producción"

    venta = venta_de_pedido(client, db, pedido["id"])
    assert venta is not None
    # El listado no trae detalles: pedir el expediente completo de la venta.
    venta = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    registrar_inventario_producto(db, cleaner, pieza["id"])
    linea = next(d for d in venta["detalles"] if d["producto_id"] == pieza["id"])
    assert linea["tipo_item"] == "REVENTA"
    assert abs(linea["costo_unitario"] - 80000.0) < 0.01, (
        "la venta debe reportar el costo real del showroom (80.000), "
        f"no el estimado ({linea['costo_unitario']})"
    )
    assert abs(linea["utilidad"] - 20000.0) < 0.01
    # El stock del showroom quedó en cero tras la venta.
    restante = db.execute(text(
        "SELECT cantidad FROM producto_inventario WHERE producto_id = :p AND ubicacion_id = :u"
    ), {"p": pieza["id"], "u": ubi}).scalar()
    assert float(restante) == 0.0


# ---------------------------------------------------------------------------
# 4. Receta de referencia (hoja de trabajo) para una orden SIN pedido:
#    antes devolvía 404 siempre que la orden no tuviera detalle de pedido;
#    ahora toma el producto de la propia orden (EXHIBICION/STOCK) y expone
#    el contexto del documento (orden_id, dims base, fotos, seccion).
# ---------------------------------------------------------------------------
def test_referencia_receta_orden_sin_pedido(client, db, cleaner):
    from helpers_e2e import area_id as _area_id, crear_empleado

    pieza = crear_producto_exhibicion(client, cleaner)  # base 1.60 × 1.90
    orden = crear_orden(client, cleaner, {
        "estado": "PENDIENTE", "es_stock": True, "producto_id": pieza["id"],
    })
    emp = crear_empleado(client, cleaner)
    etapa = crear_etapa(client, cleaner, orden["id"], _area_id(db, "Ebanistería"), emp["id"])

    r = client.get(f"/api/v1/produccion/etapa/{etapa['id']}/referencia-receta",
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"referencia-receta (sin pedido) → {r.status_code}: {r.text}"
    data = r.json()

    assert data["orden_id"] == orden["id"]
    assert data["pedido_id"] is None
    assert data["seccion_actual"] == "EBANISTERIA"
    # Sin detalle de pedido: cae a las dimensiones base del producto
    assert data["dimensiones"]["ancho"] == 1.60
    assert data["dimensiones"]["largo"] == 1.90
    assert data["producto_fotos"] == []


# ---------------------------------------------------------------------------
# 5. Regresión: la receta de referencia con producto CON FOTO debe responder
#    200 (antes explotaba con 500: producto.fotos entrega dicts, no objetos).
#    Este caso alimenta la Hoja de Trabajo del Kanban.
# ---------------------------------------------------------------------------
def test_referencia_receta_con_foto_del_producto(client, db, cleaner):
    import uuid as _uuid
    from helpers_e2e import area_id as _area_id, crear_empleado

    pieza = crear_producto_exhibicion(client, cleaner)
    # Adjunto PRODUCTO real (misma vía que el alta de piezas: uuid público)
    db.execute(text(
        "INSERT INTO adjunto (entidad_tipo, entidad_id, uuid, nombre_original, mime, tamano, archivo) "
        "VALUES ('PRODUCTO', :p, :u, 'foto.webp', 'image/webp', 4, :b)"
    ), {"p": pieza["id"], "u": str(_uuid.uuid4()), "b": b"abcd"})
    db.commit()
    aid = db.execute(text(
        "SELECT id FROM adjunto WHERE entidad_tipo = 'PRODUCTO' AND entidad_id = :p"
    ), {"p": pieza["id"]}).scalar()
    cleaner.registrar("adjunto", int(aid))

    orden = crear_orden(client, cleaner, {
        "estado": "PENDIENTE", "es_stock": True, "producto_id": pieza["id"],
    })
    emp = crear_empleado(client, cleaner)
    etapa = crear_etapa(client, cleaner, orden["id"], _area_id(db, "Ebanistería"), emp["id"])

    r = client.get(f"/api/v1/produccion/etapa/{etapa['id']}/referencia-receta",
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200, (
        f"con foto del producto debe ser 200 → {r.status_code}: {r.text}"
    )
    data = r.json()
    fotos = data["producto_fotos"]
    assert len(fotos) == 1, f"debe exponer la foto del producto: {data}"
    assert fotos[0]["url"].startswith("/api/v1/adjunto/publico/"), fotos
