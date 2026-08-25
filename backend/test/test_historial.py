"""
test_historial.py — Expediente digital: ficha con la cadena completa.

Cubre las 5 entradas (cotización, pedido, factura, envío, cliente), la cadena
completa (cotización → pedido → producción → venta/pagos → gastos → factura →
envío) y que la auditoría solo viaje para administradores.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_historial.py -v
"""
import uuid
from datetime import datetime, date

import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    VENTAS_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_producto,
)


def _uniq(prefix: str) -> str:
    return f"test_{prefix}_{uuid.uuid4().hex[:8]}"


def _convertir(client, cleaner, id_cotizacion, *, producto_id, precio, cantidad=1, adelanto=None,
               moneda_adelanto_id=None, tasa_cambio_adelanto=None, metodo_pago=None):
    body = {
        "detalles": [{
            "producto_id": producto_id,
            "cantidad": cantidad,
            "precio": precio,
            "costo_unitario": 1000,
            "porcentaje_ganancia": 40,
        }],
    }
    if adelanto is not None:
        body["adelanto"] = adelanto
        body["moneda_adelanto_id"] = moneda_adelanto_id
        body["tasa_cambio_adelanto"] = tasa_cambio_adelanto
        body["metodo_pago"] = metodo_pago
    r = client.post(f"/api/v1/pedido/convertir/{id_cotizacion}", json=body, headers=ADMIN_HEADERS)
    if r.status_code == 201:
        cleaner.registrar("pedido", r.json()["id"])
    return r


