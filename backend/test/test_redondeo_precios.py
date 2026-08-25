"""
test_redondeo_precios.py — Política de redondeo de precios al millar COP.

Cubre:
  1. Utilidad central `app/core/redondeo.py` (unit, sin BD).
  2. `calcular_costo_producto` devuelve precios múltiplos de 1.000.
  3. Pagos en moneda extranjera: el equivalente COP se redondea al millar.
  4. Venta queda PAGADA cuando el remanente tras el redondeo es ≤ 1.000 COP.
  5. Pagos en la misma moneda siguen siendo exactos (sin redondeo forzado).

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_redondeo_precios.py -v
"""
import pytest
from decimal import Decimal

from app.core.redondeo import (
    PASO_PRECIO_COP,
    es_multiplo_de_millar,
    redondear_a_multiplo,
    redondear_precio_cop,
)

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_cotizacion,
    crear_material,
    crear_pago,
    crear_producto,
    crear_receta,
)


# ---------------------------------------------------------------------------
# 1) Utilidad central (unit, sin BD)
# ---------------------------------------------------------------------------
def test_redondear_precio_cop_ceil():
    """ceil: cualquier precio sube al siguiente millar."""
    assert redondear_precio_cop(Decimal("999")) == Decimal("1000")
    assert redondear_precio_cop(Decimal("124650")) == Decimal("125000")
    assert redondear_precio_cop(Decimal("125000")) == Decimal("125000")
    assert redondear_precio_cop(Decimal("0")) == Decimal("0")
    assert redondear_precio_cop(Decimal("36.47")) == Decimal("1000")


def test_redondear_precio_cop_half_up():
    """half_up: al millar más cercano, .5 hacia arriba."""
    assert redondear_precio_cop(Decimal("124499"), "half_up") == Decimal("124000")
    assert redondear_precio_cop(Decimal("124500"), "half_up") == Decimal("125000")
    assert redondear_precio_cop(Decimal("125000"), "half_up") == Decimal("125000")


def test_redondear_a_multiplo_otros_pasos():
    assert redondear_a_multiplo(Decimal("31.25"), Decimal("0.01")) == Decimal("31.25")
    assert redondear_a_multiplo(Decimal("31.256"), Decimal("0.01")) == Decimal("31.26")
    assert redondear_a_multiplo(Decimal("124226.56"), PASO_PRECIO_COP) == Decimal("124000")


def test_es_multiplo_de_millar():
    assert es_multiplo_de_millar(Decimal("125000"))
    assert not es_multiplo_de_millar(Decimal("125036"))
    assert es_multiplo_de_millar(0)


