#!/usr/bin/env python3
"""
test_ataques_autz.py — Autorización profunda (BOLA/IDOR/función-level) y
flujos de inventario/compras/envíos del ERP YEIKAR.

Cada test intenta un ataque concreto y exige que el sistema lo REPELA con el
status adecuado (4xx) o que los invariantes se mantengan intactos. Si el test
FALLA, documenta un bug real (se reporta; no se arregla aquí).

Alcance:
  1. IDOR: Ventas accede/edita registros (pedido, cotización, orden de
     producción, gasto) creados por jackson (Dueño).
  2. Ventas crea material/producto (función-level).
  3. Ventas registra movimiento de inventario (función-level).
  4. Inventario: ENTRADA negativa / cero.
  5. Inventario: ENTRADA gigante (desbordamiento).
  6. Inventario: material / ubicación inexistentes (500 o 4xx).
  7. Compra: costo_unitario negativo / cero / gigante.
  8. Compra: RECIBIDA dos veces (doble entrada de stock).
  9. Producción: consumo de material sin stock (stock negativo).
 10. Envíos: reglas de estado, doble ENTREGADO, pedido inexistente.
 11. Precios de producción: precio negativo / gigante / área inexistente.
 12. Empleados: cargo inexistente, tipo_pago inválido, sueldo negativo.
 13. Registro público /register: mass assignment de rol (escalada a Dueño).
 14. Ventas accede a reportes financieros (estado del día).

Ejecutar:
  cd /home/daniel-castellanos/YEIKAR/backend
  venv/bin/python -m pytest test/test_ataques_autz.py -v
"""
import uuid
from datetime import date, datetime

import pytest

from app.core.config import settings  # noqa: F401
from app.db.session import session_local

try:
    from conftest import (
        ADMIN_HEADERS,
        VENTAS_HEADERS,
        crear_cliente,
        crear_cotizacion,
        crear_compra,
        crear_material,
        crear_orden_desde_pedido,
        crear_producto,
        crear_proveedor,
        actualizar_estado_compra,
        registrar_inventario_de_material,
        registrar_venta_de_pedido,
    )
except ImportError:  # pragma: no cover
    pytest.fail("No se pudo importar conftest")


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _stock_material(db, material_id: int, ubicacion_id: int = 1) -> float:
    from sqlalchemy import text
    row = db.execute(
        text("SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=:u"),
        {"m": material_id, "u": ubicacion_id},
    ).fetchone()
    return float(row[0]) if row else 0.0


def _envio_de_pedido(db, pedido_id: int):
    from sqlalchemy import text
    row = db.execute(text("SELECT id FROM envio WHERE pedido_id=:p"), {"p": pedido_id}).fetchone()
    return int(row[0]) if row else None


