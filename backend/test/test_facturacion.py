"""
test_facturacion.py — Módulo de facturación (aislado de ventas y cobros).

La factura se emite normalmente para pedidos pagados al 100% (su venta está
PAGADA), con el monto en USD que la dueña decide por cada LÍNEA del pedido y
una tasa USD → Bs. Los impuestos (IVA 16%, IGTF 3%) vienen de la tabla
`tasa_impuesto` (configurables).

Fase B: un pedido con saldo pendiente SÍ aparece como facturable y el
Dueño/Administrador puede autorizar la emisión caso a caso marcando
`permitir_saldo_pendiente` (se registra en observaciones y auditoría). Sin esa
autorización se mantiene la regla estricta del 100%, y un usuario no
administrador recibe 403.

Cada línea se identifica por `detalle_pedido.id` (no por producto): un pedido
puede tener varias líneas del mismo producto y se facturan de forma independiente.

Cubre: pedido no pagado → facturable con saldo, 400 sin autorización, 403 si el
emisor no es admin, 201 si el Dueño/Administrador autoriza; pedido pagado →
factura con totales correctos; una sola factura por pedido; anulación; tasas
configurables; regresión de mismo producto en varias líneas del pedido.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_facturacion.py -v
"""
import pytest
from datetime import date

from conftest import (
    ADMIN_HEADERS,
    VENTAS_HEADERS,
    _uniq,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_movimiento,
    crear_producto,
    registrar_inventario_de_material,
    registrar_venta_de_pedido,
)
from app.modules.auditoria.model import AuditEvent


# ---------------------------------------------------------------------------
# Helpers locales
# ---------------------------------------------------------------------------
def _convertir(client, cleaner, id_cotizacion, producto_id, precio, *,
               cantidad=1, n_lineas=1, adelanto=None, headers=ADMIN_HEADERS):
    """Cotización → pedido. n_lineas>1 repite el mismo producto en varias líneas
    (para probar el caso "mismo producto como varios productos")."""
    base_detalle = {
        "producto_id": producto_id,
        "cantidad": cantidad,
        "precio": precio,
        "costo_unitario": 1000,
        "porcentaje_ganancia": 40,
    }
    r = client.post(
        f"/api/v1/pedido/convertir/{id_cotizacion}",
        json={
            "detalles": [dict(base_detalle) for _ in range(n_lineas)],
            "adelanto": adelanto,
            "moneda_adelanto_id": 1 if adelanto else None,
            "metodo_pago": "EFECTIVO_COP" if adelanto else None,
        },
        headers=headers,
    )
    assert r.status_code == 201, f"Conversión → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    return pedido


def _convertir_pagado(client, cleaner, id_cotizacion, producto_id, precio, **kw):
    """Cotización → pedido con adelanto total (venta queda PAGADA)."""
    n = kw.pop("n_lineas", 1)
    total = precio * n
    return _convertir(client, cleaner, id_cotizacion, producto_id, precio,
                      n_lineas=n, adelanto=total, **kw)


def _convertir_sin_abono(client, cleaner, id_cotizacion, producto_id, precio, **kw):
    return _convertir(client, cleaner, id_cotizacion, producto_id, precio, **kw)


def _lineas_facturables(client, pedido_id):
    """Devuelve las líneas facturables del pedido (con detalle_pedido_id)."""
    facturables = client.get("/api/v1/factura/pedidos-facturables/", headers=ADMIN_HEADERS).json()
    for p in facturables:
        if p["pedido_id"] == pedido_id:
            return p["lineas"]
    return []


