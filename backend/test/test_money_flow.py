"""
test_money_flow.py — Flujo real de dinero del ERP YEIKAR (tests de integración).

Cubre la cadena: cotización → conversión a pedido (factura auto-generada) →
abonos en distintas monedas (COP/USD/VES), tasa congelada de la cotización,
control de saldos (sobrepago), idempotencia de conversión, eliminación de
facturas con pagos y consistencia de cuentas por cobrar.

Infraestructura: fixtures `client`, `db`, `cleaner` y helpers de
`conftest.py`. Cada test crea datos NUEVOS (cliente/producto/cotización
propios) para no colisionar; los IDs se registran en el `cleaner`.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_money_flow.py -v
"""
import re
import unicodedata

import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_pago,
    crear_producto,
)


# ---------------------------------------------------------------------------
# Helpers locales (no tocan conftest.py; registran lo creado en el cleaner)
# ---------------------------------------------------------------------------
def _convertir(client, cleaner, id_cotizacion, *, producto_id, precio, cantidad=1,
               adelanto=None, moneda_adelanto_id=None, tasa_cambio_adelanto=None,
               metodo_pago=None):
    """POST /api/v1/pedido/convertir/{id}. Registra el pedido en el cleaner si se creó."""
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
    """Factura auto-generada de un pedido (GET /venta/ + fallback a BD) registrada en el cleaner."""
    venta_id = None
    r = client.get("/api/v1/venta/", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET /venta/ → {r.status_code}: {r.text}"
    for v in r.json():
        if v["pedido_id"] == pedido_id:
            venta_id = v["id"]
            break
    if venta_id is None:  # fallback: la lista del API está paginada
        row = db.execute(text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}).fetchone()
        venta_id = int(row[0]) if row else None
    if venta_id is None:
        return None
    cleaner.registrar("venta", venta_id)
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    assert det.status_code == 200, f"GET /venta/{venta_id} → {det.status_code}: {det.text}"
    body = det.json()
    for p in body.get("pagos", []):
        cleaner.registrar("pago", p["id"])
    return body


def _sin_acentos(texto: str) -> str:
    """Normaliza el texto (quita tildes) para comparar mensajes sin depender de acentos."""
    normalizado = unicodedata.normalize("NFD", texto)
    return re.sub(r"[\u0300-\u036f]", "", normalizado)


