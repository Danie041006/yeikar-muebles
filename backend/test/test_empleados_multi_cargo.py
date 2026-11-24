"""Cargos múltiples por empleado y creación de cargos desde Empleados.

Ejecutar solo contra una BD de pruebas aislada:
  DATABASE_URL=postgresql://qa:qa-local@127.0.0.1:55432/yeikar_empleados_test \
  venv/bin/python -m pytest test/test_empleados_multi_cargo.py -v
"""
from sqlalchemy import text

from conftest import ADMIN_HEADERS


def _cargos(client):
    r = client.get("/api/v1/catalogos/cargo/", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    return {c["nombre"]: c["id"] for c in r.json()}


def test_crear_cargo_desde_empleado_es_idempotente(client, db):
    creados = []
    try:
        r = client.post(
            "/api/v1/empleado/cargo/",
            json={"nombre": "Gerente de Ventas"},
            headers=ADMIN_HEADERS,
        )
        assert r.status_code == 201, r.text
        primero = r.json()
        creados.append(primero["id"])
        assert primero["nombre"] == "Gerente de Ventas"

        # Mismo nombre con otra capitalización: reutiliza, no duplica.
        r = client.post(
            "/api/v1/empleado/cargo/",
            json={"nombre": "gerente de ventas"},
            headers=ADMIN_HEADERS,
        )
        assert r.status_code == 201, r.text
        assert r.json()["id"] == primero["id"]
    finally:
        if creados:
            db.execute(
                text("DELETE FROM cargo WHERE id = ANY(:ids)"),
                {"ids": creados},
            )
            db.commit()


def test_empleado_con_varios_cargos_crea_y_actualiza(client, db):
    creados = []
    try:
        cargos = _cargos(client)
        operario = cargos["Operario"]
        asesora = cargos["ASESORA"]
        exhibidora = cargos["EXHIBIDORA DE VENTAS"]

        r = client.post("/api/v1/empleado/", json={
            "nombre": "Stefanny QA",
            "cargo_id": operario,
            "cargo_ids": [operario, asesora, exhibidora],
            "en_nomina": True,
            "tipo_pago": "DESTAJO",
        }, headers=ADMIN_HEADERS)
        assert r.status_code == 201, r.text
        empleado = r.json()
        creados.append(empleado["id"])
        assert empleado["cargo_id"] == operario
        assert [c["nombre"] for c in empleado["cargos"]] == [
            "Operario", "ASESORA", "EXHIBIDORA DE VENTAS",
        ]

        r = client.put(f"/api/v1/empleado/{empleado['id']}", json={
            "cargo_ids": [exhibidora, asesora],
        }, headers=ADMIN_HEADERS)
        assert r.status_code == 200, r.text
        actualizado = r.json()
        assert actualizado["cargo_id"] == exhibidora
        assert [c["nombre"] for c in actualizado["cargos"]] == [
            "EXHIBIDORA DE VENTAS", "ASESORA",
        ]

        r = client.get("/api/v1/empleado/", headers=ADMIN_HEADERS)
        assert r.status_code == 200, r.text
        fila = next(e for e in r.json() if e["id"] == empleado["id"])
        assert [c["nombre"] for c in fila["cargos"]] == [
            "EXHIBIDORA DE VENTAS", "ASESORA",
        ]

        # El principal se antepone aunque no venga primero en cargo_ids.
        r = client.put(f"/api/v1/empleado/{empleado['id']}", json={
            "cargo_id": operario,
            "cargo_ids": [asesora],
        }, headers=ADMIN_HEADERS)
        assert r.status_code == 200, r.text
        assert [c["nombre"] for c in r.json()["cargos"]] == ["Operario", "ASESORA"]
    finally:
        for empleado_id in creados:
            client.delete(f"/api/v1/empleado/{empleado_id}", headers=ADMIN_HEADERS)