def _detalle_ids_via_pedido(client, pedido_id):
    """Fallback para un pedido no facturable (no pago): obtiene los ids de
    sus líneas desde el detalle del pedido."""
    r = client.get(f"/api/v1/pedido/{pedido_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET /pedido/{pedido_id} → {r.status_code}: {r.text}"
    return [d["id"] for d in r.json().get("detalles", [])]


def _emitir(client, cleaner, pedido_id, lineas, tasa_usd_ves=50.0,
            permitir=False, headers=ADMIN_HEADERS):
    """lineas: [{detalle_pedido_id, precio_usd}]. Registra la factura en el cleaner.
    `permitir` envía `permitir_saldo_pendiente=True` (autorización del admin)."""
    payload = {"pedido_id": pedido_id, "tasa_usd_ves": tasa_usd_ves, "lineas": lineas}
    if permitir:
        payload["permitir_saldo_pendiente"] = True
    r = client.post(
        "/api/v1/factura/",
        json=payload,
        headers=headers,
    )
    body = r.json() if r.status_code in (200, 201) else r.text
    if r.status_code in (200, 201):
        cleaner.registrar("factura", body["id"])
        det = client.get(f"/api/v1/factura/{body['id']}", headers=ADMIN_HEADERS)
        if det.status_code == 200:
            for d in det.json().get("detalles", []):
                cleaner.registrar("detalle_factura", d["id"])
    return r, body


def _pedidos_facturables(client):
    r = client.get("/api/v1/factura/pedidos-facturables/", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET pedidos-facturables → {r.status_code}: {r.text}"
    return r.json()


# ---------------------------------------------------------------------------
# 1) Pedido con saldo pendiente → facturable, pero requiere autorización admin
# ---------------------------------------------------------------------------
def test_pedido_pendiente_facturable_con_autorizacion_admin(client, db, cleaner):
    """Venta PENDIENTE aparece como facturable con saldo; emitir sin autorización
    falla con 400 (regla del 100%), y como Dueño/Administrador con
    `permitir_saldo_pendiente` emite dejando constancia en observaciones y auditoría."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    pedido = _convertir_sin_abono(client, cleaner, cot["id"], producto["id"], 100000)

    fila = next((p for p in _pedidos_facturables(client) if p["pedido_id"] == pedido["id"]), None)
    assert fila is not None, "Un pedido sin cobrar al 100% debe aparecer como facturable"
    assert fila["saldo_pendiente"] == pytest.approx(100000.0, abs=0.01)
    assert fila["total_pagado"] == pytest.approx(0.0, abs=0.01)
    assert fila["venta_estado"] == "PENDIENTE"

    # Sin autorización → se mantiene la regla estricta del 100% (400).
    det_ids = _detalle_ids_via_pedido(client, pedido["id"])
    r, _ = _emitir(client, cleaner, pedido["id"],
                   [{"detalle_pedido_id": det_ids[0], "precio_usd": 100}])
    assert r.status_code == 400, f"Facturar saldo sin autorizar → {r.status_code}: {r.text}"
    assert "100%" in str(r.text), f"El error debe mencionar el pago al 100%, fue: {r.text}"

    # Con autorización de admin → emite y registra la decisión (observaciones + auditoría).
    lineas_ped = _lineas_facturables(client, pedido["id"])
    ra, factura = _emitir(client, cleaner, pedido["id"],
                          [{"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 100}],
                          permitir=True)
    assert ra.status_code == 201, f"Facturar saldo autorizado → {ra.status_code}: {ra.text}"
    assert "saldo pendiente" in (factura.get("observaciones") or "").lower()

    ev = db.query(AuditEvent).filter(
        AuditEvent.action == "FACTURAR_CON_SALDO_PENDIENTE",
        AuditEvent.entity_type == "factura",
        AuditEvent.entity_id == str(factura["id"]),
    ).first()
    assert ev is not None, "Debe quedar evento de auditoría al facturar con saldo pendiente"


def test_pedido_pendiente_no_admin_rechazado_403(client, cleaner):
    """Un usuario no administrador (Ventas) no puede facturar con saldo pendiente: 403."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000,
                           headers=VENTAS_HEADERS)
    pedido = _convertir(client, cleaner, cot["id"], producto["id"], 100000,
                        headers=VENTAS_HEADERS)

    # Ventas ve su pedido pendiente como facturable...
    r = client.get("/api/v1/factura/pedidos-facturables/", headers=VENTAS_HEADERS)
    assert r.status_code == 200, f"GET pedidos-facturables (Ventas) → {r.status_code}: {r.text}"
    fila = next((p for p in r.json() if p["pedido_id"] == pedido["id"]), None)
    assert fila is not None and fila["saldo_pendiente"] > 0.01

    # ...pero facturar con saldo pendiente exige Dueño/Administrador → 403.
    det_ids = _detalle_ids_via_pedido(client, pedido["id"])
    r403, _ = _emitir(client, cleaner, pedido["id"],
                      [{"detalle_pedido_id": det_ids[0], "precio_usd": 100}],
                      permitir=True, headers=VENTAS_HEADERS)
    assert r403.status_code == 403, f"Ventas facturando con saldo → {r403.status_code}: {r403.text}"
    assert "administrador" in str(r403.text).lower()


# ---------------------------------------------------------------------------
# 2) Pedido pagado al 100% → factura con impuestos correctos
# ---------------------------------------------------------------------------
def test_factura_pedido_pagado_100(client, cleaner):
    """Adelanto total → pedido facturable; factura en USD→Bs. con IVA 16% e IGTF 3%."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    pedido = _convertir_pagado(client, cleaner, cot["id"], producto["id"], 100000)

    facturables = _pedidos_facturables(client)
    ids = [p["pedido_id"] for p in facturables]
    assert pedido["id"] in ids, "El pedido pagado debe ser facturable"
    fila = next(p for p in facturables if p["pedido_id"] == pedido["id"])
    assert fila["total_pagado"] == pytest.approx(100000.0, abs=0.01)

    lineas_ped = _lineas_facturables(client, pedido["id"])
    assert len(lineas_ped) == 1
    assert "detalle_pedido_id" in lineas_ped[0]

    # 1 producto a 100 USD, tasa 50 → base 5000 Bs., IVA 16% = 800, IGTF 3% de (5800) = 174, total 5974.
    r, factura = _emitir(client, cleaner, pedido["id"],
                         [{"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 100}],
                         tasa_usd_ves=50)
    assert r.status_code == 201, f"Emitir factura → {r.status_code}: {r.text}"
    assert factura["estado"] == "EMITIDA"
    assert factura["total_usd"] == pytest.approx(100.0, abs=0.01)
    assert factura["tasa_usd_ves"] == pytest.approx(50.0, abs=0.01)
    assert factura["base_imponible_bs"] == pytest.approx(5000.0, abs=0.01)
    assert factura["iva_bs"] == pytest.approx(800.0, abs=0.01)
    assert factura["igtf_bs"] == pytest.approx(174.0, abs=0.01)
    assert factura["total_bs"] == pytest.approx(5974.0, abs=0.01)
    assert factura["cliente"]["id"] == cliente["id"]

    det = client.get(f"/api/v1/factura/{factura['id']}", headers=ADMIN_HEADERS)
    assert det.status_code == 200, f"GET factura → {det.status_code}: {det.text}"
    detalles = det.json()["detalles"]
    assert len(detalles) == 1
    assert detalles[0]["cantidad"] == pytest.approx(1.0)
    assert detalles[0]["precio_usd"] == pytest.approx(100.0)
    assert detalles[0]["subtotal_bs"] == pytest.approx(5000.0, abs=0.01)

    # Ya no debe aparecer como facturable.
    ids_tras = [p["pedido_id"] for p in _pedidos_facturables(client)]
    assert pedido["id"] not in ids_tras, "Un pedido ya facturado no debe seguir como facturable"


# ---------------------------------------------------------------------------
# 3) Una sola factura por pedido
# ---------------------------------------------------------------------------
def test_no_duplicar_factura(client, cleaner):
    """Emitir una segunda factura del mismo pedido falla con 400."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    pedido = _convertir_pagado(client, cleaner, cot["id"], producto["id"], 100000)
    lineas_ped = _lineas_facturables(client, pedido["id"])

    r1, _ = _emitir(client, cleaner, pedido["id"],
                    [{"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 100}])
    assert r1.status_code == 201, f"Primera factura → {r1.status_code}: {r1.text}"

    r2, body = _emitir(client, cleaner, pedido["id"],
                       [{"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 50}])
    assert r2.status_code == 400, f"Segunda factura → {r2.status_code}: {r2.text}"
    assert "ya tiene una factura" in str(body).lower()


# ---------------------------------------------------------------------------
# 4) Anulación
# ---------------------------------------------------------------------------
def test_anular_factura(client, cleaner):
    """Anular cambia el estado a ANULADA y libera el pedido para re-facturar."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    pedido = _convertir_pagado(client, cleaner, cot["id"], producto["id"], 100000)
    lineas_ped = _lineas_facturables(client, pedido["id"])
    r, factura = _emitir(client, cleaner, pedido["id"],
                         [{"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 100}],
                         tasa_usd_ves=50)
    assert r.status_code == 201

    ra = client.post(f"/api/v1/factura/{factura['id']}/anular", headers=ADMIN_HEADERS)
    assert ra.status_code == 200, f"Anular → {ra.status_code}: {ra.text}"
    assert ra.json()["estado"] == "ANULADA"

    ra2 = client.post(f"/api/v1/factura/{factura['id']}/anular", headers=ADMIN_HEADERS)
    assert ra2.status_code == 400, f"Re-anular → {ra2.status_code}: {ra2.text}"

    # La factura anulada queda en el historial...
    lista = client.get("/api/v1/factura/", headers=ADMIN_HEADERS).json()
    estados = [f["estado"] for f in lista if f["id"] == factura["id"]]
    assert estados == ["ANULADA"]

    # ...pero libera el pedido: reaparece como facturable para una corrección.
    ids = [p["pedido_id"] for p in _pedidos_facturables(client)]
    assert pedido["id"] in ids, "El pedido con factura ANULADA debe poder re-facturarse"


def test_reexpedir_factura_tras_anular(client, cleaner):
    """Tras anular, el pedido puede facturarse de nuevo (corrección) con otra factura EMITIDA."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    pedido = _convertir_pagado(client, cleaner, cot["id"], producto["id"], 100000)
    lineas_ped = _lineas_facturables(client, pedido["id"])

    r1, factura1 = _emitir(client, cleaner, pedido["id"],
                           [{"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 100}],
                           tasa_usd_ves=50)
    assert r1.status_code == 201

    ra = client.post(f"/api/v1/factura/{factura1['id']}/anular", headers=ADMIN_HEADERS)
    assert ra.status_code == 200

    # Corrección con nuevos montos.
    r2, factura2 = _emitir(client, cleaner, pedido["id"],
                           [{"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 120}],
                           tasa_usd_ves=60)
    assert r2.status_code == 201, f"Re-expedición → {r2.status_code}: {r2.text}"
    assert factura2["estado"] == "EMITIDA"
    assert factura2["total_usd"] == 120.0
    assert factura2["tasa_usd_ves"] == 60.0
    assert factura2["id"] != factura1["id"]

    # La corrección bloquea una nueva emisión mientras esté vigente.
    r3, _ = _emitir(client, cleaner, pedido["id"],
                    [{"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 10}])
    assert r3.status_code == 400
    assert "ya tiene una factura" in str(r3.text).lower()

    # El pedido ya no aparece como facturable (hay una EMITIDA vigente).
    ids = [p["pedido_id"] for p in _pedidos_facturables(client)]
    assert pedido["id"] not in ids


# ---------------------------------------------------------------------------
# 5) Tasas configurables
# ---------------------------------------------------------------------------
def test_tasas_impuesto_configurables(client, db, cleaner):
    """Cambiar la tasa IVA en la tabla afecta el cálculo de la próxima factura."""
    from sqlalchemy import text

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)
    pedido = _convertir_pagado(client, cleaner, cot["id"], producto["id"], 100000)
    lineas_ped = _lineas_facturables(client, pedido["id"])

    r = client.get("/api/v1/factura/tasas/", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    tasas = {t["clave"]: t["tasa"] for t in r.json()}
    assert tasas.get("IVA") == pytest.approx(16.0)
    assert tasas.get("IGTF") == pytest.approx(3.0)

    # Cambiar IVA a 10% solo para esta prueba (se restaura al final).
    db.execute(text("UPDATE tasa_impuesto SET tasa = 10.0 WHERE clave = 'IVA'"))
    db.commit()
    try:
        rr, factura = _emitir(client, cleaner, pedido["id"],
                              [{"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 100}],
                              tasa_usd_ves=50)
        assert rr.status_code == 201, f"Emitir con IVA 10% → {rr.status_code}: {rr.text}"
        # base 5000, IVA 10% = 500, total con IVA 5500, IGTF 3% = 165 → total 5665.
        assert factura["iva_bs"] == pytest.approx(500.0, abs=0.01)
        assert factura["igtf_bs"] == pytest.approx(165.0, abs=0.01)
        assert factura["total_bs"] == pytest.approx(5665.0, abs=0.01)
    finally:
        db.execute(text("UPDATE tasa_impuesto SET tasa = 16.0 WHERE clave = 'IVA'"))
        db.commit()


# ---------------------------------------------------------------------------
# 6) REGRESIÓN: mismo producto en varias líneas del pedido
# ---------------------------------------------------------------------------
def test_mismo_producto_en_varias_lineas(client, cleaner):
    """Un pedido con DOS líneas del mismo producto (no cantidad=2) se factura
    como dos líneas independientes, cada una con su monto en USD.

    Reproduce el bug reportado: "El producto #2 está repetido en las líneas."
    """
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=100000)

    # Pedido con 2 líneas del MISMO producto, adelanto total = 2 * 100000 = 200000 → PAGADA.
    pedido = _convertir_pagado(client, cleaner, cot["id"], producto["id"], 100000, n_lineas=2)

    facturables = _pedidos_facturables(client)
    assert pedido["id"] in [p["pedido_id"] for p in facturables]

    lineas_ped = _lineas_facturables(client, pedido["id"])
    assert len(lineas_ped) == 2, "Deben existir dos líneas facturables (una por detalle_pedido)"
    # detalle_pedido_id distintos aunque sea el mismo producto.
    assert lineas_ped[0]["detalle_pedido_id"] != lineas_ped[1]["detalle_pedido_id"]
    for l in lineas_ped:
        assert l["nombre"] == producto["nombre"], "Ambas líneas son el mismo producto"

    # Facturar las dos líneas a precios DISTINTOS (200 y 100 USD) → demuestra independencia.
    r, factura = _emitir(client, cleaner, pedido["id"], [
        {"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 200},
        {"detalle_pedido_id": lineas_ped[1]["detalle_pedido_id"], "precio_usd": 100},
    ], tasa_usd_ves=50)
    assert r.status_code == 201, f"Emitir con mismo producto en 2 líneas → {r.status_code}: {r.text}"

    # total_usd = 200 + 100 = 300; base = 300*50 = 15000; IVA 16% = 2400; +IVA = 17400;
    # IGTF 3% = 522; total = 17922.
    assert factura["total_usd"] == pytest.approx(300.0, abs=0.01)
    assert factura["base_imponible_bs"] == pytest.approx(15000.0, abs=0.01)
    assert factura["iva_bs"] == pytest.approx(2400.0, abs=0.01)
    assert factura["igtf_bs"] == pytest.approx(522.0, abs=0.01)
    assert factura["total_bs"] == pytest.approx(17922.0, abs=0.01)

    # Dos detalles independientes, cada uno con su cantidad/precio propios.
    det = client.get(f"/api/v1/factura/{factura['id']}", headers=ADMIN_HEADERS).json()
    assert len(det["detalles"]) == 2
    precios = sorted(float(d["precio_usd"]) for d in det["detalles"])
    assert precios == [pytest.approx(100.0), pytest.approx(200.0)]
    for d in det["detalles"]:
        assert d["cantidad"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 7) Pedido con INSUMO (material vendido suelto) → factura fiscal correcta
# ---------------------------------------------------------------------------
def test_factura_pedido_con_insumo(client, db, cleaner):
    """Cotización mixta (mueble FABRICADO + insumo INSUMO) → pedido → factura.

    La línea INSUMO se factura con material_id (producto_id NULL), tipo_item
    INSUMO y descripción = nombre del material. Al convertir se descuenta el
    stock del insumo (venta automática)."""
    from sqlalchemy import text

    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    material = crear_material(client, cleaner, costo_base=5000.0)
    # Stock del insumo: la venta automática de la conversión lo exige.
    _, mov = crear_movimiento(client, cleaner, material["id"], "ENTRADA", 10)

    precio_prod, precio_ins, cant_ins = 100000.0, 8000.0, 2
    # Cotización mixta: 1 mueble + 2 unidades del insumo suelto.
    payload = {
        "cliente_id": cliente["id"],
        "fecha": str(date.today()),
        "estado": "BORRADOR",
        "total_estimado": precio_prod + precio_ins * cant_ins,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": _uniq("cot_mixta"),
        "detalles": [
            {"producto_id": producto["id"], "tipo_item": "FABRICADO",
             "cantidad": 1, "precio": precio_prod, "ancho": 1.6, "largo": 1.9},
            {"producto_id": None, "material_id": material["id"], "tipo_item": "INSUMO",
             "cantidad": cant_ins, "precio": precio_ins},
        ],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"Cotización mixta → {r.status_code}: {r.text}"
    cot = r.json()
    cleaner.registrar("cotizacion", cot["id"])

    # Conversión copiando los renglones EXACTOS (tipo_item + material_id).
    rc = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [
            {"producto_id": producto["id"], "tipo_item": "FABRICADO",
             "cantidad": 1, "precio": precio_prod},
            {"producto_id": None, "material_id": material["id"], "tipo_item": "INSUMO",
             "cantidad": cant_ins, "precio": precio_ins},
        ],
        "adelanto": precio_prod + precio_ins * cant_ins,
        "moneda_adelanto_id": 1,
        "metodo_pago": "EFECTIVO_COP",
    }, headers=ADMIN_HEADERS)
    assert rc.status_code == 201, f"Conversión mixta → {rc.status_code}: {rc.text}"
    pedido = rc.json()
    cleaner.registrar("pedido", pedido["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])

    # La venta automática descontó el stock del insumo (10 - 2 = 8).
    row = db.execute(
        text("SELECT cantidad FROM inventario WHERE material_id = :m"),
        {"m": material["id"]},
    ).fetchone()
    assert row is not None
    assert float(row[0]) == pytest.approx(8.0)
    registrar_inventario_de_material(db, cleaner, material["id"])

    # Facturar las dos líneas.
    lineas_ped = _lineas_facturables(client, pedido["id"])
    assert len(lineas_ped) == 2, f"Deben facturarse 2 líneas (mueble + insumo): {lineas_ped}"
    r, factura = _emitir(client, cleaner, pedido["id"], [
        {"detalle_pedido_id": lineas_ped[0]["detalle_pedido_id"], "precio_usd": 100},
        {"detalle_pedido_id": lineas_ped[1]["detalle_pedido_id"], "precio_usd": 20},
    ], tasa_usd_ves=50)
    assert r.status_code == 201, f"Facturar mixto → {r.status_code}: {r.text}"

    det = client.get(f"/api/v1/factura/{factura['id']}", headers=ADMIN_HEADERS).json()
    assert len(det["detalles"]) == 2
    por_tipo = {d.get("tipo_item", "FABRICADO"): d for d in det["detalles"]}
    assert set(por_tipo) == {"FABRICADO", "INSUMO"}

    d_ins = por_tipo["INSUMO"]
    assert d_ins["material_id"] == material["id"]
    assert d_ins["producto_id"] is None
    assert d_ins["descripcion"] == material["nombre"]

    d_prod = por_tipo["FABRICADO"]
    assert d_prod["producto_id"] == producto["id"]
    assert d_prod["material_id"] is None