# ---------------------------------------------------------------------------
# 2) El precio calculado de un producto siempre es múltiplo de 1.000
# ---------------------------------------------------------------------------
def test_calcular_precio_devuelve_millar(client, cleaner):
    """GET /producto/{id}/calcular-precio → precio_venta termina en 000."""
    producto = crear_producto(client, cleaner)
    material = crear_material(client, cleaner, costo_base=45350.5)  # costo con decimales
    crear_receta(client, cleaner, producto["id"], material["id"], cantidad_base=0.75)

    r = client.get(
        f"/api/v1/producto/{producto['id']}/calcular-precio",
        params={"ancho": 1.60, "largo": 1.90, "ganancia": 40, "impuesto": 7, "iva": 0},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"calcular-precio → {r.status_code}: {r.text}"
    precio = Decimal(str(r.json()["precio_venta"]))
    assert precio > 0, "El precio calculado debe ser mayor a cero"
    assert es_multiplo_de_millar(precio), f"precio_venta={precio} no termina en 000"


def test_recalcular_precios_vista_previa_al_millar(client, cleaner):
    """POST /producto/recalcular-precios (vista previa) propone precios al millar."""
    producto = crear_producto(client, cleaner)
    material = crear_material(client, cleaner, costo_base=32000.0)
    crear_receta(client, cleaner, producto["id"], material["id"], cantidad_base=2.0)

    r = client.post("/api/v1/producto/recalcular-precios", json={"aplicar": False}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"recalcular-precios → {r.status_code}: {r.text}"
    fila = next((f for f in r.json() if f["producto_id"] == producto["id"]), None)
    assert fila is not None, "El producto debe aparecer en la vista previa"
    precio_nuevo = Decimal(str(fila["precio_nuevo"]))
    assert es_multiplo_de_millar(precio_nuevo), f"precio_nuevo={precio_nuevo} no termina en 000"


# ---------------------------------------------------------------------------
# 3) Pago en USD sobre factura COP → equivalente COP al millar
# ---------------------------------------------------------------------------
def _venta_cop_convertida(client, cleaner, precio=100000):
    """Cotización COP → pedido sin adelanto (factura PENDIENTE). Devuelve (pedido, venta)."""
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cliente["id"], producto["id"], precio=precio)
    r = client.post(
        f"/api/v1/pedido/convertir/{cot['id']}",
        json={"detalles": [{"producto_id": producto["id"], "cantidad": 1, "precio": precio,
                            "costo_unitario": 1000, "porcentaje_ganancia": 40}]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, f"Conversión → {r.status_code}: {r.text}"
    pedido_id = r.json()["id"]
    cleaner.registrar("pedido", pedido_id)
    venta = client.get("/api/v1/venta/", params={"limite": 1000}, headers=ADMIN_HEADERS).json()
    venta = next(v for v in venta if v["pedido_id"] == pedido_id)
    cleaner.registrar("venta", venta["id"])
    det = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    for d in det.get("detalles", []):
        cleaner.registrar("detalle_venta", d["id"])
    return pedido_id, det


def test_pago_usd_base_cop_redondeada_al_millar(client, cleaner):
    """Pago USD 22.30 @ 4500 sobre factura COP 100.000:
       equivale a 100.350 COP → se redondea a 100.000 (múltiplo del millar) y la
       factura queda PAGADA (remanente de redondeo ≤ 1.000 absorbido)."""
    _, venta = _venta_cop_convertida(client, cleaner, precio=100000)

    r, body = crear_pago(client, cleaner, venta["id"], 2, 22.30,
                         metodo_pago="EFECTIVO_USD", tasa_cambio=4500)
    assert r.status_code in (200, 201), f"Pago USD → {r.status_code}: {body}"

    pago = body
    assert pago["monto_en_moneda_base"] == 100000.0, \
        f"100350 COP debe redondearse a 100000, fue {pago['monto_en_moneda_base']}"
    assert es_multiplo_de_millar(Decimal(str(pago["monto_en_moneda_base"])))

    venta2 = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert venta2["estado"] == "PAGADA", f"Factura debe quedar PAGADA, fue {venta2['estado']}"
    assert venta2["saldo_pendiente"] == pytest.approx(0.0, abs=0.01)


def test_pago_usd_redondeo_parcial_no_paga(client, cleaner):
    """Pago USD 18 @ 4500 = 81.000 COP sobre factura 100.000 → ABONADA (saldo 19.000)."""
    _, venta = _venta_cop_convertida(client, cleaner, precio=100000)

    r, body = crear_pago(client, cleaner, venta["id"], 2, 18.0,
                         metodo_pago="EFECTIVO_USD", tasa_cambio=4500)
    assert r.status_code in (200, 201), f"Pago USD → {r.status_code}: {body}"
    assert body["monto_en_moneda_base"] == 81000.0, \
        f"Equivalente COP debe ser 81000 (múltiplo del millar), fue {body['monto_en_moneda_base']}"

    venta2 = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert venta2["estado"] == "ABONADA", f"Abono parcial debe quedar ABONADA, fue {venta2['estado']}"
    assert venta2["saldo_pendiente"] == pytest.approx(19000.0, abs=0.01)


def test_pago_misma_moneda_exacto(client, cleaner):
    """Pago COP en factura COP: el monto se registra EXACTO (sin redondeo al millar)."""
    _, venta = _venta_cop_convertida(client, cleaner, precio=100000)

    r, body = crear_pago(client, cleaner, venta["id"], 1, 40000.0, metodo_pago="EFECTIVO_COP")
    assert r.status_code in (200, 201), f"Pago COP → {r.status_code}: {body}"
    assert body["monto_en_moneda_base"] == 40000.0, \
        f"Pago en misma moneda debe ser exacto, fue {body['monto_en_moneda_base']}"

    venta2 = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
    assert venta2["estado"] == "ABONADA"
    assert venta2["saldo_pendiente"] == pytest.approx(60000.0, abs=0.01)


def test_pago_usd_movimiento_caja_usa_base_redondeada(client, cleaner, db):
    """El movimiento de caja del pago USD debe registrar el mismo COP redondeado
    que descuenta del saldo (consistencia libro vs caja)."""
    from sqlalchemy import text
    _, venta = _venta_cop_convertida(client, cleaner, precio=100000)

    r, body = crear_pago(client, cleaner, venta["id"], 2, 22.30,
                         metodo_pago="EFECTIVO_USD", tasa_cambio=4500)
    assert r.status_code in (200, 201), f"Pago USD → {r.status_code}: {body}"
    assert body["monto_en_moneda_base"] == 100000.0

    fila = db.execute(text(
        """SELECT monto_en_moneda_base FROM movimiento_caja WHERE pago_id = :p"""),
        {"p": body["id"]},
    ).fetchone()
    assert fila is not None, "El pago debe generar movimiento de caja"
    assert float(fila[0]) == pytest.approx(100000.0, abs=0.01), \
        f"Caja debe usar la base redondeada (100000), fue {fila[0]}"