# -*- coding: utf-8 -*-
"""Tests unitarios del reporte de deuda por categoría (sin HTTP/BD).

Cubren la inferencia de categoría por texto y la detección de posibles
clientes duplicados.
"""
from app.modules.sales.service import (
    _categoria_por_texto,
    _grupos_duplicados,
)


def test_categoria_tableros_y_madera():
    assert _categoria_por_texto("LAMINAS DE MDF DE 9MM") == "Tableros y MDF"
    assert _categoria_por_texto("Lámina de MDF de 15 cortada a la mitad") == "Tableros y MDF"
    assert _categoria_por_texto("2.115 CMTS de Madera Apamate") == "Madera"
    assert _categoria_por_texto("Madera aserrada") == "Madera"


def test_categoria_electrodomesticos_colchones_muebles_servicios():
    assert _categoria_por_texto("NEVERA HACEB DE 254 LITROS") == "Electrodomésticos"
    assert _categoria_por_texto("AIRE SPLIT INVERTER 12.000 BTU 220") == "Electrodomésticos"
    assert _categoria_por_texto("TANQUE CONGELADOR DE 142 LTS") == "Electrodomésticos"
    assert _categoria_por_texto("COLCHON DALLAS 1 PILLON DE 1,60") == "Colchones"
    assert _categoria_por_texto("CAMA MODELO NUBE MATRIMONIAL") == "Muebles a medida"
    assert _categoria_por_texto("Sofá de 2 puestos tapizar en tela Dorian") == "Muebles a medida"
    assert _categoria_por_texto("FLETE") == "Servicios"


def test_categoria_sin_categoria():
    assert _categoria_por_texto("ALGO RARO SIN PALABRAS CLAVE") == "Sin categoría"


def test_grupos_duplicados_normaliza_y_agrupa():
    clientes = [
        {"cliente_id": 1, "cliente_nombre": "CUPERTINO BENITEZ", "saldo": 100.0},
        {"cliente_id": 2, "cliente_nombre": "Cupertino Benitez", "saldo": 50.0},
        {"cliente_id": 3, "cliente_nombre": "Otra Persona Distinta", "saldo": 10.0},
    ]
    grupos = _grupos_duplicados(clientes)
    assert len(grupos) == 1
    assert {c["cliente_id"] for c in grupos[0]["clientes"]} == {1, 2}
    assert grupos[0]["saldo_total"] == 150.0


def test_grupos_duplicados_evita_falsos_por_longitud():
    # 'cupertino' es demasiado corto frente al nombre largo → no se agrupa.
    clientes = [
        {"cliente_id": 1, "cliente_nombre": "Cupertino", "saldo": 100.0},
        {"cliente_id": 2, "cliente_nombre": "Cupertino Benitez de la Torre", "saldo": 50.0},
    ]
    assert _grupos_duplicados(clientes) == []
