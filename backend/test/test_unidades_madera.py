"""
test_unidades_madera.py
=======================
Captura flexible de madera (production/unidades.py):

  1. Fórmula de la casa por pieza: (L×A×E) × piezas ÷ 10000 = m³ a descontar.
  2. Captura lineal en cm → metros (1520 cm = 15.20 m) antes de descontar.
  3. Validaciones: pieza solo en m³, toggle solo en longitud, medidas completas.
  4. Compatibilidad legacy: sin unidad_captura la cantidad pasa tal cual.
  5. Base en cm (material definido en cm): conversión inversa.
  6. Trazabilidad (nota_captura).

Ejecutar:  pytest test/test_unidades_madera.py -v
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.modules.production.unidades import (
    resolver_cantidad_consumo,
    nota_captura,
    dimensionalidad,
    VOLUMEN,
    AREA,
    LONGITUD,
    OTRA,
)


def material(abreviatura: str):
    """Material falso: solo interesa la abreviatura de su unidad."""
    return SimpleNamespace(unidad_medida=SimpleNamespace(abreviatura=abreviatura))


# ============================================================================
# 1. Fórmula de la casa (pieza volumétrica)
# ============================================================================

def test_pieza_20x4x2_descuenta_0016_m3():
    # El ejemplo verificado en el taller: 20×4×2 → 160 → ÷10000 = 0.016 m³.
    # La columna es Numeric(12,4): NO se pierde stock redondeando.
    assert float(resolver_cantidad_consumo(material("m³"), 1, None, 20, 4, 2)) == 0.016


def test_pieza_multiplica_por_numero_de_piezas():
    # cantidad = N.º de piezas: (20×4×2) × 2 ÷ 10000 = 0.032 m³
    assert float(resolver_cantidad_consumo(material("m³"), 2, None, 20, 4, 2)) == 0.032
    # ×10 = 0.16 exacto
    assert float(resolver_cantidad_consumo(material("m³"), 10, None, 20, 4, 2)) == 0.16


def test_pieza_redondea_a_4_decimales_como_la_columna():
    # 20.5×4×2 × 1 ÷ 10000 = 0.0164 → la BD es Numeric(12,4) → 0.0164 exacto
    assert float(resolver_cantidad_consumo(material("m³"), 1, None, 20.5, 4, 2)) == 0.0164
    # 0.01555 debe redondear hacia arriba (ROUND_HALF_UP, 4 decimales) → 0.0156
    assert float(resolver_cantidad_consumo(material("m³"), 10, None, 15.55, 1, 1)) == 0.0156
    # 0.01549 redondea hacia abajo → 0.0155
    assert float(resolver_cantidad_consumo(material("m³"), 10, None, 15.49, 1, 1)) == 0.0155


def test_pieza_acepta_varias_notaciones_de_m3():
    for abrev in ("m³", "m3", "M³", "mt3"):
        assert float(resolver_cantidad_consumo(material(abrev), 1, None, 20, 4, 2)) == 0.016


# ============================================================================
# 2. Captura lineal cm → m
# ============================================================================

def test_captura_cm_convierte_a_metros_antes_de_descontar():
    # 1520 cm = 15.20 m (el caso que pidió el dueño)
    assert float(resolver_cantidad_consumo(material("m"), 1520, "CM")) == 15.20


def test_captura_en_metros_pasa_igual():
    assert float(resolver_cantidad_consumo(material("m"), 15.2, "M")) == 15.20


def test_material_lineal_acepta_varias_notaciones():
    for abrev in ("m", "M", "mts", "MT"):
        assert float(resolver_cantidad_consumo(material(abrev), 100, "CM")) == 1.00


# ============================================================================
# 3. Validaciones
# ============================================================================

def test_pieza_no_aplica_a_material_lineal():
    with pytest.raises(ValueError, match="m³"):
        resolver_cantidad_consumo(material("m"), 1, None, 20, 4, 2)


def test_pieza_exige_las_tres_medidas():
    with pytest.raises(ValueError, match="espesor"):
        resolver_cantidad_consumo(material("m³"), 1, None, 20, 4, None)


def test_toggle_cm_no_aplica_a_m2():
    with pytest.raises(ValueError, match="longitud"):
        resolver_cantidad_consumo(material("m²"), 100, "CM")


def test_unidad_captura_desconocida_rechazada():
    with pytest.raises(ValueError, match="no soportada"):
        resolver_cantidad_consumo(material("m"), 100, "pulgadas")


# ============================================================================
# 4. Compatibilidad legacy (sin captura explícita)
# ============================================================================

def test_sin_unidad_captura_la_cantidad_pasa_tal_cual():
    # Comportamiento de siempre: und, kg, m³ directo...
    assert float(resolver_cantidad_consumo(material("und"), 5)) == 5.00
    assert float(resolver_cantidad_consumo(material("m³"), 0.16)) == 0.16
    assert float(resolver_cantidad_consumo(material("m"), 3.5)) == 3.50


def test_dimensionalidad_reconoce_unidades():
    assert dimensionalidad("m³") == VOLUMEN
    assert dimensionalidad("M2") == AREA
    assert dimensionalidad("mts") == LONGITUD
    assert dimensionalidad("und") == OTRA
    assert dimensionalidad(None) == OTRA


# ============================================================================
# 5. Material definido directamente en cm
# ============================================================================

def test_material_en_cm_y_captura_cm_sin_conversion():
    assert float(resolver_cantidad_consumo(material("cm"), 1520, "CM")) == 1520.00


def test_material_en_cm_y_captura_m_convierte_a_cm():
    assert float(resolver_cantidad_consumo(material("cm"), 15.2, "M")) == 1520.00


# ============================================================================
# 6. Trazabilidad
# ============================================================================

def test_nota_captura_pieza():
    assert nota_captura(2, None, 20, 4, 2) == "pieza 20×4×2 × 2"


def test_nota_captura_cm_y_ninguna():
    assert nota_captura(1520, "CM") == "digitado en CM"
    assert nota_captura(5) is None
