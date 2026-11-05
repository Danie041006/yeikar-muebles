"""Edición y anulación de ENTRADAS manuales de inventario.

Una entrada pagada desde caja tiene tres caras: stock, Gasto (P&L) y salida de
caja. Editar/anular solo una deja el sistema descuadrado. Estos tests cubren:
  - editar cantidad/precio/fecha/proveedor/cuenta y que las tres caras cuadren,
  - anular y que se revierta el stock y se borren gasto + salida de caja,
  - pagos mixtos reescalados y reconstruidos,
  - flete/llevada,
  - pasar de pagado a fiado y de fiado a pagado,
  - que Paola (rol Inventario, no Dueño) pueda corregir una entrada de otro,
  - candado de stock insuficiente.

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_inventario_editar_anular.py -v
"""
from decimal import Decimal

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    _firmar_token,
    crear_material,
    registrar_inventario_de_material,
)

PAOLA_HEADERS = {"Authorization": f"Bearer {_firmar_token('Paola_Yeikar')}"}


def _stock(db, material_id, ubicacion_id=1) -> Decimal:
    row = db.execute(
        text("SELECT cantidad FROM inventario WHERE material_id=:m AND ubicacion_id=:u"),
        {"m": material_id, "u": ubicacion_id},
    ).fetchone()
    return Decimal(str(row[0])) if row else Decimal("0")


def _costo_material(db, material_id) -> Decimal:
    return Decimal(str(
        db.execute(
            text("SELECT costo_base FROM material WHERE id=:m"), {"m": material_id}
        ).scalar()
    ))


def _gasto(db, gasto_id):
    return db.execute(
        text("SELECT monto, monto_en_moneda_base FROM gasto WHERE id=:g"),
        {"g": gasto_id},
    ).fetchone()


def _caja_por_gasto(db, gasto_id):
    return db.execute(
        text(
            "SELECT monto, monto_en_moneda_base, metodo_caja_id "
            "FROM movimiento_caja WHERE referencia=:r"
        ),
        {"r": f"Gasto #{gasto_id}"},
    ).fetchone()


def _cxp(db, movimiento_id):
    return db.execute(
        text(
            "SELECT id, gasto_id, monto, monto_en_moneda_base, estado "
            "FROM cuenta_por_pagar "
            "WHERE origen_tipo='ENTRADA_INVENTARIO' AND origen_id=:m"
        ),
        {"m": movimiento_id},
    ).fetchone()


def _crear_entrada_simple(client, cleaner, db, material, cantidad=4, costo=84000.0):
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "ENTRADA",
        "cantidad": cantidad,
        "costo_unitario": costo,
        "pagado_desde_metodo_caja_id": 1,
        "proveedor_nombre": "pintutecnicas",
        "departamento": "PINTURA",
        "recibido_por": "andres",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"entrada → {r.status_code}: {r.text}"
    mov = r.json()
    cleaner.registrar("movimiento_inventario", mov["id"])
    registrar_inventario_de_material(db, cleaner, material["id"])
    if mov.get("gasto_id"):
        cleaner.registrar("gasto", mov["gasto_id"])
        cleaner.registrar_caja_ref(f"Gasto #{mov['gasto_id']}")
    return mov


def _crear_entrada_mixta(client, cleaner, db, material):
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 500000,
        "pagos": [
            {"metodo_caja_id": 1, "moneda_id": 1, "monto": 600000},
            {"metodo_caja_id": 2, "moneda_id": 2, "monto": 100, "tasa_pago": 4000},
        ],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"entrada mixta → {r.status_code}: {r.text}"
    mov = r.json()
    cleaner.registrar("movimiento_inventario", mov["id"])
    registrar_inventario_de_material(db, cleaner, material["id"])
    for (gasto_id,) in db.execute(
        text(
            "SELECT gasto_id FROM entrada_compra_pago "
            "WHERE movimiento_inventario_id=:m ORDER BY id"
        ),
        {"m": mov["id"]},
    ).fetchall():
        cleaner.registrar("gasto", int(gasto_id))
        cleaner.registrar_caja_ref(f"Gasto #{int(gasto_id)}")
    return mov