def _contar_pedidos(client):
    r = client.get("/api/v1/pedido/", params={"solo_mes_actual": "false"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET /pedido/ → {r.status_code}: {r.text}"
    return len(r.json())


def _sin_pedido_ni_pago(db, cotizacion_id):
    """True si no existe pedido ni pago vinculados a una cotización (conversión fallida)."""
    n_pedido = db.execute(
        text("SELECT COUNT(*) FROM pedido WHERE cotizacion_id = :c"), {"c": cotizacion_id}
    ).scalar()
    n_pago = db.execute(
        text(
            """SELECT COUNT(*) FROM pago p
               JOIN venta v ON v.id = p.venta_id
               JOIN pedido o ON o.id = v.pedido_id
               WHERE o.cotizacion_id = :c"""
        ),
        {"c": cotizacion_id},
    ).scalar()
    return n_pedido == 0 and n_pago == 0


# ---------------------------------------------------------------------------
# 1) Conversión sin abono
# ---------------------------------------------------------------------------
def test_convertir_sin_abono(client, cleaner, db):
    """Cotización COP → pedido sin adelanto: factura PENDIENTE, total = cant*precio, 0 pagos."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000)
    assert r.status_code == 201, f"Conversión sin abono → {r.status_code}: {r.text}"

    pedido = r.json()
    assert pedido["cotizacion_id"] == cot["id"], "El pedido debe apuntar a la cotización origen"

    venta = _buscar_venta(client, cleaner, db, pedido["id"])
    assert venta is not None, "La conversión debe auto-generar la factura (venta)"
    assert venta["estado"] == "PENDIENTE", f"Sin abono la factura debe quedar PENDIENTE, estado={venta['estado']}"
    assert venta["total"] == pytest.approx(100000.0, abs=0.01), f"total={venta['total']} debe ser 100000"
    assert venta["total_pagado"] == 0.0, f"Sin abono total_pagado debe ser 0, fue {venta['total_pagado']}"
    assert venta["saldo_pendiente"] == pytest.approx(100000.0, abs=0.01), \
        f"saldo_pendiente={venta['saldo_pendiente']} debe ser el total (100000)"


# ---------------------------------------------------------------------------
# 2) Abono en la misma moneda (COP)
# ---------------------------------------------------------------------------
def test_abono_misma_moneda(client, cleaner, db):
    """Adelanto COP 40000 sobre factura COP 100000 → ABONADA, saldo 60000."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000,
                   adelanto=40000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    assert r.status_code == 201, f"Conversión con abono COP → {r.status_code}: {r.text}"

    venta = _buscar_venta(client, cleaner, db, r.json()["id"])
    assert venta is not None, "Debe existir la factura con el abono"
    assert venta["estado"] == "ABONADA", f"Con abono parcial el estado debe ser ABONADA, fue {venta['estado']}"
    assert venta["total_pagado"] == pytest.approx(40000.0, abs=0.01), \
        f"total_pagado={venta['total_pagado']} debe ser 40000"
    assert venta["saldo_pendiente"] == pytest.approx(60000.0, abs=0.01), \
        f"saldo_pendiente={venta['saldo_pendiente']} debe ser 60000"
    assert len(venta["pagos"]) == 1, "Debe registrarse exactamente un pago (el adelanto)"


# ---------------------------------------------------------------------------
# 3) Abono total → factura pagada
# ---------------------------------------------------------------------------
def test_abono_total_paga_venta(client, cleaner, db):
    """Adelanto igual al total (100000 COP) → factura PAGADA, saldo 0."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000,
                   adelanto=100000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    assert r.status_code == 201, f"Conversión con abono total → {r.status_code}: {r.text}"

    venta = _buscar_venta(client, cleaner, db, r.json()["id"])
    assert venta is not None, "Debe existir la factura"
    assert venta["estado"] == "PAGADA", f"Abono total debe dejar la factura PAGADA, fue {venta['estado']}"
    assert venta["total_pagado"] == pytest.approx(100000.0, abs=0.01)
    assert venta["saldo_pendiente"] == pytest.approx(0.0, abs=0.01), \
        f"Factura pagada debe tener saldo 0, fue {venta['saldo_pendiente']}"


# ---------------------------------------------------------------------------
# 4) Factura USD con tasa congelada de la cotización
# ---------------------------------------------------------------------------
def test_factura_usd_usa_tasa_congelada(client, cleaner, db):
    """Cotización USD 500 @ tasa 3900: la factura congela moneda USD y tasa 3900 (no la vigente)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=500, moneda_id=2, tasa_cambio=3900)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=500)
    assert r.status_code == 201, f"Conversión USD → {r.status_code}: {r.text}"

    venta = _buscar_venta(client, cleaner, db, r.json()["id"])
    assert venta is not None, "Debe existir la factura en USD"
    assert venta["moneda_id"] == 2, f"La factura debe quedar en USD (moneda_id=2), fue {venta['moneda_id']}"
    assert venta["tasa_cambio"] == pytest.approx(3900.0, abs=1e-6), \
        f"La factura debe congelar la tasa de la cotización (3900), fue {venta['tasa_cambio']}"
    assert venta["total"] == pytest.approx(500.0, abs=0.01)