def _crear_pedido_jackson(client, cleaner, precio=100_000):
    """Flujo completo jackson: cliente → producto → cotización → pedido COTIZADO."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], precio)
    r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json={
        "detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": precio}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"convertir cotización → {r.status_code}: {r.text[:200]}"
    ped = r.json()
    cleaner.registrar("pedido", ped["id"])
    registrar_venta_de_pedido(client, cleaner, ped["id"])
    return cot, ped


def _finalizar_pedido(client, cleaner, ped, precio=100_000):
    """Lleva un pedido a TERMINADO vía producción (etapa + FINALIZADA)."""
    orden = crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])
    r = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 3, "estado": "ASIGNADA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    etapa = r.json()["id"]
    cleaner.registrar("etapa_produccion", etapa)
    assert client.put(f"/api/v1/produccion/etapa/{etapa}/estado",
                      params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS).status_code == 200
    assert client.put(f"/api/v1/produccion/etapa/{etapa}/estado",
                      params={"estado": "COMPLETADA"}, headers=ADMIN_HEADERS).status_code == 200
    r = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado",
                   params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return orden


# ═══════════════════════════════════════════════════════════════════════════
# 1. IDOR — Ventas accede/edita registros de jackson
# ═══════════════════════════════════════════════════════════════════════════

def test_01_idor_ventas_sobre_registros_jackson(client, db, cleaner):
    """Ventas (daniel) intenta VER/EDITAR pedidos, cotizaciones, órdenes de
    producción y gastos creados por jackson (Dueño). Debe ser repelido
    (403/404), nunca 200."""
    cot, ped = _crear_pedido_jackson(client, cleaner)
    orden = crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])

    r = client.post("/api/v1/gasto/gastos/", json={
        "tipo_gasto_id": 2, "moneda_id": 1, "fecha": str(date.today()),
        "monto": 5000, "descripcion": f"test_idor_{_uid()}",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    gasto_id = r.json()["id"]
    cleaner.registrar("gasto", gasto_id)

    intentos = [
        ("GET", f"/api/v1/pedido/{ped['id']}", None),
        ("PUT", f"/api/v1/pedido/{ped['id']}", {"observaciones": "intento de daniel"}),
        ("GET", f"/api/v1/cotizacion/{cot['id']}", None),
        ("GET", f"/api/v1/produccion/orden/{orden['id']}", None),
        ("GET", f"/api/v1/gasto/gastos/{gasto_id}", None),
    ]
    for metodo, path, payload in intentos:
        rr = client.request(metodo, path, json=payload, headers=VENTAS_HEADERS)
        print(f"  IDOR {metodo} {path} → {rr.status_code}")
        assert rr.status_code in (403, 404), (
            f"IDOR {metodo} {path} → {rr.status_code}: Ventas accedió a un registro de jackson "
            f"(BUG de alcance) {rr.text[:200]}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2-3. Función-level: Ventas NO puede crear material/producto ni movimiento
# ═══════════════════════════════════════════════════════════════════════════

def test_02_ventas_no_crea_material_ni_producto(client):
    """Ventas tiene materiales/productos SOLO lectura (gestionar=False):
    crear material o producto debe ser 403."""
    r = client.post("/api/v1/material/", json={
        "nombre": f"hack_mat_{_uid()}", "unidad_medida_id": 2, "costo_base": 1000.0,
    }, headers=VENTAS_HEADERS)
    assert r.status_code == 403, (
        f"Ventas creó MATERIAL (puede inventar materiales con costos) → BUG: {r.status_code} {r.text[:200]}"
    )
    r = client.post("/api/v1/producto/", json={
        "nombre": f"hack_prod_{_uid()}", "tipo_producto_id": 1,
        "ancho_base": 1.6, "largo_base": 1.9,
    }, headers=VENTAS_HEADERS)
    assert r.status_code == 403, (
        f"Ventas creó PRODUCTO → BUG: {r.status_code} {r.text[:200]}"
    )


def test_03_ventas_no_registra_movimiento_inventario(client):
    """Ventas no tiene el módulo inventario: registrar movimiento debe ser 403."""
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": 1, "ubicacion_id": 1, "tipo": "ENTRADA", "cantidad": 10,
    }, headers=VENTAS_HEADERS)
    assert r.status_code == 403, (
        f"Ventas registró movimiento de inventario (puede inflar stock) → BUG: {r.status_code} {r.text[:200]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4-6. Inventario — integridad
# ═══════════════════════════════════════════════════════════════════════════

def test_04_inventario_entrada_negativa_cero(client, db, cleaner):
    """ENTRADA con cantidad negativa o cero no debe reducir stock."""
    mat = crear_material(client, cleaner)
    for cant in (-100, 0):
        r = client.post("/api/v1/inventario/movimiento", json={
            "material_id": mat["id"], "ubicacion_id": 1, "tipo": "ENTRADA", "cantidad": cant,
        }, headers=ADMIN_HEADERS)
        assert r.status_code == 422, (
            f"ENTRADA cantidad={cant} aceptada → BUG: {r.status_code} {r.text[:150]}"
        )
    assert _stock_material(db, mat["id"]) == 0.0, (
        f"stock alterado por cantidad inválida → {_stock_material(db, mat['id'])}"
    )


def test_05_inventario_entrada_gigante(client, db, cleaner):
    """ENTRADA de 1e15 (desborda Numeric(12,2)) debe rechazarse, no corromper stock."""
    mat = crear_material(client, cleaner)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"], "ubicacion_id": 1, "tipo": "ENTRADA", "cantidad": 1e15,
    }, headers=ADMIN_HEADERS)
    stock = _stock_material(db, mat["id"])
    print(f"  ENTRADA 1e15 → {r.status_code} · stock={stock}")
    assert r.status_code in (400, 422), (
        f"ENTRADA 1e15 aceptada → BUG: {r.status_code} {r.text[:150]} · stock={stock}"
    )


def test_06_inventario_material_ubicacion_inexistentes(client, cleaner):
    """material_id / ubicacion_id inexistentes → 4xx, nunca 500."""
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": 999999999, "ubicacion_id": 1, "tipo": "ENTRADA", "cantidad": 5,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (400, 404, 409, 422), (
        f"material inexistente → {r.status_code} (500=BUG) {r.text[:150]}"
    )
    mat = crear_material(client, cleaner)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"], "ubicacion_id": 999999999, "tipo": "ENTRADA", "cantidad": 5,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (400, 404, 409, 422), (
        f"ubicación inexistente → {r.status_code} (500=BUG) {r.text[:150]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7-8. Compras — integridad
# ═══════════════════════════════════════════════════════════════════════════

def test_07_compra_costo_unitario_extremo(client, cleaner):
    """costo_unitario negativo/cero/gigante en una compra debe rechazarse."""
    prov = crear_proveedor(client, cleaner)
    mat = crear_material(client, cleaner)
    base = {
        "proveedor_id": prov["id"], "moneda_id": 1, "fecha": str(date.today()),
        "estado": "BORRADOR", "observaciones": f"test07_{_uid()}",
    }
    for cu in (-100, 0):
        r = client.post("/api/v1/compras/", json={
            **base, "detalle": [{"material_id": mat["id"], "cantidad": 1, "costo_unitario": cu}],
        }, headers=ADMIN_HEADERS)
        assert r.status_code == 422, (
            f"compra costo_unitario={cu} aceptada → BUG: {r.status_code} {r.text[:150]}"
        )
    r = client.post("/api/v1/compras/", json={
        **base, "detalle": [{"material_id": mat["id"], "cantidad": 1, "costo_unitario": 1e15}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (400, 422), (
        f"compra costo_unitario=1e15 aceptada → BUG: {r.status_code} {r.text[:150]}"
    )


def test_08_compra_recibida_dos_veces_no_duplica_stock(client, db, cleaner):
    """Marcar una compra RECIBIDA dos veces no debe sumar el stock 2 veces."""
    prov = crear_proveedor(client, cleaner)
    mat = crear_material(client, cleaner)
    compra = crear_compra(client, cleaner, prov["id"], mat["id"], cantidad=10, costo_unitario=500.0)

    r, _ = actualizar_estado_compra(client, compra["id"], "RECIBIDA")
    assert r.status_code == 200, r.text
    stock1 = _stock_material(db, mat["id"])
    r2, _ = actualizar_estado_compra(client, compra["id"], "RECIBIDA")
    stock2 = _stock_material(db, mat["id"])
    print(f"  RECIBIDA x2: stock 1ª={stock1}, 2ª={stock2} · statuses={r.status_code}/{r2.status_code}")
    assert stock1 == 10.0, f"esperado 10 tras primera RECIBIDA, hay {stock1}"
    assert stock2 == stock1, (
        f"doble RECIBIDA duplicó stock: {stock1} → {stock2} (BUG de doble entrada)"
    )
    registrar_inventario_de_material(db, cleaner, mat["id"])


# ═══════════════════════════════════════════════════════════════════════════
# 9. Consumo de material SIN stock
# ═══════════════════════════════════════════════════════════════════════════

def test_09_consumo_material_sin_stock_rechazado(client, db, cleaner):
    """Consumir un material sin stock (o con stock insuficiente) no debe
    dejar el inventario en negativo."""
    cot, ped = _crear_pedido_jackson(client, cleaner)
    orden = crear_orden_desde_pedido(client, cleaner, ped["detalles"][0]["id"])
    r = client.post("/api/v1/produccion/etapa/", json={
        "orden_produccion_id": orden["id"], "area_id": 1,
        "empleado_responsable_id": 3, "estado": "EN_PROCESO",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    etapa = r.json()["id"]
    cleaner.registrar("etapa_produccion", etapa)

    mat = crear_material(client, cleaner)  # material nuevo SIN inventario
    payload = {
        "etapa_produccion_id": etapa, "material_id": mat["id"], "cantidad": 10,
        "fecha": datetime.utcnow().isoformat(),
        "solicitante_empleado_id": 3,
    }
    r = client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)
    print(f"  consumo sin stock → {r.status_code} {r.text[:120]}")
    assert r.status_code == 400, (
        f"consumo sin stock aceptado → BUG: {r.status_code} {r.text[:200]} · stock={_stock_material(db, mat['id'])}"
    )
    assert _stock_material(db, mat["id"]) == 0.0, "stock quedó negativo"

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"], "ubicacion_id": 1, "tipo": "ENTRADA", "cantidad": 3,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/produccion/consumo/", json={
        **payload, "cantidad": 10,
    }, headers=ADMIN_HEADERS)
    print(f"  consumo 10 con stock 3 → {r.status_code} {r.text[:120]}")
    assert r.status_code == 400, (
        f"consumo > stock aceptado → BUG: {r.status_code} {r.text[:200]} · stock={_stock_material(db, mat['id'])}"
    )
    assert _stock_material(db, mat["id"]) == 3.0, "stock quedó negativo tras consumo excesivo"
    registrar_inventario_de_material(db, cleaner, mat["id"])


# ═══════════════════════════════════════════════════════════════════════════
# 10. Envíos
# ═══════════════════════════════════════════════════════════════════════════

def test_10_envio_reglas(client, db, cleaner):
    """Reglas de envío: no entregar pedido no TERMINADO, no saltar estados,
    doble ENTREGADO sin corromper, pedido inexistente → 400."""
    # a) envío ENTREGADO de un pedido NO TERMINADO → 400
    cot, ped = _crear_pedido_jackson(client, cleaner)
    r = client.post("/api/v1/envio/", json={
        "pedido_id": ped["id"], "estado": "ENTREGADO", "direccion_entrega": "x",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, (
        f"envío ENTREGADO de pedido no TERMINADO aceptado → BUG: {r.status_code} {r.text[:200]}"
    )

    # b) envío con pedido inexistente → 400
    r = client.post("/api/v1/envio/", json={
        "pedido_id": 999999999, "estado": "PREPARADO",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, (
        f"envío con pedido inexistente → {r.status_code} (500=BUG) {r.text[:150]}"
    )

    # c) doble ENTREGADO sobre envío auto-creado tras finalizar producción
    cot2, ped2 = _crear_pedido_jackson(client, cleaner)
    _finalizar_pedido(client, cleaner, ped2)
    r = client.get(f"/api/v1/pedido/{ped2['id']}", headers=ADMIN_HEADERS)
    assert r.json()["estado"] == "TERMINADO", r.json()["estado"]
    envio_id = _envio_de_pedido(db, ped2["id"])
    assert envio_id, "no se auto-creó el envío tras finalizar producción"
    cleaner.registrar("envio", envio_id)

    r = client.put(f"/api/v1/envio/{envio_id}/estado", params={"estado": "ENTREGADO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"salto PREPARADO→ENTREGADO aceptado → {r.status_code} {r.text[:150]}"

    assert client.put(f"/api/v1/envio/{envio_id}/estado", params={"estado": "EN_TRANSITO"},
                      headers=ADMIN_HEADERS).status_code == 200
    r1 = client.put(f"/api/v1/envio/{envio_id}/estado", params={"estado": "ENTREGADO"}, headers=ADMIN_HEADERS)
    r2 = client.put(f"/api/v1/envio/{envio_id}/estado", params={"estado": "ENTREGADO"}, headers=ADMIN_HEADERS)
    print(f"  ENTREGADO dos veces → {r1.status_code} / {r2.status_code}")
    r = client.get(f"/api/v1/pedido/{ped2['id']}", headers=ADMIN_HEADERS)
    assert r.json()["estado"] == "ENTREGADO", (
        f"pedido en {r.json()['estado']} tras doble ENTREGADO (inconsistencia) → BUG"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 11. Precios de producción
# ═══════════════════════════════════════════════════════════════════════════

def test_11_precio_produccion_extremos(client, cleaner):
    """Precio negativo / gigante / área inexistente en costo-producción."""
    r = client.post("/api/v1/costo-produccion/", json={
        "area_id": 1, "descripcion": f"test11_{_uid()}", "precio": -5,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 422, f"precio negativo aceptado → BUG: {r.status_code} {r.text[:150]}"

    r = client.post("/api/v1/costo-produccion/", json={
        "area_id": 999999, "descripcion": f"test11b_{_uid()}", "precio": 100,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, f"área inexistente → {r.status_code} (500=BUG) {r.text[:150]}"

    r = client.post("/api/v1/costo-produccion/", json={
        "area_id": 1, "descripcion": f"test11c_{_uid()}", "precio": 1e15,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (400, 422), f"precio gigante aceptado → BUG: {r.status_code} {r.text[:150]}"


# ═══════════════════════════════════════════════════════════════════════════
# 12. Empleados
# ═══════════════════════════════════════════════════════════════════════════

def test_12_empleado_datos_invalidos(client, cleaner):
    """cargo inexistente → 4xx; tipo_pago inválido debe rechazarse; sueldo negativo → 422."""
    r = client.post("/api/v1/empleado/", json={
        "nombre": f"hack_{_uid()}", "cargo_id": 999999, "tipo_pago": "DESTAJO", "sueldo_semanal": 100,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (400, 422), (
        f"empleado cargo inexistente → {r.status_code} (500=BUG) {r.text[:150]}"
    )

    r = client.post("/api/v1/empleado/", json={
        "nombre": f"hack2_{_uid()}", "cargo_id": 1, "tipo_pago": "DESTAJO", "sueldo_semanal": -50,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 422, f"sueldo negativo aceptado → BUG: {r.status_code} {r.text[:150]}"

    r = client.post("/api/v1/empleado/", json={
        "nombre": f"hack3_{_uid()}", "cargo_id": 1, "tipo_pago": "HACKER", "sueldo_semanal": 100,
    }, headers=ADMIN_HEADERS)
    if r.status_code in (200, 201):
        cleaner.registrar("empleado", r.json()["id"])
        print(f"  ⚠ BUG: empleado con tipo_pago 'HACKER' ACEPTADO → {r.status_code}, id={r.json()['id']}")
    assert r.status_code in (400, 422), (
        f"empleado con tipo_pago 'HACKER' aceptado → BUG de validación: {r.status_code} {r.text[:150]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 13. /api/auth/register — mass assignment de rol
# ═══════════════════════════════════════════════════════════════════════════

def test_13_register_mass_assignment_rol(client, db, cleaner):
    """El registro público no debe aplicar campos de privilegio del payload
    (es_admin/rol/rol_id) y solo debe estar disponible para administradores."""
    nombre = f"hacker_rol_{_uid()}"
    r = client.post("/api/auth/register", json={
        "nombre_usuario": nombre, "password": "Xy12345!",
        "es_admin": True, "rol": "Dueño", "rol_id": 1, "activo": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"register: {r.status_code} {r.text[:200]}"
    uid = r.json().get("id")
    if uid:
        cleaner.registrar("usuario", uid)
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT r.nombre FROM usuario_rol ur JOIN rol r ON r.id=ur.rol_id WHERE ur.usuario_id=:u"
    ), {"u": uid}).fetchall()
    nombres = [x[0] for x in rows]
    assert "Dueño" not in nombres, (
        f"escalada a Dueño vía /register mass assignment → BUG: roles={nombres}"
    )

    r2 = client.post("/api/auth/register", json={
        "nombre_usuario": f"hx_{_uid()}", "password": "Xy12345!",
    }, headers=VENTAS_HEADERS)
    assert r2.status_code == 403, (
        f"Ventas registró un usuario → BUG: {r2.status_code} {r2.text[:150]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 14. Ventas NO accede a reportes financieros
# ═══════════════════════════════════════════════════════════════════════════

def test_14_ventas_no_ve_reportes_financieros(client):
    """Estado del día / PnL / informe mensual son exclusivos de Dueño/Admin."""
    rutas = [
        "/api/v1/reports/diario",
        "/api/v1/reports/pnl?mes=2026-01",
        "/api/v1/reports/informe-mensual?mes=2026-01",
        "/api/v1/reports/rentabilidad-producto",
    ]
    for ruta in rutas:
        r = client.get(ruta, headers=VENTAS_HEADERS)
        assert r.status_code == 403, (
            f"Ventas accede a {ruta} (expone dinero) → BUG: {r.status_code} {r.text[:150]}"
        )
