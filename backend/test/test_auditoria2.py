"""Auditoría fase 2 — regresiones de los hallazgos de la segunda ronda.

Cubre:
  A) Abono USD con TRM sobre cotización COP (1 USD = TRM COP, no 1:1)
  B) DELETE con FK → 409 limpio (cliente/proveedor/material con referencias)
  C) Gastos: tipo_gasto/moneda inexistentes → 400; PATCH con nulos → 400
  D) Cotización: tasa_cambio <= 0 rechazada
  E) Venta con moneda distinta a la cotización → 400

Todos los datos se crean con prefijo test_ y se registran en el cleaner.
"""
from datetime import datetime
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_producto,
    crear_proveedor,
    crear_receta,
    crear_compra,
)


# ---------------------------------------------------------------------------
# Helpers locales
# ---------------------------------------------------------------------------
def _convertir(client, cleaner, id_cotizacion, *, producto_id, precio, cantidad=1,
               adelanto=None, moneda_adelanto_id=None, tasa_cambio_adelanto=None,
               metodo_pago=None):
    """POST /api/v1/pedido/convertir/{id}. Registra el pedido si se creó."""
    body = {
        "detalles": [{
            "producto_id": producto_id,
            "cantidad": cantidad,
            "precio": precio,
            "costo_unitario": 1000,
            "porcentaje_ganancia": 40,
        }],
        "adelanto": adelanto,
        "moneda_adelanto_id": moneda_adelanto_id,
        "tasa_cambio_adelanto": tasa_cambio_adelanto,
        "metodo_pago": metodo_pago,
    }
    r = client.post(f"/api/v1/pedido/convertir/{id_cotizacion}", json=body, headers=ADMIN_HEADERS)
    if r.status_code == 201:
        cleaner.registrar("pedido", r.json()["id"])
    return r


def _buscar_venta(client, cleaner, db, pedido_id):
    venta_id = db.execute(
        text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}
    ).fetchone()
    if not venta_id:
        return None
    venta_id = int(venta_id[0])
    cleaner.registrar("venta", venta_id)
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    assert det.status_code == 200, f"GET /venta/{venta_id} → {det.status_code}: {det.text}"
    body = det.json()
    for p in body.get("pagos", []):
        cleaner.registrar("pago", p["id"])
    for d in body.get("detalles", []):
        cleaner.registrar("detalle_venta", d["id"])
    return body


# ---------------------------------------------------------------------------
# A) Abono USD con TRM sobre cotización COP
# ---------------------------------------------------------------------------
def test_cotizacion_cop_abono_usd_usa_trm(client, cleaner, db):
    """Cotización COP + adelanto USD con TRM 3900 → 200 USD = 780.000 COP.
    (Bug corregido: antes se deducía 1 USD = 1 COP desde la tasa 1.0 de la cotización COP.)"""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=1_000_000, moneda_id=1, tasa_cambio=1.0)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=1_000_000,
                   adelanto=200, moneda_adelanto_id=2, tasa_cambio_adelanto=3900,
                   metodo_pago="EFECTIVO_USD")
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"

    pedido_id = r.json()["id"]
    venta = _buscar_venta(client, cleaner, db, pedido_id)
    assert venta is not None, "no se creó la factura de la conversión"
    pagos = venta.get("pagos", [])
    assert len(pagos) == 1, f"esperado 1 pago, se obtuvo {len(pagos)}"
    pago = pagos[0]
    assert float(pago["monto_en_moneda_base"]) == 200 * 3900, (
        f"esperado {200 * 3900} COP, se obtuvo {pago['monto_en_moneda_base']}"
    )


def test_cotizacion_cop_abono_usd_sin_trm_rechaza(client, cleaner, db):
    """Cotización COP + adelanto USD sin TRM → 400 (el par no es deducible)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=1_000_000, moneda_id=1, tasa_cambio=1.0)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=1_000_000,
                   adelanto=200, moneda_adelanto_id=2, metodo_pago="EFECTIVO_USD")
    assert r.status_code == 400, f"esperado 400, se obtuvo {r.status_code}: {r.text}"
    n_pedido = db.execute(
        text("SELECT COUNT(*) FROM pedido WHERE cotizacion_id = :c"), {"c": cot["id"]}
    ).scalar()
    assert n_pedido == 0, "la conversión inválida no debe dejar pedidos a medias"


def test_cotizacion_usd_abono_cop_derivado(client, cleaner, db):
    """Cotización USD con TRM 3900 + adelanto COP → 1 COP = 1/3900 USD (regresión)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=500, moneda_id=2, tasa_cambio=3900)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=500,
                   adelanto=390_000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    assert r.status_code == 201, f"convertir → {r.status_code}: {r.text}"

    pedido_id = r.json()["id"]
    venta = _buscar_venta(client, cleaner, db, pedido_id)
    assert venta is not None
    pagos = venta.get("pagos", [])
    assert len(pagos) == 1
    pago = pagos[0]
    # 390.000 COP * (1/3900) = 100 USD
    assert round(float(pago["monto_en_moneda_base"]), 2) == 100.0, (
        f"esperado 100 USD, se obtuvo {pago['monto_en_moneda_base']}"
    )