# ---------------------------------------------------------------------------
# 5) Abono USD en factura USD (tasa 1:1)
# ---------------------------------------------------------------------------
def test_abono_usd_en_factura_usd(client, cleaner, db):
    """Adelanto 200 USD sobre factura USD 500 @3900 → ABONADA, pagado 200, saldo 300."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=500, moneda_id=2, tasa_cambio=3900)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=500,
                   adelanto=200, moneda_adelanto_id=2, metodo_pago="EFECTIVO_USD")
    assert r.status_code == 201, f"Conversión con abono USD → {r.status_code}: {r.text}"

    venta = _buscar_venta(client, cleaner, db, r.json()["id"])
    assert venta is not None, "Debe existir la factura en USD"
    assert venta["estado"] == "ABONADA", f"Abono parcial en USD debe dejar ABONADA, fue {venta['estado']}"
    assert venta["total_pagado"] == pytest.approx(200.0, abs=0.01), \
        f"Misma moneda = tasa 1:1 → pagado 200, fue {venta['total_pagado']}"
    assert venta["saldo_pendiente"] == pytest.approx(300.0, abs=0.01), \
        f"saldo_pendiente={venta['saldo_pendiente']} debe ser 300"


# ---------------------------------------------------------------------------
# 6) Abono COP en factura USD (tasa derivada 1/3900)
# ---------------------------------------------------------------------------
def test_abono_cop_en_factura_usd(client, cleaner, db):
    """Adelanto 780000 COP (BANCOLOMBIA) en factura USD 500 @3900 → pagado ≈ 200 (780000/3900)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=500, moneda_id=2, tasa_cambio=3900)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=500,
                   adelanto=780000, moneda_adelanto_id=1, metodo_pago="BANCOLOMBIA")
    assert r.status_code == 201, f"Conversión con abono COP en factura USD → {r.status_code}: {r.text}"

    venta = _buscar_venta(client, cleaner, db, r.json()["id"])
    assert venta is not None, "Debe existir la factura en USD"
    assert venta["estado"] == "ABONADA", f"Con abono parcial debe quedar ABONADA, fue {venta['estado']}"
    # tasa derivada 1/3900 (guardada con redondeo a 6 decimales)
    pago = venta["pagos"][0]
    assert pago["tasa_cambio"] == pytest.approx(0.0002564, abs=1e-6), \
        f"Tasa del pago COP→USD debe ser ≈ 1/3900, fue {pago['tasa_cambio']}"
    assert venta["total_pagado"] == pytest.approx(200.0, abs=0.01), \
        f"780000 COP a 1/3900 = 200 USD, total_pagado={venta['total_pagado']}"
    assert venta["saldo_pendiente"] == pytest.approx(300.0, abs=0.01), \
        f"saldo_pendiente={venta['saldo_pendiente']} debe ser ≈ 300"


# ---------------------------------------------------------------------------
# 7) Abono VES sin TRM → rechazado sin dejar pedido
# ---------------------------------------------------------------------------
def test_abono_ves_requiere_trm(client, cleaner, db):
    """Adelanto VES sin tasa_cambio_adelanto → 400 con mensaje TRM/tasa y SIN pedido ni factura."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=500, moneda_id=2, tasa_cambio=3900)

    pedidos_antes = _contar_pedidos(client)
    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=500,
                   adelanto=1000, moneda_adelanto_id=3, metodo_pago="EFECTIVO_VES")  # VES sin TRM
    assert r.status_code == 400, f"Abono VES sin TRM debe ser 400, fue {r.status_code}: {r.text}"

    msg = _sin_acentos(r.json().get("detail", "") if r.status_code == 400 else "").lower()
    assert ("trm" in msg) or ("tasa" in msg), \
        f"El mensaje debe mencionar TRM/tasa, fue: {r.text}"

    pedidos_despues = _contar_pedidos(client)
    assert pedidos_despues == pedidos_antes, \
        f"La conversión rechazada no debe crear pedidos: antes={pedidos_antes} después={pedidos_despues}"
    assert _sin_pedido_ni_pago(db, cot["id"]), "No debe existir pedido ni pago de la cotización rechazada"


# ---------------------------------------------------------------------------
# 8) Abono VES con TRM explícita
# ---------------------------------------------------------------------------
def test_abono_ves_con_trm(client, cleaner, db):
    """Adelanto 1000 VES @ tasa 10 (1 VES = 10 COP) en factura USD 500@3900:
       el equivalente en la moneda de la factura SIEMPRE es entero:
       10000 COP base = 2.5641 USD → baja a 2 USD (regla del taller, < 0.9)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=500, moneda_id=2, tasa_cambio=3900)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=500,
                   adelanto=1000, moneda_adelanto_id=3, tasa_cambio_adelanto=10,
                   metodo_pago="EFECTIVO_VES")
    assert r.status_code == 201, f"Abono VES con TRM debe ser 201, fue {r.status_code}: {r.text}"

    venta = _buscar_venta(client, cleaner, db, r.json()["id"])
    assert venta is not None, "Debe existir la factura en USD"
    assert venta["estado"] == "ABONADA", f"Con abono parcial debe quedar ABONADA, fue {venta['estado']}"
    assert venta["total_pagado"] == 2.0, \
        f"1000 VES*10 = 10000 COP base = 2.5641 USD → entero 2; total_pagado={venta['total_pagado']}"
    assert venta["saldo_pendiente"] == pytest.approx(500 - 2, abs=0.01), \
        f"saldo_pendiente={venta['saldo_pendiente']}"


