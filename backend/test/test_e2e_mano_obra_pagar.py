"""
test_e2e_mano_obra_pagar.py
===========================
Regresión del fix: el frontend llamaba PUT /produccion/mano-obra/{id}/pagar
(endpoint que NO existía → 404). Ahora el endpoint existe y materializa el
egreso "Mano de Obra de Producción" al marcar pagada, y lo revierte al
desmarcar (mismo marcador [mano_obra {id}]).

Ejecutar:  pytest test/test_e2e_mano_obra_pagar.py -v
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente, crear_material, crear_receta
from helpers_e2e import (
    area_id,
    cargos,
    convertir_cotizacion,
    crear_cotizacion_multidetalle,
    crear_empleado,
    crear_etapa,
    crear_producto_fabricado,
    entrar_stock_material,
)


def test_mano_obra_marcar_pagada_crea_y_revierte_egreso(client, cleaner, db):
    # 1. Escenario mínimo: cliente + mueble + receta + orden + etapa EN_PROCESO.
    cliente = crear_cliente(client, cleaner)
    material = crear_material(client, cleaner, unidad_medida_id=2)
    entrar_stock_material(client, cleaner, material["id"], 50)
    producto = crear_producto_fabricado(client, cleaner)
    crear_receta(client, cleaner, producto["id"], material["id"], 2.0, "FIJO", "EBANISTERIA")
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente["id"], [
        {"producto_id": producto["id"], "tipo_item": "FABRICADO", "cantidad": 1, "precio": 150000},
    ])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [
        {"producto_id": producto["id"], "tipo_item": "FABRICADO", "cantidad": 1, "precio": 150000},
    ])
    assert r.status_code == 201, r.text

    # La conversión no crea la orden: se crea al pasar el pedido a PRODUCCION
    # (orders/service) o con /orden/desde-pedido. Usamos desde-pedido.
    detalle_id = pedido["detalles"][0]["id"]
    r = client.post(f"/api/v1/produccion/orden/desde-pedido/{detalle_id}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), r.text
    orden = r.json()
    cleaner.registrar("orden_produccion", orden["id"])

    emp = crear_empleado(client, cleaner, cargo_id=cargos(db)["ebanista"], en_nomina=True)
    etapa = crear_etapa(client, cleaner, orden["id"], area_id(db, "Ebanistería"), emp["id"])
    r = client.put(f"/api/v1/produccion/etapa/{etapa['id']}/estado",
                   params={"estado": "EN_PROCESO"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text

    # 2. Mano de obra (etapa EN_PROCESO).
    r = client.post("/api/v1/produccion/mano-obra/", json={
        "etapa_produccion_id": etapa["id"],
        "empleado_id": emp["id"],
        "monto": 25000,
        "porcentaje_recargo": 10.0,
        "listo_nomina": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    mo = r.json()
    cleaner.registrar("mano_obra", mo["id"])

    def _gasto_mano_obra():
        return db.execute(text(
            "SELECT id, monto FROM gasto WHERE observaciones LIKE :pat"
        ), {"pat": f"%[mano_obra {mo['id']}]%"}).fetchone()

    # 3. ANTES del fix este endpoint daba 404 → ahora 200 y crea el egreso.
    r = client.put(f"/api/v1/produccion/mano-obra/{mo['id']}/pagar",
                   params={"pagado": True}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["pagado"] is True
    gasto = _gasto_mano_obra()
    assert gasto is not None, "Debe materializar el egreso al marcar pagada"
    # monto = 25000 × 1.10 = 27500
    assert float(gasto[1]) == 27500.0
    cleaner.registrar("gasto", gasto[0])

    # 4. Desmarcar → el egreso se revierte (gasto eliminado).
    r = client.put(f"/api/v1/produccion/mano-obra/{mo['id']}/pagar",
                   params={"pagado": False}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["pagado"] is False
    assert _gasto_mano_obra() is None, "Al desmarcar debe revertirse el egreso"

    # 5. Doble marca pagada no duplica el egreso (idempotente).
    for _ in range(2):
        r = client.put(f"/api/v1/produccion/mano-obra/{mo['id']}/pagar",
                       params={"pagado": True}, headers=ADMIN_HEADERS)
        assert r.status_code == 200, r.text
    gasto = _gasto_mano_obra()
    assert gasto is not None
    cleaner.registrar("gasto", gasto[0])
    n = db.execute(text("SELECT count(*) FROM gasto WHERE observaciones LIKE :pat"),
                   {"pat": f"%[mano_obra {mo['id']}]%"}).scalar()
    assert n == 1, "No debe duplicarse el egreso"

    # 6. La mano de obra pagada no se puede eliminar (protección contable).
    r = client.delete(f"/api/v1/produccion/mano-obra/{mo['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text

    print("[FIX mano-obra/pagar] egreso creado (27500), revertido, idempotente y protegido")