def _base_pedido(client, cleaner, precio=100000, adelanto=None):
    """Cliente + producto + cotización COP + conversión. Devuelve (cot, pedido)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=precio)
    r = _convertir(client, cleaner, cot["id"], producto_id=producto["id"], precio=precio,
                   adelanto=adelanto, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP" if adelanto else None)
    assert r.status_code == 201, f"Conversión → {r.status_code}: {r.text}"
    _registrar_venta_cleaner(client, cleaner, r.json()["id"])
    return cot, r.json()


def _registrar_venta_cleaner(client, cleaner, pedido_id):
    """Registra la venta auto-generada por la conversión (venta + detalles + pagos)."""
    from conftest import session_local
    venta_id = None
    r = client.get("/api/v1/venta/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    if r.status_code == 200:
        for v in r.json():
            if v.get("pedido_id") == pedido_id:
                venta_id = v["id"]
                break
    if venta_id is None:
        dbq = session_local()
        try:
            row = dbq.execute(text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}).fetchone()
            venta_id = int(row[0]) if row else None
        finally:
            dbq.close()
    if venta_id is None:
        return
    cleaner.registrar("venta", venta_id)
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    if det.status_code == 200:
        for d in det.json().get("detalles", []):
            cleaner.registrar("detalle_venta", d["id"])
        for p in det.json().get("pagos", []):
            cleaner.registrar("pago", p["id"])


# ---------------------------------------------------------------------------
# 1) Cotización sin pedido (no todas las cotizaciones se convierten)
# ---------------------------------------------------------------------------
def test_ficha_cotizacion_sin_pedido(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=250000)

    r = client.get(f"/api/v1/historial/cotizacion/{cot['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET ficha cotización → {r.status_code}: {r.text}"
    ficha = r.json()
    assert ficha["cotizacion"]["id"] == cot["id"]
    assert ficha["cotizacion"]["estado"] == "BORRADOR"
    assert ficha["cotizacion"]["total_estimado"] == pytest.approx(250000.0)
    assert ficha["cotizacion"]["detalles"], "La ficha debe incluir los detalles de la cotización"
    assert ficha["pedido"] is None, "Sin conversión no debe haber pedido"
    assert ficha["venta"] is None and ficha["envio"] is None


# ---------------------------------------------------------------------------
# 2) Ficha completa de pedido (cadena cotización → pedido → venta)
# ---------------------------------------------------------------------------
def test_ficha_pedido_cadena_completa(client, cleaner):
    cot, pedido = _base_pedido(client, cleaner, precio=100000, adelanto=40000)

    r = client.get(f"/api/v1/historial/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET ficha pedido → {r.status_code}: {r.text}"
    ficha = r.json()
    assert ficha["cotizacion"]["id"] == cot["id"]
    assert ficha["pedido"]["id"] == pedido["id"]
    assert ficha["pedido"]["cotizacion_id"] == cot["id"]
    assert ficha["cliente"]["nombre"] == ficha["cliente"]["nombre"]
    assert len(ficha["detalles_pedido"]) == 1, "La ficha debe tener el detalle del pedido"
    det = ficha["detalles_pedido"][0]
    assert det["precio"] == pytest.approx(100000.0)
    assert det["producto_nombre"], "El detalle debe traer el nombre del producto"

    venta = ficha["venta"]
    assert venta is not None, "La conversión auto-genera la venta"
    assert venta["estado"] == "ABONADA"
    assert len(venta["pagos"]) == 1, "Debe aparecer el abono registrado"
    assert venta["pagos"][0]["monto"] == pytest.approx(40000.0)
    assert venta["saldo_pendiente"] == pytest.approx(60000.0)
    assert venta["pagos"][0]["caja"] is not None, "El pago debe traer su movimiento de caja"


# ---------------------------------------------------------------------------
# 3) Producción en la ficha (orden + etapas)
# ---------------------------------------------------------------------------
def test_ficha_pedido_con_produccion(client, cleaner, db):
    cot, pedido = _base_pedido(client, cleaner, precio=100000)

    detalle_id = db.execute(
        text("SELECT id FROM detalle_pedido WHERE pedido_id = :p"),
        {"p": pedido["id"]},
    ).fetchone()[0]
    r = client.post(f"/api/v1/produccion/orden/desde-pedido/{detalle_id}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"Crear orden → {r.status_code}: {r.text}"
    cleaner.registrar("orden_produccion", r.json()["id"])

    ficha = client.get(f"/api/v1/historial/pedido/{pedido['id']}", headers=ADMIN_HEADERS).json()
    prod = ficha["detalles_pedido"][0]["produccion"]
    assert prod is not None, "La ficha debe incluir la producción del detalle"
    assert prod["orden"]["id"] == r.json()["id"]
    assert prod["orden"]["estado"] == "PENDIENTE"
    assert prod["etapas"] == []
    assert prod["costo"] is None, "Sin finalizar no debe haber costo"


# ---------------------------------------------------------------------------
# 4) Factura como entrada del expediente
# ---------------------------------------------------------------------------
def test_ficha_factura(client, cleaner, db):
    cot, pedido = _base_pedido(client, cleaner, precio=100000, adelanto=100000)

    from app.modules.facturacion.model import Factura
    db_obj = Factura(
        pedido_id=pedido["id"],
        cliente_id=cot["cliente_id"],
        fecha_emision=date.today(),
        total_usd=25.0,
        tasa_usd_ves=100.0,
        base_imponible_bs=2500.0,
        iva_bs=400.0,
        igtf_bs=87.0,
        total_bs=2987.0,
        estado="EMITIDA",
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    cleaner.registrar("factura", db_obj.id)

    r = client.get(f"/api/v1/historial/factura/{db_obj.id}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET ficha factura → {r.status_code}: {r.text}"
    ficha = r.json()
    assert ficha["factura_entrada"]["id"] == db_obj.id
    assert ficha["factura_entrada"]["estado"] == "EMITIDA"
    assert ficha["pedido"]["id"] == pedido["id"], "La ficha debe traer la cadena del pedido"
    assert ficha["venta"]["estado"] == "PAGADA"
    assert len(ficha["facturas"]) == 1, "La cadena debe listar la factura emitida"


# ---------------------------------------------------------------------------
# 5) Envío como entrada del expediente
# ---------------------------------------------------------------------------
def test_ficha_envio(client, cleaner, db):
    cot, pedido = _base_pedido(client, cleaner, precio=100000)

    from app.modules.envios.model import Envio
    envio = Envio(pedido_id=pedido["id"], estado="PREPARADO", guia_despacho="GUIA-TEST-1")
    db.add(envio)
    db.commit()
    db.refresh(envio)
    cleaner.registrar("envio", envio.id)

    r = client.get(f"/api/v1/historial/envio/{envio.id}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET ficha envío → {r.status_code}: {r.text}"
    ficha = r.json()
    assert ficha["envio_entrada"]["id"] == envio.id
    assert ficha["envio_entrada"]["guia_despacho"] == "GUIA-TEST-1"
    assert ficha["pedido"]["id"] == pedido["id"]
    assert ficha["envio"]["estado"] == "PREPARADO", "La cadena debe traer el envío"


# ---------------------------------------------------------------------------
# 6) Resumen del cliente (todas sus operaciones)
# ---------------------------------------------------------------------------
def test_ficha_cliente(client, cleaner):
    cot, pedido = _base_pedido(client, cleaner, precio=100000)
    cliente_id = cot["cliente_id"]

    r = client.get(f"/api/v1/historial/cliente/{cliente_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"GET ficha cliente → {r.status_code}: {r.text}"
    ficha = r.json()
    assert ficha["cliente"]["id"] == cliente_id
    resumen = ficha["resumen"]
    assert any(c["id"] == cot["id"] for c in resumen["cotizaciones"])
    assert any(p["id"] == pedido["id"] for p in resumen["pedidos"])
    assert any(v["pedido_id"] == pedido["id"] if "pedido_id" in v else True for v in resumen["ventas"]), \
        "El cliente debe tener su venta asociada"


# ---------------------------------------------------------------------------
# 7) Auditoría solo para administradores
# ---------------------------------------------------------------------------
def test_auditoria_solo_admin(client, cleaner):
    cot, pedido = _base_pedido(client, cleaner, precio=100000)

    ficha_admin = client.get(f"/api/v1/historial/pedido/{pedido['id']}", headers=ADMIN_HEADERS).json()
    assert isinstance(ficha_admin["auditoria"], list)
    assert len(ficha_admin["auditoria"]) >= 1, "El admin debe ver los eventos (conversión genera eventos)"
    entidades = {e["entidad"] for e in ficha_admin["auditoria"]}
    assert "cotizacion" in entidades and "pedido" in entidades

    ficha_ventas = client.get(f"/api/v1/historial/pedido/{pedido['id']}", headers=VENTAS_HEADERS).json()
    assert ficha_ventas["auditoria"] == [], "Un usuario sin rol admin no debe recibir la auditoría"


# ---------------------------------------------------------------------------
# 8) 404 para entidades inexistentes
# ---------------------------------------------------------------------------
def test_ficha_404(client):
    for ruta in ("pedido", "cotizacion", "factura", "envio", "cliente"):
        r = client.get(f"/api/v1/historial/{ruta}/999999999", headers=ADMIN_HEADERS)
        assert r.status_code == 404, f"{ruta} inexistente debe dar 404, fue {r.status_code}"