# ---------------------------------------------------------------------------
# B) DELETE con FK → 409 limpio (no 500)
# ---------------------------------------------------------------------------
def test_eliminar_cliente_con_pedido_es_409(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=1000)
    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=1000)
    assert r.status_code == 201, r.text
    cleaner.registrar("venta", db.execute(
        text("SELECT id FROM venta WHERE pedido_id = :p"),
        {"p": r.json()["id"]},
    ).scalar())

    r_del = client.delete(f"/api/v1/cliente/{cliente['id']}", headers=ADMIN_HEADERS)
    assert r_del.status_code == 409, (
        f"esperado 409, se obtuvo {r_del.status_code}: {r_del.text}"
    )


def test_eliminar_proveedor_con_compra_es_409(client, cleaner, db):
    proveedor = crear_proveedor(client, cleaner)
    material = crear_material(client, cleaner)
    compra = crear_compra(client, cleaner, proveedor["id"], material["id"], cantidad=1, costo_unitario=1000)

    r_del = client.delete(f"/api/v1/proveedor/{proveedor['id']}", headers=ADMIN_HEADERS)
    assert r_del.status_code == 409, (
        f"esperado 409, se obtuvo {r_del.status_code}: {r_del.text}"
    )
    cleaner.registrar("detalle_compra", db.execute(
        text("SELECT id FROM detalle_compra WHERE compra_id = :c"), {"c": compra["id"]}
    ).scalar())


def test_eliminar_material_con_receta_es_409(client, cleaner, db):
    material = crear_material(client, cleaner)
    producto = crear_producto(client, cleaner)
    crear_receta(client, cleaner, producto["id"], material["id"], cantidad_base=1.0)

    r_del = client.delete(f"/api/v1/material/{material['id']}", headers=ADMIN_HEADERS)
    assert r_del.status_code == 409, (
        f"esperado 409, se obtuvo {r_del.status_code}: {r_del.text}"
    )


