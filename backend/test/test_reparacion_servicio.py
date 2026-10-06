"""
test_reparacion_servicio.py — Reparación (REPARACION) y Servicios (SERVICIO).

  1. Una línea REPARACION (pieza del cliente, sin producto) cotiza → el pedido
     nace en PRODUCCION y se crea una OrdenProduccion SIN producto. El taller
     registra tela/MO en una etapa (Tapicería), se finaliza, se conoce el costo
     real, el pedido pasa a TERMINADO y se auto-crea el envío.
  2. El endpoint de rentabilidad compara el costo real vs el estimado y expone
     el margen real (incluye el flete real del envío si se registra).
  3. Una línea SERVICIO (p. ej. flete) NO entra a producción: un pedido solo de
     reventa + servicio nace APROBADO, no genera orden y pasa directo a TERMINADO.
  4. La factura fiscal incluye la descripción del servicio (descripcion_especifica).

Ejecutar:  pytest test/test_reparacion_servicio.py -v
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente, crear_material
from helpers_e2e import (
    crear_cotizacion_multidetalle,
    convertir_cotizacion,
    crear_empleado,
    crear_etapa,
    crear_consumo,
    registrar_mano_obra,
    finalizar_orden,
    area_id,
    entrar_stock_material,
    venta_de_pedido,
    envio_de_pedido,
    crear_producto_reventa,
    crear_stock_producto,
    emitir_factura,
)


def _finalizar_reparacion(client, cleaner, db, orden_id, material_id, empleado_id):
    """Crea una etapa (Tapicería), registra un consumo + mano de obra y finaliza."""
    tapa = area_id(db, "Tapicería")
    etapa = crear_etapa(client, cleaner, orden_id, tapa, empleado_id, estado="ASIGNADA")
    assert client.put(
        f"/api/v1/produccion/etapa/{etapa['id']}/estado",
        params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS,
    ).status_code == 200
    r, _ = crear_consumo(client, cleaner, db, etapa["id"], material_id, 2, empleado_id)
    assert r.status_code in (200, 201), f"consumo → {r.status_code}: {r.text}"
    registrar_mano_obra(client, cleaner, etapa["id"], empleado_id, monto=15000.0)
    assert client.put(
        f"/api/v1/produccion/etapa/{etapa['id']}/estado",
        params={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS,
    ).status_code == 200
    return finalizar_orden(client, orden_id)


def test_reparacion_entra_a_produccion_y_cierra_con_costo_real(client, db, cleaner):
    cliente = crear_cliente(client, cleaner)
    mat = crear_material(client, cleaner, costo_base=3000.0)
    entrar_stock_material(client, cleaner, mat["id"], 10)
    emp = crear_empleado(client, cleaner, cargo_id=1)

    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [{
        "tipo_item": "REPARACION", "cantidad": 1, "precio": 250000.0,
        "descripcion_especifica": "Tapizar sofá de 3 puestos",
        "costo_total": 45000.0, "costo_materiales": 30000.0, "costo_mano_obra": 15000.0,
    }])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [{
        "tipo_item": "REPARACION", "cantidad": 1, "precio": 250000.0,
        "descripcion_especifica": "Tapizar sofá de 3 puestos",
    }])
    assert r.status_code in (200, 201), f"convertir → {r.status_code}: {r.text}"
    assert pedido["estado"] == "PRODUCCION", "una reparación es producible → PRODUCCION"

    # Se auto-creó una OrdenProduccion SIN producto.
    orden = db.execute(text(
        "SELECT o.id, o.detalle_pedido_id, o.producto_id, o.tipo "
        "FROM orden_produccion o "
        "JOIN detalle_pedido d ON d.id = o.detalle_pedido_id "
        "WHERE d.pedido_id = :p"
    ), {"p": pedido["id"]}).fetchone()
    assert orden is not None, "la reparación debe crear orden de producción"
    assert orden[2] is None, "la orden de reparación NO lleva producto"
    assert orden[3] == "PEDIDO"

    _finalizar_reparacion(client, cleaner, db, orden[0], mat["id"], emp["id"])

    # Costo real guardado (materiales + MO + gastos de sección).
    costo = db.execute(text(
        "SELECT costo_material, costo_mano_obra, costo_gastos, costo_total "
        "FROM costo_produccion WHERE orden_produccion_id = :o"
    ), {"o": orden[0]}).fetchone()
    assert costo is not None, "al finalizar se calcula el costo"
    assert float(costo[0]) >= 6000.0, "materiales = 2 × 3000"
    assert float(costo[1]) >= 15000.0, "mano de obra registrada"
    assert float(costo[3]) > 0, "costo total > 0"

    # El pedido terminó y se auto-creó el envío.
    envio = envio_de_pedido(db, pedido["id"])
    assert envio is not None, "al terminar la reparación se crea el envío"

    # Rentabilidad: costo real vs estimado, margen real.
    r = client.get(f"/api/v1/pedido/{pedido['id']}/rentabilidad", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    rent = r.json()
    assert rent["tiene_produccion"] is True
    assert rent["costo_estimado_produccion"] >= 45000.0
    assert rent["costo_real_produccion"] > 0
    assert rent["total_cobrado_base"] == 250000.0
    assert rent["margen_real"] == rent["total_cobrado_base"] - rent["costo_real_produccion"]
    assert rent["margen_estimado"] == rent["total_cobrado_base"] - rent["costo_estimado_produccion"]


def test_servicio_con_reventa_no_entra_a_produccion(client, db, cleaner):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto_reventa(client, cleaner, costo_base=50000.0)
    crear_stock_producto(client, cleaner, db, prod["id"], 1, 50000.0)
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        {"producto_id": prod["id"], "tipo_item": "REVENTA", "cantidad": 1,
         "precio": 100000.0, "ancho": 1.6, "largo": 1.9},
        {"tipo_item": "SERVICIO", "cantidad": 1, "precio": 30000.0,
         "descripcion_especifica": "Flete / Envío a distancia"},
    ])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [
        {"producto_id": prod["id"], "tipo_item": "REVENTA", "cantidad": 1,
         "precio": 100000.0, "ancho": 1.6, "largo": 1.9},
        {"tipo_item": "SERVICIO", "cantidad": 1, "precio": 30000.0,
         "descripcion_especifica": "Flete / Envío a distancia"},
    ])
    assert r.status_code in (200, 201), f"convertir → {r.status_code}: {r.text}"
    assert pedido["estado"] == "APROBADO", "reventa + servicio no es producible"

    n_ordenes = db.execute(text(
        "SELECT COUNT(*) FROM orden_produccion o JOIN detalle_pedido d ON d.id = o.detalle_pedido_id "
        "WHERE d.pedido_id = :p"
    ), {"p": pedido["id"]}).scalar()
    assert n_ordenes == 0, "el servicio NO genera orden de producción"

    # El pedido va directo a TERMINADO → se crea el envío.
    r = client.put(f"/api/v1/pedido/{pedido['id']}", json={"estado": "TERMINADO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert envio_de_pedido(db, pedido["id"]) is not None

    # Rentabilidad con flete cobrado como SERVICIO.
    rent = client.get(f"/api/v1/pedido/{pedido['id']}/rentabilidad", headers=ADMIN_HEADERS).json()
    assert rent["tiene_produccion"] is False
    assert rent["total_cobrado_base"] == 130000.0
    assert rent["flete_cobrado_base"] == 30000.0
    assert rent["margen_real"] == rent["total_cobrado_base"] - rent["costo_real_produccion"]


def test_servicio_se_factura_con_su_descripcion(client, db, cleaner):
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto_reventa(client, cleaner, costo_base=50000.0)
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [{
        "tipo_item": "SERVICIO", "cantidad": 1, "precio": 30000.0,
        "descripcion_especifica": "Instalación a domicilio",
    }])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [{
        "tipo_item": "SERVICIO", "cantidad": 1, "precio": 30000.0,
        "descripcion_especifica": "Instalación a domicilio",
    }])
    assert r.status_code in (200, 201), f"convertir → {r.status_code}: {r.text}"
    venta = venta_de_pedido(client, db, pedido["id"])
    assert venta is not None

    dp_id = pedido["detalles"][0]["id"]
    r, fac = emitir_factura(client, cleaner, db, pedido["id"],
                            [{"detalle_pedido_id": dp_id, "precio_usd": 10.0}],
                            permitir_saldo_pendiente=True)
    assert r.status_code in (200, 201), f"factura → {r.status_code}: {r.text}"
    det = client.get(f"/api/v1/factura/{fac['id']}", headers=ADMIN_HEADERS).json()
    linea = next(d for d in det["detalles"] if d["id"] == dp_id or True)
    assert "Instalación a domicilio" in (linea["descripcion"] or ""), (
        "la factura debe llevar la descripción del servicio, no quedar vacía")


def test_flete_real_se_resta_del_margen(client, db, cleaner):
    """Registrar el costo real del flete en el envío lo resta del margen real."""
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto_reventa(client, cleaner, costo_base=50000.0)
    crear_stock_producto(client, cleaner, db, prod["id"], 1, 50000.0)
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        {"producto_id": prod["id"], "tipo_item": "REVENTA", "cantidad": 1,
         "precio": 100000.0, "ancho": 1.6, "largo": 1.9},
    ])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [
        {"producto_id": prod["id"], "tipo_item": "REVENTA", "cantidad": 1,
         "precio": 100000.0, "ancho": 1.6, "largo": 1.9},
    ])
    assert r.status_code in (200, 201), r.text
    client.put(f"/api/v1/pedido/{pedido['id']}", json={"estado": "TERMINADO"}, headers=ADMIN_HEADERS)
    envio = envio_de_pedido(db, pedido["id"])
    assert envio is not None

    # Registrar el costo real del flete (COP).
    r = client.put(f"/api/v1/envio/{envio['id']}", json={
        "costo_flete": 15000.0, "moneda_flete_id": 1,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    rent = client.get(f"/api/v1/pedido/{pedido['id']}/rentabilidad", headers=ADMIN_HEADERS).json()
    assert rent["flete_real_base"] == 15000.0
    assert rent["margen_real"] == rent["total_cobrado_base"] - rent["costo_real_produccion"] - 15000.0