# ---------------------------------------------------------------------------
# 9) Idempotencia: la misma cotización no se convierte dos veces
# ---------------------------------------------------------------------------
def test_convertir_duplicado_rechazado(client, cleaner, db):
    """Convertir la misma cotización dos veces: la 1ª 201, la 2ª DEBE ser 4xx 'ya fue convertida'."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r1 = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000)
    assert r1.status_code == 201, f"Primera conversión → {r1.status_code}: {r1.text}"

    r2 = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000)
    assert r2.status_code in (400, 409), \
        f"La segunda conversión debe ser 4xx (400/409), fue {r2.status_code}: {r2.text}"
    detail = (r2.json().get("detail", "") if r2.status_code in (400, 409) else "").lower()
    assert "ya fue convertida" in detail, \
        f"El mensaje debe indicar que la cotización ya fue convertida, fue: {r2.text}"

    ventas = client.get("/api/v1/venta/", headers=ADMIN_HEADERS).json()
    assert sum(1 for v in ventas if v["pedido_id"] == r1.json()["id"]) == 1, \
        "La conversión duplicada no debe crear una segunda factura"

    # Registrar la factura auto-generada para que la limpieza no falle por FK.
    for v in ventas:
        if v["pedido_id"] == r1.json()["id"]:
            cleaner.registrar("venta", v["id"])
            for d in client.get(f"/api/v1/venta/{v['id']}", headers=ADMIN_HEADERS).json().get("detalles", []):
                cleaner.registrar("detalle_venta", d["id"])
            break


# ---------------------------------------------------------------------------
# 10) Producto inexistente en la conversión
# ---------------------------------------------------------------------------
def test_convertir_con_producto_inexistente(client, cleaner, db):
    """producto_id=99999999 → se espera un 4xx claro (400/404). Registra el resultado actual."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={
            "detalles": [{"producto_id": 99999999, "cantidad": 1, "precio": 100000,
                          "costo_unitario": 1000, "porcentaje_ganancia": 40}],
        },
        headers=ADMIN_HEADERS,
    )
    # Resultado actual (reportado): puede ser 409 "ya fue convertida" = sospechoso.
    assert r.status_code in (400, 404), (
        f"Se esperaba un 4xx claro (400/404) por producto inexistente; "
        f"se obtuvo {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# 11) Eliminar factura con pagos
# ---------------------------------------------------------------------------
def test_eliminar_venta_con_pagos(client, cleaner, db):
    """DELETE de una factura con pagos debe ser 2xx o 4xx limpio, NUNCA 500."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000,
                   adelanto=40000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    assert r.status_code == 201, f"Conversión → {r.status_code}: {r.text}"
    venta = _buscar_venta(client, cleaner, db, r.json()["id"])
    assert venta is not None and venta["pagos"], "La factura debe tener pagos para este test"

    try:
        dr = client.delete(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS)
        status_real = dr.status_code
        cuerpo = dr.text
    except Exception as e:  # noqa: BLE001 — TestClient propaga excepciones no capturadas (≈500)
        pytest.fail(
            f"DELETE /venta/{venta['id']} con pagos lanzó excepción sin capturar "
            f"(equivalente a un 500 en producción): {type(e).__name__}: {e!r}"
        )

    assert 200 <= status_real < 300 or 400 <= status_real < 500, (
        f"Eliminar una factura con pagos debe ser 2xx o 4xx limpio; "
        f"status real obtenido: {status_real} — cuerpo: {cuerpo}"
    )


# ---------------------------------------------------------------------------
# 12) Pago sobre factura ya pagada
# ---------------------------------------------------------------------------
def test_pago_venta_pagada_rechazado(client, cleaner, db):
    """Factura PAGADA: un pago adicional → 400 y no registra nada extra."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000,
                   adelanto=100000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    assert r.status_code == 201, f"Conversión → {r.status_code}: {r.text}"
    venta = _buscar_venta(client, cleaner, db, r.json()["id"])
    assert venta["estado"] == "PAGADA", f"Precondición: factura PAGADA, fue {venta['estado']}"

    rpago, cuerpo = crear_pago(client, cleaner, venta["id"], 1, 500.0, metodo_pago="EFECTIVO_COP")
    assert rpago.status_code == 400, f"Pago sobre factura pagada debe ser 400, fue {rpago.status_code}: {cuerpo}"
    detail = rpago.json().get("detail", "").lower()
    assert "pagada" in detail or "totalmente" in detail, \
        f"El mensaje debe explicar que la venta ya está pagada, fue: {rpago.text}"

    venta2 = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert venta2["estado"] == "PAGADA", "La factura debe seguir PAGADA tras el pago rechazado"
    assert len(venta2["pagos"]) == 1, "No debe registrarse ningún pago adicional"
    assert venta2["total_pagado"] == pytest.approx(100000.0, abs=0.01)


# ---------------------------------------------------------------------------
# 13) Consistencia de cuentas por cobrar
# ---------------------------------------------------------------------------
def test_cuentas_por_cobrar_consistente(client, cleaner, db):
    """Cuentas por cobrar: total_pagado + saldo_pendiente == total y moneda coherente."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000,
                   adelanto=40000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    assert r.status_code == 201, f"Conversión → {r.status_code}: {r.text}"
    venta = _buscar_venta(client, cleaner, db, r.json()["id"])
    assert venta["estado"] == "ABONADA", f"Precondición: factura ABONADA, fue {venta['estado']}"

    rcc = client.get("/api/v1/venta/cuentas-por-cobrar/", headers=ADMIN_HEADERS)
    assert rcc.status_code == 200, f"GET cuentas-por-cobrar → {rcc.status_code}: {rcc.text}"

    filas = [f for f in rcc.json() if f["venta_id"] == venta["id"]]
    assert filas, "La factura ABONADA debe aparecer en cuentas por cobrar"
    fila = filas[0]
    assert fila["total_pagado"] + fila["saldo_pendiente"] == pytest.approx(fila["total"], abs=0.01), \
        f"Inconsistencia: pagado({fila['total_pagado']}) + saldo({fila['saldo_pendiente']}) != total({fila['total']})"
    assert fila["saldo_pendiente"] > 0, "Debe quedar saldo pendiente"
    assert fila["moneda_codigo"] == "COP", \
        f"Venta COP debe reportar moneda_codigo 'COP', fue {fila['moneda_codigo']}"


# ---------------------------------------------------------------------------
# 14) Sobrepago rechazado sin dejar rastro
# ---------------------------------------------------------------------------
def test_sobrepago_rechazado(client, cleaner, db):
    """Adelanto 100001 sobre factura COP 100000 → 400 (excede saldo) y SIN pago registrado."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    pedidos_antes = _contar_pedidos(client)
    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000,
                   adelanto=100001, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    assert r.status_code == 400, f"El sobrepago debe ser 400, fue {r.status_code}: {r.text}"
    detail = (r.json().get("detail", "") if r.status_code == 400 else "").lower()
    assert "excede" in detail, f"El mensaje debe indicar que excede el saldo, fue: {r.text}"

    pedidos_despues = _contar_pedidos(client)
    assert pedidos_despues == pedidos_antes, \
        f"El sobrepago rechazado no debe crear pedidos: antes={pedidos_antes} después={pedidos_despues}"
    assert _sin_pedido_ni_pago(db, cot["id"]), \
        "No debe existir pedido ni pago de la conversión con sobrepago"


# ---------------------------------------------------------------------------
# 15) Adelanto sin método de pago
# ---------------------------------------------------------------------------
def test_abono_metodo_obligatorio(client, cleaner, db):
    """Adelanto sin metodo_pago → 400 y sin pedido creado."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    pedidos_antes = _contar_pedidos(client)
    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=100000,
                   adelanto=40000, moneda_adelanto_id=1)  # sin metodo_pago
    assert r.status_code == 400, f"Adelanto sin método de pago debe ser 400, fue {r.status_code}: {r.text}"
    detail = _sin_acentos(r.json().get("detail", "") if r.status_code == 400 else "").lower()
    assert "metodo de pago" in detail, f"El mensaje debe exigir el método de pago, fue: {r.text}"

    pedidos_despues = _contar_pedidos(client)
    assert pedidos_despues == pedidos_antes, \
        f"La conversión rechazada no debe crear pedidos: antes={pedidos_antes} después={pedidos_despues}"
    assert _sin_pedido_ni_pago(db, cot["id"]), "No debe existir pedido ni pago"


# ---------------------------------------------------------------------------
# 16) Cobro USD genera movimiento de caja automático
# ---------------------------------------------------------------------------
def _movimiento_de_pago(db, pedido_id):
    """Movimiento de caja vinculado a un pago de un pedido (via venta)."""
    return db.execute(
        text(
            """SELECT mc.tipo, mc.monto, mc.moneda_id, mc.tasa_cambio,
                      mc.monto_en_moneda_base, mca.codigo AS cuenta
               FROM movimiento_caja mc
               JOIN metodo_caja mca ON mca.id = mc.metodo_caja_id
               JOIN pago p ON p.id = mc.pago_id
               JOIN venta v ON v.id = p.venta_id
               WHERE v.pedido_id = :pedido
            """
        ),
        {"pedido": pedido_id},
    ).fetchall()


def test_abono_usd_genera_movimiento_caja(client, cleaner, db):
    """Adelanto EFECTIVO_USD en factura USD → movimiento ENTRADA en la cuenta
    EFECTIVO_USD, moneda del pago (USD) y tasa COP = TRM de la venta (3900)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=500, moneda_id=2, tasa_cambio=3900)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=500,
                   adelanto=200, moneda_adelanto_id=2, metodo_pago="EFECTIVO_USD")
    assert r.status_code == 201, f"Conversión con abono USD → {r.status_code}: {r.text}"
    _buscar_venta(client, cleaner, db, r.json()["id"])  # registra venta/pagos para la limpieza

    filas = _movimiento_de_pago(db, r.json()["id"])
    assert filas, "El cobro debe generar un movimiento de caja automático"
    fila = filas[0]
    assert fila.cuenta == "EFECTIVO_USD", f"Cuenta debe ser EFECTIVO_USD, fue {fila.cuenta}"
    assert fila.tipo == "ENTRADA"
    assert fila.monto == pytest.approx(200.0, abs=0.01)
    assert fila.moneda_id == 2, "El movimiento debe quedar en USD (moneda del pago)"
    assert fila.tasa_cambio == pytest.approx(3900.0, abs=1e-6), \
        f"Tasa COP por USD debe ser la TRM de la venta (3900), fue {fila.tasa_cambio}"
    assert fila.monto_en_moneda_base == pytest.approx(200 * 3900, abs=0.01), \
        f"Equivalente COP = 200 × 3900, fue {fila.monto_en_moneda_base}"


