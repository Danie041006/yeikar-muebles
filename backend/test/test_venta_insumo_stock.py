"""
test_venta_insumo_stock.py — Venta de insumos sueltos: stock y reversión.

Cadena completa INSUMO: cotización (tipo_item INSUMO) → pedido → venta
(descuenta stock del inventario de materiales) → eliminar la venta
(devuelve el stock y registra ENTRADA con referencia VENTA).

El descuento y la reversión usan la MISMA distribución por ubicaciones: la
reversión repone cada SALIDA en su ubicación original (kardex neto en cero).

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_venta_insumo_stock.py -v
"""
import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_cliente,
    crear_material,
    crear_movimiento,
    registrar_inventario_de_material,
)


def _cotizacion_insumo(client, cleaner, cliente_id, material_id, precio, cantidad=1) -> dict:
    """Cotización con un único renglón INSUMO (material vendido suelto)."""
    payload = {
        "cliente_id": cliente_id,
        "fecha": str(date.today()),
        "estado": "BORRADOR",
        "total_estimado": round(precio * cantidad, 2),
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": _uniq("cot_insumo"),
        "detalles": [
            {
                "producto_id": None,
                "material_id": material_id,
                "tipo_item": "INSUMO",
                "cantidad": cantidad,
                "precio": precio,
            }
        ],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear cotización INSUMO → {r.status_code}: {r.text}"
    cot = r.json()
    cleaner.registrar("cotizacion", cot["id"])
    return cot


def _convertir_insumo(client, cleaner, cot_id, material_id, precio, cantidad) -> dict:
    """Convierte la cotización de insumo en pedido (con renglón exacto)."""
    r = client.post(f"/api/v1/pedido/convertir/{cot_id}", json={
        "detalles": [
            {
                "producto_id": None,
                "material_id": material_id,
                "tipo_item": "INSUMO",
                "cantidad": cantidad,
                "precio": precio,
            }
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"conversión INSUMO → {r.status_code}: {r.text}"
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    return pedido


def _stock(db, material_id) -> Decimal:
    row = db.execute(
        text("SELECT COALESCE(SUM(cantidad), 0) FROM inventario WHERE material_id = :m"),
        {"m": material_id},
    ).fetchone()
    return Decimal(str(row[0]))


def _venta_id(db, pedido_id):
    row = db.execute(
        text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}
    ).fetchone()
    return int(row[0]) if row else None


def test_venta_insumo_descuenta_y_eliminar_revierte(client, db, cleaner):
    """Vender 2 láminas (de 10 en stock) descuenta 2; eliminar la venta las
    devuelve (kardex ENTRADA con referencia VENTA) y deja el stock original."""
    cliente = crear_cliente(client, cleaner)
    material = crear_material(client, cleaner, costo_base=5000.0)
    crear_movimiento(client, cleaner, material["id"], "ENTRADA", 10)
    registrar_inventario_de_material(db, cleaner, material["id"])
    assert _stock(db, material["id"]) == Decimal("10")

    precio, cantidad = 8000.0, 2
    cot = _cotizacion_insumo(client, cleaner, cliente["id"], material["id"], precio, cantidad)
    pedido = _convertir_insumo(client, cleaner, cot["id"], material["id"], precio, cantidad)

    # La conversión factura automáticamente (venta) → descuenta stock: 10 - 2 = 8.
    venta_id = _venta_id(db, pedido["id"])
    assert venta_id is not None, "La conversión debe crear la venta automáticamente"
    cleaner.registrar("venta", venta_id)
    db.expire_all()
    assert _stock(db, material["id"]) == Decimal("8")

    # Un renglón INSUMO en la venta.
    rv = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    assert rv.status_code == 200
    detalles = rv.json()["detalles"]
    assert len(detalles) == 1
    assert detalles[0]["tipo_item"] == "INSUMO"
    assert detalles[0]["material_id"] == material["id"]

    # Eliminar la venta SIN pagos (pedido sin adelanto) → revierte el stock.
    rd = client.delete(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    assert rd.status_code == 204, f"eliminar venta → {rd.status_code}: {rd.text}"

    db.expire_all()
    assert _stock(db, material["id"]) == Decimal("10"), "La reversión debe devolver el stock completo"

    # Kardex: queda la SALIDA de la venta y su ENTRADA de reversión.
    movs = db.execute(text(
        "SELECT tipo, cantidad, referencia_tipo, referencia_id FROM movimiento_inventario "
        "WHERE material_id = :m ORDER BY id"
    ), {"m": material["id"]}).fetchall()
    tipos = [(m[0], Decimal(str(m[1]))) for m in movs]
    assert tipos == [("ENTRADA", Decimal("10")), ("SALIDA", Decimal("2")), ("ENTRADA", Decimal("2"))]
    assert movs[-1][2] == "VENTA" and int(movs[-1][3]) == venta_id

    # La venta ya no existe; el pedido queda.
    assert _venta_id(db, pedido["id"]) is None
    r = client.get(f"/api/v1/pedido/{pedido['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200


def test_reversion_devuelve_stock_vendible(client, db, cleaner):
    """Tras revertir, el stock vuelve a estar disponible: con stock 0 la
    conversión de un nuevo insumo falla; tras revertir la venta anterior,
    el stock revertido puede venderse de nuevo."""
    cliente = crear_cliente(client, cleaner)
    material = crear_material(client, cleaner, costo_base=1000.0)
    crear_movimiento(client, cleaner, material["id"], "ENTRADA", 3)
    registrar_inventario_de_material(db, cleaner, material["id"])

    precio = 2000.0
    cot1 = _cotizacion_insumo(client, cleaner, cliente["id"], material["id"], precio, 3)
    pedido1 = _convertir_insumo(client, cleaner, cot1["id"], material["id"], precio, 3)
    venta1 = _venta_id(db, pedido1["id"])
    cleaner.registrar("venta", venta1)
    db.expire_all()
    assert _stock(db, material["id"]) == Decimal("0")

    # Sin stock: convertir una nueva cotización del mismo insumo falla.
    cot2 = _cotizacion_insumo(client, cleaner, cliente["id"], material["id"], precio, 1)
    r2 = client.post(f"/api/v1/pedido/convertir/{cot2['id']}", json={
        "detalles": [{"producto_id": None, "material_id": material["id"],
                      "tipo_item": "INSUMO", "cantidad": 1, "precio": precio}],
    }, headers=ADMIN_HEADERS)
    assert r2.status_code in (400, 409), f"convertir sin stock → {r2.status_code}: {r2.text}"

    # Revertir la primera venta → el stock vuelve y es vendible de nuevo.
    rd = client.delete(f"/api/v1/venta/{venta1}", headers=ADMIN_HEADERS)
    assert rd.status_code == 204
    db.expire_all()
    assert _stock(db, material["id"]) == Decimal("3")
