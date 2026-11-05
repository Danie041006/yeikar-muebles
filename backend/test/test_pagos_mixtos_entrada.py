# -*- coding: utf-8 -*-
"""
test_pagos_mixtos_entrada.py — Compras de inventario pagadas de DOS maneras.

Caso real: entra madera y la paga la mitad en efectivo (COP) y el resto por
Zelle (USD). Antes solo existía un pago por entrada. Ahora:
  - `pagos: [...]` genera un gasto + salida de caja POR CADA pago.
  - La suma de los equivalentes en COP debe cuadrar con la compra.
  - El desglose queda en `entrada_compra_pago` y sale en el libro de entradas.

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_pagos_mixtos_entrada.py -v
"""
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_material,
    registrar_inventario_de_material,
)


def _crear_entrada(client, cleaner, db, material, pagos, cantidad=2, costo=500000.0):
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "ENTRADA",
        "cantidad": cantidad,
        "costo_unitario": costo,
        "pagos": pagos,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"entrada → {r.status_code}: {r.text}"
    mov = r.json()
    cleaner.registrar("movimiento_inventario", mov["id"])
    registrar_inventario_de_material(db, cleaner, material["id"])

    # Limpieza: los gastos + sus salidas de caja + las filas del desglose
    for (pago_row,) in db.execute(text(
        "SELECT id FROM entrada_compra_pago WHERE movimiento_inventario_id = :m"
    ).params(m=mov["id"])).fetchall():
        cleaner.registrar("entrada_compra_pago", int(pago_row))
    for (gasto_id,) in db.execute(text(
        "SELECT id FROM gasto WHERE descripcion LIKE :pat"
    ).params(pat=f"%{material['nombre']}%")).fetchall():
        cleaner.registrar("gasto", int(gasto_id))
        cleaner.registrar_caja_ref(f"Gasto #{int(gasto_id)}")
    return mov


def _salidas_caja(db, mov_id):
    return db.execute(text(
        """
        SELECT m.id, m.monto, m.tasa_cambio, m.monto_en_moneda_base, m.moneda_id, c.nombre
        FROM movimiento_caja m
        JOIN metodo_caja c ON c.id = m.metodo_caja_id
        JOIN entrada_compra_pago p ON p.gasto_id = cast(split_part(m.referencia, '#', 2) AS bigint)
        WHERE p.movimiento_inventario_id = :m
          AND m.referencia LIKE 'Gasto #%'
        ORDER BY p.id
        """
    ).params(m=mov_id)).fetchall()


