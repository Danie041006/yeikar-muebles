"""Entrada de inventario pagada en una moneda distinta al COP.

- El movimiento guarda `moneda_pago_id`, `tasa_pago` y el `gasto_id` generado
  (antes esa info vivía solo en el gasto y se perdía al borrarlo).
- El gasto se crea en la moneda de la cuenta con el equivalente en COP.
- Ese gasto NO se puede borrar por separado: dejaría la entrada sin pago.

Ejecutar:  pytest test/test_entrada_moneda_pago.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_material,
    registrar_inventario_de_material,
)


def _cuenta_usd(db):
    row = db.execute(text(
        """
        SELECT mc.id, mc.moneda_id
        FROM metodo_caja mc
        JOIN moneda mo ON mo.id = mc.moneda_id
        WHERE mo.codigo = 'USD'
        ORDER BY mc.id
        LIMIT 1
        """
    )).fetchone()
    assert row is not None, "No hay cuenta de caja en USD para el test"
    return int(row[0]), int(row[1])


def test_entrada_en_usd_guarda_moneda_tasa_y_gasto(client, cleaner, db):
    mat = crear_material(client, cleaner)
    cuenta_id, moneda_id = _cuenta_usd(db)

    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": mat["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 20,
        "costo_unitario": 84760,
        "pagado_desde_metodo_caja_id": cuenta_id,
        "moneda_pago_id": moneda_id,
        "tasa_pago": 3260,
        "proveedor_nombre": "IMECA",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    mov = r.json()
    registrar_inventario_de_material(db, cleaner, mat["id"])
    cleaner.registrar("movimiento_inventario", mov["id"])

    # El movimiento conserva la moneda, la tasa y el gasto vinculado.
    assert mov["moneda_pago_id"] == moneda_id
    assert float(mov["tasa_pago"]) == 3260
    assert mov["gasto_id"] is not None
    gasto_id = mov["gasto_id"]
    cleaner.registrar("gasto", gasto_id)
    cleaner.registrar_caja_ref(f"Gasto #{gasto_id}")

    # El gasto nace en USD por 520 (1.695.200 COP ÷ 3.260) y con su equivalente.
    row = db.execute(text(
        "SELECT moneda_id, monto, tasa_cambio, monto_en_moneda_base FROM gasto WHERE id = :g"
    ), {"g": gasto_id}).fetchone()
    assert int(row[0]) == moneda_id
    assert float(row[1]) == 520.0
    assert float(row[2]) == 3260.0
    assert float(row[3]) == 1695200.0

    # El gasto autogenerado no se puede borrar solo.
    r = client.delete(f"/api/v1/gasto/gastos/{gasto_id}", headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "entrada de inventario" in r.json()["detail"].lower()