def test_detalle_devuelve_los_pagos(client, db, cleaner):
    material = crear_material(client, cleaner, costo_base=1000.0)
    mov = _crear_entrada_simple(client, cleaner, db, material)

    r = client.get(f"/api/v1/inventario/movimiento/{mov['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    detalle = r.json()
    assert detalle["id"] == mov["id"]
    assert len(detalle["pagos"]) == 1
    pago = detalle["pagos"][0]
    assert pago["metodo_caja_id"] == 1
    assert pago["moneda_id"] == 1
    assert abs(float(pago["monto"]) - 336000.0) < 0.01


def test_editar_entrada_actualiza_stock_gasto_y_caja(client, db, cleaner):
    material = crear_material(client, cleaner, costo_base=1000.0)
    mov = _crear_entrada_simple(client, cleaner, db, material)

    assert _stock(db, material["id"]) == Decimal("4")
    assert _costo_material(db, material["id"]) == Decimal("84000")
    assert _gasto(db, mov["gasto_id"])[0] == Decimal("336000.00")
    assert _caja_por_gasto(db, mov["gasto_id"])[0] == Decimal("336000.00")

    # Sube cantidad y precio: stock +1, gasto y caja al nuevo total.
    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "cantidad": 5,
        "costo_unitario": 90000,
        "motivo_correccion": "La factura traía 5, no 4",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    mov = r.json()
    gasto_id = mov["gasto_id"]
    cleaner.registrar("gasto", gasto_id)
    cleaner.registrar_caja_ref(f"Gasto #{gasto_id}")
    assert _stock(db, material["id"]) == Decimal("5")
    assert _costo_material(db, material["id"]) == Decimal("90000")
    assert _gasto(db, gasto_id)[0] == Decimal("450000.00")
    assert _caja_por_gasto(db, gasto_id)[0] == Decimal("450000.00")

    # Baja cantidad y precio: stock 2, total 138.000.
    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "cantidad": 2,
        "costo_unitario": 69000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    mov = r.json()
    gasto_id = mov["gasto_id"]
    cleaner.registrar("gasto", gasto_id)
    cleaner.registrar_caja_ref(f"Gasto #{gasto_id}")
    assert _stock(db, material["id"]) == Decimal("2")
    assert _costo_material(db, material["id"]) == Decimal("69000")
    assert _gasto(db, gasto_id)[0] == Decimal("138000.00")
    assert _caja_por_gasto(db, gasto_id)[0] == Decimal("138000.00")

    # Anular: stock 0, costo 0, gasto y caja desaparecen.
    r = client.delete(
        f"/api/v1/inventario/movimiento/{mov['id']}",
        params={"motivo": "Entrada duplicada"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 204, r.text
    assert _stock(db, material["id"]) == Decimal("0")
    assert _costo_material(db, material["id"]) == Decimal("0")
    assert _gasto(db, gasto_id) is None
    assert _caja_por_gasto(db, gasto_id) is None
    quedan = db.execute(
        text("SELECT COUNT(*) FROM movimiento_inventario WHERE id=:m"), {"m": mov["id"]}
    ).scalar()
    assert quedan == 0


def test_cambiar_cuenta_de_pago_mueve_la_salida(client, db, cleaner):
    material = crear_material(client, cleaner, costo_base=1000.0)
    mov = _crear_entrada_simple(client, cleaner, db, material)

    # La cuenta 2 es USD: el backend debe rechazarla porque la compra es COP.
    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "pagado_desde_metodo_caja_id": 2,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "moneda" in r.text.lower()

    # La cuenta 1 es COP: el update es válido y deja la salida en esa cuenta.
    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "observaciones": "Corregido",
        "pagado_desde_metodo_caja_id": 1,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    mov = r.json()
    cleaner.registrar("gasto", mov["gasto_id"])
    cleaner.registrar_caja_ref(f"Gasto #{mov['gasto_id']}")
    assert _caja_por_gasto(db, mov["gasto_id"])[2] == 1


def test_anular_bloquea_si_el_stock_ya_se_consumio(client, db, cleaner):
    material = crear_material(client, cleaner, costo_base=1000.0)
    mov = _crear_entrada_simple(client, cleaner, db, material, cantidad=4)

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "SALIDA",
        "cantidad": 3,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cleaner.registrar("movimiento_inventario", r.json()["id"])

    r = client.delete(
        f"/api/v1/inventario/movimiento/{mov['id']}", headers=ADMIN_HEADERS
    )
    assert r.status_code == 400, r.text
    assert "stock" in r.text.lower()
    assert _stock(db, material["id"]) == Decimal("1")


def test_pagos_mixtos_se_reescalan_y_se_anulan(client, db, cleaner):
    material = crear_material(client, cleaner, costo_base=1000.0)
    mov = _crear_entrada_mixta(client, cleaner, db, material)

    filas = db.execute(
        text(
            "SELECT gasto_id, monto, monto_en_moneda_base, moneda_id "
            "FROM entrada_compra_pago WHERE movimiento_inventario_id=:m ORDER BY id"
        ),
        {"m": mov["id"]},
    ).fetchall()
    assert len(filas) == 2
    assert abs(float(filas[0][2]) - 600000.0) < 0.01
    assert abs(float(filas[1][2]) - 400000.0) < 0.01

    # Sube a 3 × 500.000 = 1.500.000: los pagos se reescalan 60/40.
    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "cantidad": 3,
        "costo_unitario": 500000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    mov = r.json()

    filas = db.execute(
        text(
            "SELECT gasto_id, monto, monto_en_moneda_base, moneda_id "
            "FROM entrada_compra_pago WHERE movimiento_inventario_id=:m ORDER BY id"
        ),
        {"m": mov["id"]},
    ).fetchall()
    assert len(filas) == 2
    for fila in filas:
        cleaner.registrar("gasto", int(fila[0]))
        cleaner.registrar_caja_ref(f"Gasto #{int(fila[0])}")
    assert abs(float(filas[0][2]) - 900000.0) < 0.01
    assert abs(float(filas[1][2]) - 600000.0) < 0.01
    assert abs(float(filas[1][1]) - 150.0) < 0.01
    assert abs(sum(float(f[2]) for f in filas) - 1500000.0) < 0.01
    assert _stock(db, material["id"]) == Decimal("3")

    r = client.delete(
        f"/api/v1/inventario/movimiento/{mov['id']}", headers=ADMIN_HEADERS
    )
    assert r.status_code == 204, r.text
    assert _stock(db, material["id"]) == Decimal("0")
    for fila in filas:
        assert _gasto(db, int(fila[0])) is None
        assert _caja_por_gasto(db, int(fila[0])) is None


def test_editar_flete_crea_y_elimina_su_gasto(client, db, cleaner):
    material = crear_material(client, cleaner, costo_base=1000.0)
    mov = _crear_entrada_simple(client, cleaner, db, material)

    # Flete de 50.000 COP desde la misma cuenta (Bancolombia/1).
    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "llevada": 50000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    mov = r.json()
    assert mov["llevada_gasto_id"] is not None
    flete_id = mov["llevada_gasto_id"]
    cleaner.registrar("gasto", flete_id)
    cleaner.registrar_caja_ref(f"Gasto #{flete_id}")
    flete = _gasto(db, flete_id)
    assert flete is not None
    assert abs(float(flete[0]) - 50000.0) < 0.01
    caja_flete = _caja_por_gasto(db, flete_id)
    assert caja_flete is not None
    assert abs(float(caja_flete[0]) - 50000.0) < 0.01

    # Quitar el flete: se borra su gasto y su salida de caja.
    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "llevada": 0,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    mov = r.json()
    assert mov["llevada_gasto_id"] is None
    assert _gasto(db, flete_id) is None
    assert _caja_por_gasto(db, flete_id) is None


def test_pasar_a_fiado_y_volver_a_pagado(client, db, cleaner):
    material = crear_material(client, cleaner, costo_base=1000.0)
    mov = _crear_entrada_simple(client, cleaner, db, material)
    gasto_original = mov["gasto_id"]

    # Pagado → fiado: se borran gasto/salida de caja y nace la cuenta por pagar.
    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "fiar": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    mov = r.json()
    assert mov["fiar"] is True
    assert mov["gasto_id"] is None
    assert _gasto(db, gasto_original) is None
    cxp = _cxp(db, mov["id"])
    assert cxp is not None
    assert abs(float(cxp[2]) - 336000.0) < 0.01
    assert cxp[4] == "PENDIENTE"
    cleaner.registrar("cuenta_por_pagar", int(cxp[0]))
    if cxp[1] is not None:
        cleaner.registrar("gasto", int(cxp[1]))

    # Fiado → pagado: se borra la deuda y vuelve la salida de caja.
    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "fiar": False,
        "pagos": [{"metodo_caja_id": 1, "moneda_id": 1, "monto": 336000}],
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    mov = r.json()
    assert mov["fiar"] is False
    assert mov["gasto_id"] is not None
    cleaner.registrar("gasto", mov["gasto_id"])
    cleaner.registrar_caja_ref(f"Gasto #{mov['gasto_id']}")
    assert _cxp(db, mov["id"]) is None
    assert _gasto(db, mov["gasto_id"])[0] == Decimal("336000.00")
    assert _caja_por_gasto(db, mov["gasto_id"])[0] == Decimal("336000.00")


def test_paola_puede_editar_una_entrada_de_otro_usuario(client, db, cleaner):
    """Paola tiene Inventario en modo gestionar; no necesita ser la autora."""
    material = crear_material(client, cleaner, costo_base=1000.0)
    mov = _crear_entrada_simple(client, cleaner, db, material)

    r = client.put(f"/api/v1/inventario/movimiento/{mov['id']}", json={
        "cantidad": 3,
        "costo_unitario": 80000,
        "motivo_correccion": "Corrección de Paola",
    }, headers=PAOLA_HEADERS)
    assert r.status_code == 200, r.text
    mov = r.json()
    cleaner.registrar("gasto", mov["gasto_id"])
    cleaner.registrar_caja_ref(f"Gasto #{mov['gasto_id']}")
    assert _stock(db, material["id"]) == Decimal("3")
    assert _costo_material(db, material["id"]) == Decimal("80000")
    assert _gasto(db, mov["gasto_id"])[0] == Decimal("240000.00")


def test_anular_una_entrada_de_otro_usuario_como_paola(client, db, cleaner):
    material = crear_material(client, cleaner, costo_base=1000.0)
    mov = _crear_entrada_simple(client, cleaner, db, material)

    r = client.delete(
        f"/api/v1/inventario/movimiento/{mov['id']}",
        params={"motivo": "Anulada por Paola"},
        headers=PAOLA_HEADERS,
    )
    assert r.status_code == 204, r.text
    assert _stock(db, material["id"]) == Decimal("0")
    assert _gasto(db, mov["gasto_id"]) is None