# ---------------------------------------------------------------------------
# 17) Cobro COP en factura USD → movimiento en COP con tasa 1.0
# ---------------------------------------------------------------------------
def test_abono_cop_genera_movimiento_caja(client, cleaner, db):
    """Adelanto 780000 COP (BANCOLOMBIA) en factura USD 500@3900 → movimiento en la
    cuenta BANCOLOMBIA con moneda COP y tasa COP = 1.0 (1/3900 × 3900)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=500, moneda_id=2, tasa_cambio=3900)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=500,
                   adelanto=780000, moneda_adelanto_id=1, metodo_pago="BANCOLOMBIA")
    assert r.status_code == 201, f"Conversión con abono COP → {r.status_code}: {r.text}"
    _buscar_venta(client, cleaner, db, r.json()["id"])  # registra venta/pagos para la limpieza

    filas = _movimiento_de_pago(db, r.json()["id"])
    assert filas, "El cobro debe generar un movimiento de caja automático"
    fila = filas[0]
    assert fila.cuenta == "BANCOLOMBIA", f"Cuenta debe ser BANCOLOMBIA, fue {fila.cuenta}"
    assert fila.tipo == "ENTRADA"
    assert fila.monto == pytest.approx(780000.0, abs=0.01)
    assert fila.moneda_id == 1, "El movimiento debe quedar en COP (moneda del pago)"
    assert fila.tasa_cambio == pytest.approx(1.0, abs=1e-6), \
        f"Tasa COP por COP debe ser 1.0, fue {fila.tasa_cambio}"
    assert fila.monto_en_moneda_base == pytest.approx(780000.0, abs=0.01)


# ---------------------------------------------------------------------------
# 18) El cobro se refleja en el resumen de cuentas
# ---------------------------------------------------------------------------
def test_resumen_cuentas_refleja_cobro(client, cleaner, db):
    """Tras un cobro EFECTIVO_USD, el resumen /cuenta/resumen muestra la cuenta
    EFECTIVO_USD con saldo en USD mayor a cero."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"],
                           precio=500, moneda_id=2, tasa_cambio=3900)

    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=500,
                   adelanto=200, moneda_adelanto_id=2, metodo_pago="EFECTIVO_USD")
    assert r.status_code == 201, f"Conversión → {r.status_code}: {r.text}"
    _buscar_venta(client, cleaner, db, r.json()["id"])  # registra venta/pagos para la limpieza

    rr = client.get("/api/v1/cuenta/resumen", headers=ADMIN_HEADERS)
    assert rr.status_code == 200, f"GET /cuenta/resumen → {rr.status_code}: {rr.text}"
    resumen = rr.json()
    cuenta = next((x for x in resumen if x["metodo_caja"]["codigo"] == "EFECTIVO_USD"), None)
    assert cuenta, "La cuenta EFECTIVO_USD debe aparecer en el resumen de cuentas"
    linea_usd = next((l for l in cuenta["saldo_por_moneda"] if l["moneda_id"] == 2), None)
    assert linea_usd, "Debe existir saldo en USD para EFECTIVO_USD"
    assert float(linea_usd["monto"]) >= 200.0, \
        f"El saldo en USD debe reflejar el cobro (>=200), fue {linea_usd['monto']}"


