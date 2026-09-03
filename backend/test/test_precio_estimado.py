"""
test_precio_estimado.py
=======================
Flujo del PRECIO ESTIMADO de venta: muebles que se cotizan de una vez con un
precio que da el vendedor mientras no tienen estructura de costos.

Reglas verificadas:
  1. Producto con SOLO precio de venta estimado → el precio sale TAL CUAL
     (sin inflar por impuesto/ganancia: el estimado ya es el precio final).
  2. Producto con costo estimado (sin precio) → margen sí aplica.
  3. Producto sin nada → 0 con fuente "sin_definir".
  4. Editar el estimado → el precio cambia al momento.

Ejecutar:  pytest test/test_precio_estimado.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from conftest import ADMIN_HEADERS, _uniq


def _crear(client, cleaner, **payload) -> dict:
    body = {"nombre": _uniq("est"), "tipo_producto_id": 1, **payload}
    r = client.post("/api/v1/producto/", json=body, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    prod = r.json()
    cleaner.registrar("producto", prod["id"])
    return prod


def _precio(client, producto_id, ganancia=40.0, impuesto=7.0) -> dict:
    r = client.post(
        f"/api/v1/producto/{producto_id}/calcular-precio",
        params={"ancho": 1.6, "largo": 1.9, "ganancia": ganancia, "impuesto": impuesto},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_estimado_puro_sale_tal_cual(client, cleaner):
    """El estimado es el precio final del cliente: ni impuesto ni ganancia
    se suman encima (ya van implícitos en el número que dio el vendedor)."""
    prod = _crear(client, cleaner, precio_venta_base=2500000)
    r = _precio(client, prod["id"])
    assert r["fuente_precio"] == "estimado_sin_estructura"
    assert r["precio_venta"] == 2500000.0
    assert r["precio_sugerido"] == 2500000.0


def test_estimado_no_se_infla_con_otros_porcentajes(client, cleaner):
    """Aunque el renglón de la cotización cambie ganancia/impuesto, el estimado
    se mantiene: es el precio acordado, no un costo a margear."""
    prod = _crear(client, cleaner, precio_venta_base=2500000)
    r = _precio(client, prod["id"], ganancia=55.0, impuesto=19.0)
    assert r["precio_venta"] == 2500000.0


def test_costo_estimado_aplica_margen(client, cleaner):
    """Con COSTO estimado (sin precio de venta), el margen y el impuesto sí
    se calculan: 1.000.000 × 1.07 × 1.40 = 1.498.000."""
    prod = _crear(client, cleaner, precio_costo_base=1000000)
    r = _precio(client, prod["id"])
    assert r["fuente_precio"] == "estimado_sin_estructura"
    assert r["precio_venta"] == 1498000.0


def test_sin_nada_fuente_sin_definir(client, cleaner):
    prod = _crear(client, cleaner)
    r = _precio(client, prod["id"])
    assert r["fuente_precio"] == "sin_definir"
    assert r["precio_venta"] == 0.0


def test_editar_estimado_cambia_el_precio(client, cleaner):
    prod = _crear(client, cleaner, precio_venta_base=2500000)
    assert _precio(client, prod["id"])["precio_venta"] == 2500000.0

    r = client.put(f"/api/v1/producto/{prod['id']}", json={
        "precio_venta_base": 3000000,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert _precio(client, prod["id"])["precio_venta"] == 3000000.0


def test_estructura_de_costos_tiene_prioridad_sobre_estimado(client, cleaner):
    """Cuando el producto YA tiene estructura (receta), el precio se recalcula
    con ella y la fuente deja de ser 'estimado'."""
    from conftest import crear_material, crear_receta
    prod = _crear(client, cleaner, precio_venta_base=2500000)
    mat = crear_material(client, cleaner, costo_base=1000.0)
    crear_receta(client, cleaner, prod["id"], mat["id"], 10, tipo_escala="FIJO")
    r = _precio(client, prod["id"])
    assert r["fuente_precio"] == "estructura_de_costos"
    # 10 und × $1.000 = 10.000 de material → precio con margen (NOT estimado)
    assert r["precio_venta"] < 2500000.0
