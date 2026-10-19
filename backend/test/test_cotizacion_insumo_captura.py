"""
test_cotizacion_insumo_captura.py — Captura flexible de insumos en Cotizaciones.

Caso real: la madera se inventaría en m³ pero se cotiza al cliente en cm
(cuenta del taller). El renglón guarda 1128 cm × 160 COP/cm (total 180.480),
pero el costo y el inventario usan 0,1128 m³. Antes el sistema guardaba
1128 m³, disparaba el costo a 1.804.800.000 y bloqueaba la venta por stock.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_cotizacion_insumo_captura.py -v
"""
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

UNIDAD_M3 = 193  # catálogo de unidades del seed
UNIDAD_UND = 1


def _cotizacion_insumo(
    client,
    cleaner,
    cliente_id,
    material_id,
    *,
    cantidad,
    precio,
    unidad_captura=None,
    cantidad_base=None,
    costo_total=None,
) -> dict:
    detalle = {
        "producto_id": None,
        "material_id": material_id,
        "tipo_item": "INSUMO",
        "cantidad": cantidad,
        "precio": precio,
    }
    if unidad_captura:
        detalle["unidad_captura"] = unidad_captura
    if cantidad_base is not None:
        detalle["cantidad_base"] = cantidad_base
    if costo_total is not None:
        detalle["costo_total"] = costo_total

    payload = {
        "cliente_id": cliente_id,
        "fecha": str(date.today()),
        "estado": "BORRADOR",
        "total_estimado": round(precio * cantidad, 2),
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": _uniq("cot_insumo_captura"),
        "detalles": [detalle],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear cotización INSUMO → {r.status_code}: {r.text}"
    cot = r.json()
    cleaner.registrar("cotizacion", cot["id"])
    return cot


def _convertir(client, cleaner, cot_id, material_id, *, cantidad, precio) -> dict:
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


def test_madera_cotizada_en_cm_descuenta_m3(client, db, cleaner):
    """1128 cm × 160 = 180.480; stock baja 0,1128 m³ (no 1128)."""
    cliente = crear_cliente(client, cleaner)
    madera = crear_material(
        client, cleaner, nombre=_uniq("madera_cm"),
        costo_base=1_600_000.0, unidad_medida_id=UNIDAD_M3,
    )
    crear_movimiento(client, cleaner, madera["id"], "ENTRADA", 1)
    registrar_inventario_de_material(db, cleaner, madera["id"])
    assert _stock(db, madera["id"]) == Decimal("1")

    cot = _cotizacion_insumo(
        client, cleaner, cliente["id"], madera["id"],
        cantidad=1128, precio=160, unidad_captura="CM",
        cantidad_base=0.1128, costo_total=180_480,
    )
    det = cot["detalles"][0]
    assert float(det["cantidad"]) == 1128.0
    assert det["unidad_captura"] == "CM"
    assert float(det["cantidad_base"]) == 0.1128
    assert float(det["costo_total"]) == 180_480.0

    pedido = _convertir(
        client, cleaner, cot["id"], madera["id"], cantidad=1128, precio=160,
    )
    dp = pedido["detalles"][0]
    assert float(dp["cantidad"]) == 1128.0
    assert dp["unidad_captura"] == "CM"
    assert float(dp["cantidad_base"]) == 0.1128
    # Costo por unidad vendida (cm): 180.480 / 1128 = 160.
    assert float(dp["costo_unitario"]) == 160.0

    venta_id = _venta_id(db, pedido["id"])
    assert venta_id is not None, "La conversión debe crear la venta automáticamente"
    cleaner.registrar("venta", venta_id)
    db.expire_all()
    assert _stock(db, madera["id"]) == Decimal("0.8872")

    rv = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    assert rv.status_code == 200
    dv = rv.json()["detalles"][0]
    assert dv["tipo_item"] == "INSUMO"
    assert float(dv["cantidad"]) == 1128.0
    assert dv["unidad_captura"] == "CM"
    assert float(dv["cantidad_base"]) == 0.1128
    assert float(dv["costo_unitario"]) == 160.0
    assert float(dv["utilidad"]) == 0.0

    mov = db.execute(text(
        "SELECT cantidad FROM movimiento_inventario "
        "WHERE material_id = :m AND referencia_tipo = 'VENTA' AND tipo = 'SALIDA' "
        "ORDER BY id DESC LIMIT 1"
    ), {"m": madera["id"]}).fetchone()
    assert Decimal(str(mov[0])) == Decimal("0.1128")


def test_madera_cotizada_en_m3_con_4_decimales(client, db, cleaner):
    """0,1128 m³ se guarda exacto; no se redondea a 0,11."""
    cliente = crear_cliente(client, cleaner)
    madera = crear_material(
        client, cleaner, nombre=_uniq("madera_m3"),
        costo_base=1_600_000.0, unidad_medida_id=UNIDAD_M3,
    )
    crear_movimiento(client, cleaner, madera["id"], "ENTRADA", 1)
    registrar_inventario_de_material(db, cleaner, madera["id"])

    cot = _cotizacion_insumo(
        client, cleaner, cliente["id"], madera["id"],
        cantidad=0.1128, precio=1_600_000,
        cantidad_base=0.1128, costo_total=180_480,
    )
    det = cot["detalles"][0]
    assert float(det["cantidad"]) == 0.1128
    assert det["unidad_captura"] is None
    assert float(det["cantidad_base"]) == 0.1128

    pedido = _convertir(
        client, cleaner, cot["id"], madera["id"],
        cantidad=0.1128, precio=1_600_000,
    )
    dp = pedido["detalles"][0]
    assert float(dp["cantidad"]) == 0.1128
    assert float(dp["cantidad_base"]) == 0.1128

    db.expire_all()
    assert _stock(db, madera["id"]) == Decimal("0.8872")


def test_unidad_captura_invalida_se_rechaza(client, cleaner):
    """No se puede capturar en cm un material vendido por unidad."""
    cliente = crear_cliente(client, cleaner)
    tornillo = crear_material(
        client, cleaner, nombre=_uniq("tornillo"), costo_base=500.0,
        unidad_medida_id=UNIDAD_UND,
    )
    r = client.post("/api/v1/cotizacion/", json={
        "cliente_id": cliente["id"],
        "fecha": str(date.today()),
        "estado": "BORRADOR",
        "total_estimado": 500.0,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": _uniq("cot_insumo_invalido"),
        "detalles": [{
            "producto_id": None,
            "material_id": tornillo["id"],
            "tipo_item": "INSUMO",
            "cantidad": 1,
            "precio": 500.0,
            "unidad_captura": "CM",
        }],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "Unidad de captura inválida" in r.text


def test_insumo_legacy_sin_unidad_usa_cantidad_como_base(client, cleaner):
    """Cotizaciones viejas sin unidad de captura: cantidad_base = cantidad."""
    cliente = crear_cliente(client, cleaner)
    material = crear_material(client, cleaner, costo_base=1000.0)
    cot = _cotizacion_insumo(
        client, cleaner, cliente["id"], material["id"],
        cantidad=2, precio=2000,
    )
    det = cot["detalles"][0]
    assert det["unidad_captura"] is None
    assert float(det["cantidad_base"]) == 2.0


def test_editar_cotizacion_insumo_conserva_captura_cm(client, cleaner):
    """Editar la cotización reemplaza los renglones y recalcula cantidad_base."""
    cliente = crear_cliente(client, cleaner)
    madera = crear_material(
        client, cleaner, nombre=_uniq("madera_edit"),
        costo_base=1_600_000.0, unidad_medida_id=UNIDAD_M3,
    )
    cot = _cotizacion_insumo(
        client, cleaner, cliente["id"], madera["id"],
        cantidad=1128, precio=160, unidad_captura="CM",
        cantidad_base=0.1128, costo_total=180_480,
    )
    r = client.put(f"/api/v1/cotizacion/{cot['id']}", json={
        "cliente_id": cliente["id"],
        "fecha": str(date.today()),
        "estado": "BORRADOR",
        "total_estimado": 180_480,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "observaciones": cot["observaciones"],
        "detalles": [{
            "producto_id": None,
            "material_id": madera["id"],
            "tipo_item": "INSUMO",
            "cantidad": 1128,
            "precio": 160,
            "unidad_captura": "CM",
            "cantidad_base": 0.1128,
            "costo_total": 180_480,
        }],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    det = r.json()["detalles"][0]
    assert det["unidad_captura"] == "CM"
    assert float(det["cantidad_base"]) == 0.1128
    assert float(det["costo_total"]) == 180_480.0
