"""
test_buscador_pedidos.py — Búsqueda de pedidos para Paola.

Cubre:
  1. Buscar por #pedido (con y sin '#').
  2. Buscar por #cotización (el número que se ve en Cotizaciones).
  3. Buscar por cédula del cliente.
  4. "Historial Completo": sin mes/año devuelve pedidos de meses anteriores.

Ejecutar: pytest test/test_buscador_pedidos.py -v
"""
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_cliente
from helpers_e2e import crear_cotizacion_multidetalle, convertir_cotizacion


def _crear_pedido_reparacion(client, cleaner, cliente_id):
    """Crea una cotización de reparación en BORRADOR y la convierte a pedido."""
    detalle = {
        "tipo_item": "REPARACION",
        "cantidad": 1,
        "precio": 150000.0,
        "descripcion_especifica": "Reparación de prueba de búsqueda",
    }
    cot = crear_cotizacion_multidetalle(client, cleaner, cliente_id, [detalle])
    r, pedido = convertir_cotizacion(client, cleaner, cot["id"], [detalle])
    assert r.status_code in (200, 201), f"convertir → {r.status_code}: {r.text}"
    return cot, pedido


def _ids(resultado):
    return {int(o["id"]) for o in resultado}


def test_buscar_pedido_por_su_numero(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    _, pedido = _crear_pedido_reparacion(client, cleaner, cliente["id"])

    for termino in (str(pedido["id"]), f"#{pedido['id']}"):
        r = client.get("/api/v1/pedido/", params={"buscar": termino}, headers=ADMIN_HEADERS)
        assert r.status_code == 200, r.text
        assert pedido["id"] in _ids(r.json()), (
            f"buscar={termino!r} debe encontrar el pedido #{pedido['id']}"
        )


def test_buscar_pedido_por_numero_de_cotizacion(client, cleaner):
    cliente = crear_cliente(client, cleaner)
    cot, pedido = _crear_pedido_reparacion(client, cleaner, cliente["id"])

    r = client.get(
        "/api/v1/pedido/", params={"buscar": f"#{cot['id']}"}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200, r.text
    assert pedido["id"] in _ids(r.json()), (
        f"buscar=#{cot['id']} debe encontrar el pedido generado por esa cotización"
    )


def test_buscar_pedido_por_cedula_del_cliente(client, db, cleaner):
    cliente = crear_cliente(client, cleaner)
    cedula = f"V-{cliente['id']}98765"
    db.execute(
        text("UPDATE cliente SET cedula = :c WHERE id = :id"),
        {"c": cedula, "id": cliente["id"]},
    )
    db.commit()

    _, pedido = _crear_pedido_reparacion(client, cleaner, cliente["id"])
    r = client.get("/api/v1/pedido/", params={"buscar": cedula}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert pedido["id"] in _ids(r.json()), "debe encontrar el pedido por cédula"


def test_historial_completo_incluye_pedidos_de_otros_meses(client, db, cleaner):
    cliente = crear_cliente(client, cleaner)
    _, pedido = _crear_pedido_reparacion(client, cleaner, cliente["id"])

    # Mover el pedido 40 días atrás: siempre cae fuera del mes actual.
    fecha_vieja = date.today() - timedelta(days=40)
    db.execute(
        text("UPDATE pedido SET fecha = :f WHERE id = :id"),
        {"f": fecha_vieja, "id": pedido["id"]},
    )
    db.commit()

    # Sin "Historial Completo" (mes actual) NO aparece.
    r = client.get("/api/v1/pedido/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    assert pedido["id"] not in _ids(r.json())

    # Con historial completo (sin mes/año) SÍ aparece.
    r = client.get(
        "/api/v1/pedido/",
        params={"solo_mes_actual": "false", "limite": 1000},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    assert pedido["id"] in _ids(r.json()), (
        "Historial Completo debe incluir pedidos de meses anteriores"
    )