# ---------------------------------------------------------------------------
# C) Gastos: FKs inexistentes y PATCH con nulos
# ---------------------------------------------------------------------------
def test_gasto_tipo_inexistente_es_400(client, cleaner):
    r = client.post("/api/v1/gasto/gastos/", json={
        "tipo_gasto_id": 999999,
        "moneda_id": 1,
        "fecha": str(datetime.today().date()),
        "monto": 100,
        "descripcion": "test_gasto_invalido",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"esperado 400, se obtuvo {r.status_code}: {r.text}"


def test_gasto_moneda_inexistente_es_400(client, cleaner):
    r = client.post("/api/v1/gasto/gastos/", json={
        "tipo_gasto_id": 1,
        "moneda_id": 999999,
        "fecha": str(datetime.today().date()),
        "monto": 100,
        "descripcion": "test_gasto_invalido",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"esperado 400, se obtuvo {r.status_code}: {r.text}"


def test_gasto_patch_tasa_nula_es_400(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=1000)
    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=1000)
    assert r.status_code == 201, r.text
    pedido_id = r.json()["id"]
    venta_id = db.execute(
        text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}
    ).scalar()
    cleaner.registrar("venta", venta_id)
    pagos = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json().get("pagos", [])
    for p in pagos:
        cleaner.registrar("pago", p["id"])

    gasto = client.post("/api/v1/gasto/gastos/", json={
        "tipo_gasto_id": 1,
        "moneda_id": 2,
        "fecha": str(datetime.today().date()),
        "monto": 100,
        "tasa_cambio": 3900,
        "descripcion": "test_gasto_patch",
    }, headers=ADMIN_HEADERS)
    assert gasto.status_code == 201, gasto.text
    cleaner.registrar("gasto", gasto.json()["id"])

    r_patch = client.put(f"/api/v1/gasto/gastos/{gasto.json()['id']}", json={"tasa_cambio": None},
                         headers=ADMIN_HEADERS)
    assert r_patch.status_code == 400, (
        f"esperado 400 al poner tasa_cambio null, se obtuvo {r_patch.status_code}: {r_patch.text}"
    )


# ---------------------------------------------------------------------------
# D) Cotización: tasa_cambio inválida rechazada
# ---------------------------------------------------------------------------
def test_cotizacion_tasa_cero_es_422(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    payload = {
        "cliente_id": cliente["id"],
        "fecha": str(datetime.today().date()),
        "estado": "BORRADOR",
        "total_estimado": 500,
        "moneda_id": 2,
        "tasa_cambio": 0,
        "detalles": [{"producto_id": producto["id"], "cantidad": 1, "precio": 500}],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 422, f"esperado 422, se obtuvo {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# E) Venta con moneda distinta a la cotización → 400
# ---------------------------------------------------------------------------
def test_venta_moneda_distinta_a_cotizacion_es_400(client, cleaner, db):
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=1_000_000, moneda_id=1, tasa_cambio=1.0)
    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=1_000_000)
    assert r.status_code == 201, r.text
    pedido_id = r.json()["id"]
    cleaner.registrar("venta", db.execute(
        text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}
    ).scalar())

    r_venta = client.post("/api/v1/venta/", json={
        "pedido_id": pedido_id, "moneda_id": 2  # USD contra cotización COP
    }, headers=ADMIN_HEADERS)
    assert r_venta.status_code == 400, (
        f"esperado 400, se obtuvo {r_venta.status_code}: {r_venta.text}"
    )


# ---------------------------------------------------------------------------
# F) Normalización de secciones en costeo paramétrico
#    "EBANISTERÍA" (con tilde) debe matchear la regla "EBANISTERIA" y
#    "EBANISTERÍA (NOCHEROS)" debe activar es_nochero.
# ---------------------------------------------------------------------------
def test_normalizar_seccion_canoniza_tildes_y_sufijos():
    from app.modules.productos.cost_service import _normalizar_seccion

    assert _normalizar_seccion("EBANISTERÍA") == "EBANISTERIA"
    assert _normalizar_seccion("TAPICERÍA") == "TAPICERIA"
    assert _normalizar_seccion("PINTURA (CAMA)") == "PINTURA"
    assert _normalizar_seccion("TENDIDO (PATAS)") == "TENDIDO"
    assert _normalizar_seccion("EBANISTERÍA (NOCHEROS)") == "NOCHEROS"
    assert _normalizar_seccion("PINTURA (NOCHEROS)") == "NOCHEROS"
    assert _normalizar_seccion("NOCHEROS") == "NOCHEROS"
    assert _normalizar_seccion("COLA DE PATO") == "COLA_DE_PATO"
    assert _normalizar_seccion(None) == "EBANISTERIA"
    assert _normalizar_seccion("") == "EBANISTERIA"


# ---------------------------------------------------------------------------
# G) POR_RANGO: la cantidad salta según el largo del mueble
#    (regresión del flujo receta → calcular-precio)
# ---------------------------------------------------------------------------
def test_por_rango_aplica_cantidad_segun_largo(client, cleaner):
    from conftest import crear_material

    producto = crear_producto(client, cleaner)
    material = crear_material(client, cleaner, costo_base=100.0)
    r = client.post(f"/api/v1/producto/{producto['id']}/receta", json={
        "material_id": material["id"],
        "cantidad_base": 1,
        "tipo_escala": "POR_RANGO",
        "seccion": "EBANISTERIA",
        "rangos": [
            {"max": 1.0, "cantidad": 4},
            {"max": 1.5, "cantidad": 6},
            {"max": 2.0, "cantidad": 8},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cleaner.registrar("producto_material", r.json()["id"])

    def cant(largo):
        r_calc = client.get(
            f"/api/v1/producto/{producto['id']}/calcular-precio",
            params={"ancho": 1.6, "largo": largo, "ganancia": 0, "iva": 0},
            headers=ADMIN_HEADERS,
        )
        assert r_calc.status_code == 200, r_calc.text
        mats = r_calc.json().get("materiales") or []
        assert mats, r_calc.text
        return mats[0]["cantidad_calculada"]

    assert cant(0.8) == 4.0, "largo 0.8 debe caer en el rango 'hasta 1.0' → 4"
    assert cant(1.2) == 6.0, "largo 1.2 debe caer en el rango 'hasta 1.5' → 6"
    assert cant(1.9) == 8.0, "largo 1.9 debe caer en el rango 'hasta 2.0' → 8"
    assert cant(3.0) == 8.0, "largo 3.0 supera todos los máximos → último rango (8)"
