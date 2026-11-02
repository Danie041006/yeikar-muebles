"""
test_comprobantes_caja.py — Comprobante del pago visible desde Cuentas.

Cubre:
  1. `GET /cuenta/movimiento/{id}/comprobantes` devuelve el recibo del pago.
  2. `GET /cuenta/movimientos` expone `pago_id`.
  3. `GET /cuenta/libro` expone `pago_id` en la fila del movimiento.
  4. `GET /venta/cuentas-por-cobrar/` cuenta los comprobantes (`recibos_count`)
     para marcarlos en la tarjeta de Cobros.

Ejecutar: pytest test/test_comprobantes_caja.py -v
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente, crear_cotizacion, crear_producto
from helpers_e2e import convertir_cotizacion

# Imagen real en memoria (el servicio de adjuntos valida y recomprime).
_buf = io.BytesIO()
Image.new("RGB", (4, 4), (220, 180, 60)).save(_buf, format="PNG")
PNG_1X1 = _buf.getvalue()


def test_comprobante_del_pago_se_ve_en_cuentas(client, db, cleaner):
    cliente = crear_cliente(client, cleaner)
    producto = crear_producto(client, cleaner)
    cot = crear_cotizacion(
        client, cleaner, cliente["id"], producto["id"], precio=100000.0
    )
    r, pedido = convertir_cotizacion(
        client, cleaner, cot["id"],
        [{"producto_id": producto["id"], "cantidad": 1, "precio": 100000.0}],
        adelanto=50000.0,
        moneda_adelanto_id=1,
        metodo_pago="EFECTIVO_COP",
    )
    assert r.status_code in (200, 201), f"convertir → {r.status_code}: {r.text}"

    ventas = client.get("/api/v1/venta/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    assert ventas.status_code == 200, ventas.text
    venta = next(v for v in ventas.json() if v["pedido_id"] == pedido["id"])
    detalle = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS)
    assert detalle.status_code == 200, detalle.text
    pago = detalle.json()["pagos"][0]
    pago_id = int(pago["id"])

    # Sube el comprobante del pago (la misma vía que usa Ventas).
    r = client.post(
        "/api/v1/adjunto/upload",
        data={"entidad_tipo": "PAGO", "entidad_id": str(pago_id)},
        files={"archivo": ("recibo.png", PNG_1X1, "image/png")},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, f"subir adjunto → {r.status_code}: {r.text}"
    adjunto_id = int(r.json()["id"])
    cleaner.registrar("adjunto", adjunto_id)

    mov = db.execute(
        text("SELECT id, metodo_caja_id, fecha FROM movimiento_caja WHERE pago_id = :p"),
        {"p": pago_id},
    ).fetchone()
    assert mov is not None, "el pago debe crear su movimiento de caja"
    mov_id, metodo_id, mov_fecha = int(mov[0]), int(mov[1]), mov[2]

    # 1) Endpoint nuevo: comprobantes del movimiento.
    r = client.get(
        f"/api/v1/cuenta/movimiento/{mov_id}/comprobantes", headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, r.text
    comprobantes = r.json()
    assert len(comprobantes) == 1
    assert comprobantes[0]["id"] == adjunto_id

    # 2) El listado de movimientos expone pago_id.
    r = client.get(
        "/api/v1/cuenta/movimientos",
        params={"metodo_caja_id": metodo_id},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    fila_mov = next(m for m in r.json() if m["id"] == mov_id)
    assert fila_mov["pago_id"] == pago_id

    # 3) El libro de caja expone pago_id en la fila.
    fecha = str(mov_fecha)
    r = client.get(
        "/api/v1/cuenta/libro",
        params={
            "metodo_caja_id": metodo_id,
            "fecha_desde": fecha,
            "fecha_hasta": fecha,
        },
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    fila_libro = next(f for f in r.json()["filas"] if f["id"] == mov_id)
    assert fila_libro["pago_id"] == pago_id

    # 4) Cobros marca la venta con la cantidad de comprobantes.
    r = client.get("/api/v1/venta/cuentas-por-cobrar/", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    cuenta = next(c for c in r.json() if c["venta_id"] == venta["id"])
    assert cuenta["recibos_count"] == 1