def test_compra_pagada_en_dos_cuentas(client, cleaner, db):
    material = crear_material(client, cleaner, costo_base=500000.0)
    # 2 × 500.000 = 1.000.000 COP → 600.000 en efectivo + el resto (100 USD @ 4.000)
    mov = _crear_entrada(client, cleaner, db, material, [
        {"metodo_caja_id": 1, "moneda_id": 1, "monto": 600000},
        {"metodo_caja_id": 2, "moneda_id": 2, "monto": 100, "tasa_pago": 4000},
    ])

    salidas = _salidas_caja(db, mov["id"])
    assert len(salidas) == 2, f"deben ser dos salidas de caja: {salidas}"
    assert abs(float(salidas[0][1]) - 600000.0) < 0.01
    assert abs(float(salidas[1][1]) - 100.0) < 0.01
    assert float(salidas[1][2]) == 4000.0, "tasa COP por USD congelada"
    assert float(salidas[1][3]) == 400000.0, "equivalente en COP del pago USD"

    # El desglose quedó guardado
    filas = db.execute(text(
        "SELECT monto, tasa_cambio, monto_en_moneda_base, moneda_id FROM entrada_compra_pago "
        "WHERE movimiento_inventario_id = :m ORDER BY id"
    ).params(m=mov["id"])).fetchall()
    assert len(filas) == 2
    assert float(filas[1][1]) == 4000.0

    # Compatibilidad: los campos clásicos del movimiento apuntan al pago 1
    pagado = db.execute(text(
        "SELECT pagado_desde_metodo_caja_id FROM movimiento_inventario WHERE id = :m"
    ).params(m=mov["id"])).scalar()
    assert pagado == 1

    # El libro de entradas muestra el desglose
    from app.core.hora_ve import hoy_ve
    hoy = str(hoy_ve())
    r = client.get(
        "/api/v1/inventario/libro",
        params={"desde": hoy, "hasta": hoy, "lado": "ENTRADAS", "buscar": material["nombre"]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    fila = r.json()["filas"][0]
    assert len(fila["pagos"]) == 2
    assert fila["pagos"][0]["cuenta"] == "Efectivo en Pesos"
    assert fila["pagos"][1]["moneda"] == "USD"
    assert float(fila["pagos"][1]["monto_cop"]) == 400000.0


def test_pago_mixto_sin_tasa_rechaza(client, cleaner, db):
    material = crear_material(client, cleaner, costo_base=500000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "ENTRADA",
        "cantidad": 1,
        "costo_unitario": 400000,
        "pagos": [
            {"metodo_caja_id": 1, "moneda_id": 1, "monto": 300000},
            {"metodo_caja_id": 2, "moneda_id": 2, "monto": 25},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "tasa" in r.text.lower()


def test_pago_mixto_no_cuadra_rechaza(client, cleaner, db):
    material = crear_material(client, cleaner, costo_base=500000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 500000,
        "pagos": [
            {"metodo_caja_id": 1, "moneda_id": 1, "monto": 600000},
            {"metodo_caja_id": 2, "moneda_id": 2, "monto": 50, "tasa_pago": 4000},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "faltan" in r.text.lower()


def test_pago_mixto_faltante_rechaza(client, cleaner, db):
    material = crear_material(client, cleaner, costo_base=500000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 500000,
        "pagos": [
            {"metodo_caja_id": 1, "moneda_id": 1, "monto": 600000},
            {"metodo_caja_id": 2, "moneda_id": 2, "monto": 80, "tasa_pago": 4000},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "faltan" in r.text.lower()


def test_cuenta_de_otra_moneda_rechaza(client, cleaner, db):
    material = crear_material(client, cleaner, costo_base=500000.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "ENTRADA",
        "cantidad": 1,
        "costo_unitario": 400000,
        "pagos": [
            {"metodo_caja_id": 2, "moneda_id": 1, "monto": 400000},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "moneda" in r.text.lower()


def test_un_solo_pago_sigue_igual(client, cleaner, db):
    """`pagos` con UN pago equivale a la vía clásica: un gasto + una salida."""
    material = crear_material(client, cleaner, costo_base=500000.0)
    mov = _crear_entrada(client, cleaner, db, material, [
        {"metodo_caja_id": 1, "moneda_id": 1, "monto": 1000000},
    ])
    salidas = _salidas_caja(db, mov["id"])
    assert len(salidas) == 1
    assert abs(float(salidas[0][1]) - 1000000.0) < 0.01


def _crear_en_producto(client, cleaner, db, pagos, modo="reventa"):
    """Entrada de PRODUCTO (plásticos/reventa) pagada de N cuentas."""
    payload = {
        "nombre": _uniq(f"plastico_{modo}"),
        "tipo_producto_id": 2,
        "es_reventa": True,
    }
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    prod = r.json()
    cleaner.registrar("producto", prod["id"])
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": prod["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 3,
        "costo_unitario": 100000,
        "pagos": pagos,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"movimiento producto → {r.status_code}: {r.text}"
    mov = r.json()
    cleaner.registrar("movimiento_producto_inventario", mov["id"])
    for (gid,) in db.execute(text(
        "SELECT id FROM gasto WHERE descripcion LIKE :pat"
    ).params(pat=f"%{prod['nombre']}%")).fetchall():
        cleaner.registrar("gasto", int(gid))
        cleaner.registrar_caja_ref(f"Gasto #{int(gid)}")
    salidas = db.execute(text(
        """
        SELECT c.nombre, m.monto, m.monto_en_moneda_base
        FROM movimiento_caja m
        JOIN metodo_caja c ON c.id = m.metodo_caja_id
        JOIN entrada_compra_pago p ON p.gasto_id = cast(split_part(m.referencia, '#', 2) AS bigint)
        WHERE p.movimiento_producto_id = :m
          AND m.referencia LIKE 'Gasto #%'
        ORDER BY p.id
        """
    ).params(m=mov["id"])).fetchall()
    return mov, salidas


def test_compra_producto_pagada_en_dos_cuentas(client, cleaner, db):
    """Plásticos/reventa: mitad COP, resto USD; dos gastos y dos salidas."""
    mov, salidas = _crear_en_producto(client, cleaner, db, [
        {"metodo_caja_id": 1, "moneda_id": 1, "monto": 150000},
        {"metodo_caja_id": 2, "moneda_id": 2, "monto": 37.5, "tasa_pago": 4000},
    ])
    assert len(salidas) == 2
    assert abs(float(salidas[0][1]) - 150000.0) < 0.01
    assert abs(float(salidas[1][1]) - 37.5) < 0.01
    assert float(salidas[1][2]) == 150000.0, "37.5 USD × 4.000 = 150.000 COP"
    # El desglose queda registrado para el libro de productos
    n = db.execute(text(
        "SELECT count(*) FROM entrada_compra_pago WHERE movimiento_producto_id = :m"
    ).params(m=mov["id"])).scalar()
    assert n == 2