# ---------------------------------------------------------------------------
# 19) Cotización USD exige precios convertidos (defensa contra el bug de moneda)
# ---------------------------------------------------------------------------
def test_cotizacion_usd_rechaza_precios_sin_convertir(client, cleaner):
    """Cotización USD cuyo precio de detalle no está convertido (precio COP como
    USD) → 400 con mensaje claro, sin crear la cotización."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)

    payload = {
        "cliente_id": cliente["id"],
        "fecha": "2026-08-06",
        "estado": "BORRADOR",
        "total_estimado": 928.0,
        "moneda_id": 2,
        "tasa_cambio": 3200.0,
        "observaciones": "test validacion moneda",
        "detalles": [{"producto_id": producto["id"], "cantidad": 1, "precio": 2968462.0}],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"Precio sin convertir debe ser 400, fue {r.status_code}: {r.text}"
    msg = _sin_acentos(r.json().get("detail", "")).lower()
    assert "no coincide con el total" in msg, f"El mensaje debe explicar la inconsistencia, fue: {r.text}"

    # Con precios convertidos (consistente) → 201
    payload_ok = {**payload, "detalles": [{"producto_id": producto["id"], "cantidad": 1, "precio": 928.0}],
                  "observaciones": "test validacion ok"}
    r_ok = client.post("/api/v1/cotizacion/", json=payload_ok, headers=ADMIN_HEADERS)
    assert r_ok.status_code == 201, f"Precio convertido debe ser 201, fue {r_ok.status_code}: {r_ok.text}"
    cleaner.registrar("cotizacion", r_ok.json()["id"])
    for d in r_ok.json().get("detalles", []):
        cleaner.registrar("detalle_cotizacion", d["id"])
