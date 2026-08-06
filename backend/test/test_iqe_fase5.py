#!/usr/bin/env python3
"""
Pruebas de la Fase 5 del Cotizador Inteligente (IQE): IA ingeniero de producción.

Cubre el flujo de preguntas dinámicas y la aplicación de respuestas al motor
de costos real:

  - generate-structure con nuevo_alto / nuevo_fondo / respuestas /
    dimensiones_referencia
  - _reescalar_cantidad_ia: reescala cantidades IA hacia las medidas reales
  - _escalar_cantidad con escala VOLUMEN
  - _aplicar_respuestas: material, espesor, acabado, secciones sí/no,
    procesos de fabricación y estructura reforzada

Ejecutar (requiere PostgreSQL activo):
  cd backend && source venv/bin/activate
  python -m pytest test/test_iqe_fase5.py -v
"""
import os
import sys
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.db.session import session_local
from app.modules.productos.model import Material, MaterialSinonimo
from app.modules.quotes.structure_builder import (
    LineaCosto,
    SeccionCosto,
    _aplicar_respuestas,
    _escalar_cantidad,
    _reescalar_cantidad_ia,
    build_cost_structure,
)
from app.modules.quotes.vision_provider import FurnitureAttributes

import conftest as cf


def _crear_material_db(db, cleaner, nombre, costo_base=10000.0, unidad_medida_id=2) -> Material:
    """Crea un Material directamente en BD (para tests que no usan el client)."""
    mat = Material(
        nombre=nombre,
        unidad_medida_id=unidad_medida_id,
        costo_base=costo_base,
        activo=True,
    )
    db.add(mat)
    db.flush()
    cleaner.registrar("material", mat.id)
    return mat


# ---------------------------------------------------------------------------
# Unit: _reescalar_cantidad_ia
# ---------------------------------------------------------------------------

class TestReescalarCantidadIa:
    def test_piezas_no_escalan(self):
        assert _reescalar_cantidad_ia(2.0, "UN",
                                       {"ancho": 1.6, "largo": 1.9},
                                       1.6, 1.9, None) == 2.0

    def test_lineal_escala_por_largo(self):
        r = _reescalar_cantidad_ia(3.0, "M",
                                   {"ancho": 1.6, "largo": 1.9},
                                   1.6, 2.0, None)
        assert r == pytest.approx(3.0 * 2.0 / 1.9, rel=1e-3)

    def test_area_escala_por_superficie(self):
        r = _reescalar_cantidad_ia(2.5, "M2",
                                   {"ancho": 1.6, "largo": 1.9},
                                   1.8, 1.9, None)
        assert r == pytest.approx(2.5 * (1.8 * 1.9) / (1.6 * 1.9), rel=1e-3)

    def test_volumen_escala_por_alto(self):
        r = _reescalar_cantidad_ia(1.0, "M3",
                                   {"ancho": 1.6, "largo": 1.9, "alto": 0.5},
                                   1.6, 1.9, 0.6)
        assert r == pytest.approx(1.0 * 0.6 / 0.5, rel=1e-3)

    def test_sin_dimensiones_referencia_no_escala(self):
        assert _reescalar_cantidad_ia(3.0, "M", None, 1.6, 1.9, None) == 3.0

    def test_sin_dimensiones_nuevas_no_escala(self):
        assert _reescalar_cantidad_ia(3.0, "M",
                                      {"ancho": 1.6, "largo": 1.9},
                                      None, None, None) == 3.0


# ---------------------------------------------------------------------------
# Unit: _escalar_cantidad con VOLUMEN
# ---------------------------------------------------------------------------

def _pm(tipo_escala, cantidad_base):
    return SimpleNamespace(
        tipo_escala=tipo_escala,
        cantidad_base=Decimal(str(cantidad_base)),
        distancia_pauta_cm=None,
        tornillos_por_pieza=None,
        rangos=[],
    )


class TestEscalarCantidadVolumen:
    def test_volumen_escala_con_alto(self):
        pm = _pm("VOLUMEN", 10)
        r = _escalar_cantidad(
            pm,
            Decimal("1.60"), Decimal("1.90"),
            Decimal("1.60"), Decimal("1.90"),
            Decimal("0.50"), Decimal("0.60"),
        )
        assert r == Decimal("12").quantize(Decimal("0.0001"))

    def test_volumen_sin_alto_trata_como_area(self):
        pm = _pm("VOLUMEN", 10)
        r = _escalar_cantidad(
            pm,
            Decimal("1.60"), Decimal("1.90"),
            Decimal("1.80"), Decimal("1.90"),
            None, None,
        )
        assert r == Decimal("11.25").quantize(Decimal("0.0001"))

    def test_fijo_no_escala(self):
        pm = _pm("FIJO", 4)
        r = _escalar_cantidad(
            pm, Decimal("1.60"), Decimal("1.90"),
            Decimal("1.80"), Decimal("2.00"),
        )
        assert r == Decimal("4")


# ---------------------------------------------------------------------------
# Unit: _aplicar_respuestas
# ---------------------------------------------------------------------------

def _secciones_con_lineas():
    eb = SeccionCosto("EBANISTERÍA")
    eb.items.append(LineaCosto("MDF RH 15MM", 2.0, "M2", 50000.0, razon="Propuesto por IA"))
    pintura = SeccionCosto("PINTURA")
    pintura.items.append(LineaCosto("PINTURA", 1.0, "UN", 20000.0, razon="Propuesto por IA"))
    tap = SeccionCosto("TAPICERÍA")
    tap.items.append(LineaCosto("ESPUMA", 1.0, "UN", 15000.0, razon="Propuesto por IA"))
    return {"EBANISTERÍA": eb, "PINTURA": pintura, "TAPICERÍA": tap}


def _attrs():
    return FurnitureAttributes(
        tipo_mueble="cama",
        nivel_confianza=0.85,
        observaciones="",
        tipo_patas="madera",
        estilo_general="moderno",
        tiene_tapiceria=True,
        tiene_luces=False,
        familia_probable="cama",
    )


class TestAplicarRespuestas:
    def test_material_principal_cambia_precio(self, db, cleaner):
        import uuid
        nombre = f"TESTMELAMINA {uuid.uuid4().hex[:6]}"
        _crear_material_db(db, cleaner, nombre, costo_base=80000.0)
        respuestas = {"material_principal": nombre}
        secs = _secciones_con_lineas()
        _aplicar_respuestas(db, secs, respuestas, _attrs())

        mdf = secs["EBANISTERÍA"].items[0]
        assert nombre.lower() in mdf.nombre.lower()
        assert mdf.precio_pendiente is False
        assert mdf.costo_unitario == 80000.0

    def test_espesor_tablero_actualiza_nombre(self, db):
        respuestas = {"espesor_tablero": "18"}
        secs = _secciones_con_lineas()
        _aplicar_respuestas(db, secs, respuestas, _attrs())
        assert "18MM" in secs["EBANISTERÍA"].items[0].nombre.upper()

    def test_acabado_agrega_linea_si_no_existe(self, db, cleaner):
        _crear_material_db(db, cleaner, "LACA", costo_base=30000.0)
        respuestas = {"acabado": "laca"}
        secs = _secciones_con_lineas()
        del secs["PINTURA"]
        _aplicar_respuestas(db, secs, respuestas, _attrs())
        assert "PINTURA" in secs
        assert any("laca" in i.nombre.lower() for i in secs["PINTURA"].items)

    def test_seccion_no_desactiva_lineas(self, db):
        respuestas = {"tiene_tapizado": "no"}
        secs = _secciones_con_lineas()
        _aplicar_respuestas(db, secs, respuestas, _attrs())
        assert secs["TAPICERÍA"].items[0].activo is False

    def test_seccion_si_garantiza_linea(self, db, cleaner):
        _crear_material_db(db, cleaner, "TIRA LED", costo_base=5000.0)
        respuestas = {"tiene_led": "si"}
        secs = _secciones_con_lineas()
        _aplicar_respuestas(db, secs, respuestas, _attrs())
        assert "ILUMINACIÓN" in secs
        assert any("led" in i.nombre.lower() for i in secs["ILUMINACIÓN"].items)

    def test_procesos_agregan_mano_de_obra(self, db):
        respuestas = {"piezas_cnc": 4}
        secs = _secciones_con_lineas()
        _aplicar_respuestas(db, secs, respuestas, _attrs())
        assert any("corte cnc" in i.nombre.lower() for i in secs["EBANISTERÍA"].items)

    def test_estructura_reforzada_incrementa_cantidades(self, db):
        respuestas = {"estructura_reforzada": "si"}
        secs = _secciones_con_lineas()
        _aplicar_respuestas(db, secs, respuestas, _attrs())
        assert secs["EBANISTERÍA"].items[0].cantidad == pytest.approx(2.0 * 1.15)

    def test_respuestas_fuera_de_vocabulario_se_ignoran(self, db):
        respuestas = {"ciudad_del_cliente": "Bogotá", "descuento": 50}
        secs = _secciones_con_lineas()
        _aplicar_respuestas(db, secs, respuestas, _attrs())
        assert len(secs["EBANISTERÍA"].items) == 1


# ---------------------------------------------------------------------------
# Integración: generate-structure con las nuevas variables
# ---------------------------------------------------------------------------

def test_generate_structure_con_respuestas_y_volumen(client, cleaner):
    """El endpoint acepta alto/fondo/respuestas/dimensiones_referencia y las
    aplica al motor de costos real."""
    from conftest import ADMIN_HEADERS

    mat_mdf = cf.crear_material(client, cleaner, nombre="MDF RH 15MM", costo_base=40000.0, unidad_medida_id=3)
    mat_tela = cf.crear_material(client, cleaner, nombre="TELA", costo_base=30000.0, unidad_medida_id=2)

    estructura_ia = [
        {
            "seccion": "EBANISTERÍA",
            "items": [
                {
                    "nombre_material": "MDF RH 15MM",
                    "cantidad_sugerida": 2.5,
                    "unidad": "m2",
                    "razon": "Estructura principal",
                    "es_opcional": False,
                }
            ],
        },
        {
            "seccion": "TAPICERÍA",
            "items": [
                {
                    "nombre_material": "TELA",
                    "cantidad_sugerida": 3.0,
                    "unidad": "m",
                    "razon": "Cabecera tapizada",
                    "es_opcional": False,
                }
            ],
        },
    ]

    r = client.post("/api/v1/intelligent-quotation/generate-structure", headers=ADMIN_HEADERS, json={
        "tipo_mueble": "cama",
        "atributos": {
            "tiene_tapiceria": True,
            "tiene_luces": False,
            "tipo_patas": "madera",
            "estilo_general": "moderno",
        },
        "estructura_propuesta": estructura_ia,
        "nuevo_ancho": 1.80,
        "nuevo_largo": 1.90,
        "nuevo_alto": 0.60,
        "respuestas": {
            "material_principal": "MDF RH 15MM",
            "espesor_tablero": "18",
            "tiene_tapizado": "si",
            "tiene_led": "no",
        },
        "dimensiones_referencia": {"ancho": 1.60, "largo": 1.90, "alto": 0.50},
        "ganancia_porcentaje": 40.0,
        "iva_porcentaje": 0.0,
        "pct_mano_obra": 15.0,
        "pct_gastos": 10.0,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert "secciones" in data and len(data["secciones"]) > 0
    assert "resumen" in data
    assert data["resumen"]["precio_con_iva"] >= 0

    # El MDF escaló por superficie (1.80×1.90 / 1.60×1.90 = 1.125)
    seccion_eb = next(s for s in data["secciones"] if s["seccion"] == "EBANISTERÍA")
    mdf = next(i for i in seccion_eb["items"] if "MDF" in i["nombre"].upper())
    assert mdf["cantidad"] == pytest.approx(2.5 * (1.8 * 1.9) / (1.6 * 1.9), rel=0.01)

    # El espesor confirmado se refleja en el nombre
    assert "18" in mdf["nombre"]


def test_generate_structure_sin_historicos_reescala_cantidades_ia(client, cleaner):
    """Sin receta histórica, las cantidades IA (con unidad escalable) se
    reescalan a las medidas reales en vez de usarse crudas."""
    from conftest import ADMIN_HEADERS

    cf.crear_material(client, cleaner, nombre="ESPUMA", costo_base=10000.0, unidad_medida_id=2)

    estructura_ia = [
        {
            "seccion": "TAPICERÍA",
            "items": [
                {
                    "nombre_material": "ESPUMA",
                    "cantidad_sugerida": 2.0,
                    "unidad": "m2",
                    "razon": "Relleno",
                    "es_opcional": False,
                }
            ],
        },
    ]

    r = client.post("/api/v1/intelligent-quotation/generate-structure", headers=ADMIN_HEADERS, json={
        "tipo_mueble": "cama",
        "atributos": {
            "tiene_tapiceria": True,
            "tiene_luces": False,
            "tipo_patas": "madera",
            "estilo_general": "moderno",
        },
        "estructura_propuesta": estructura_ia,
        "nuevo_ancho": 1.80,
        "nuevo_largo": 1.90,
        "respuestas": {"tiene_tapizado": "si"},
        "dimensiones_referencia": {"ancho": 1.60, "largo": 1.90},
        "ganancia_porcentaje": 40.0,
        "iva_porcentaje": 0.0,
        "pct_mano_obra": 15.0,
        "pct_gastos": 10.0,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    seccion = next(s for s in data["secciones"] if s["seccion"] == "TAPICERÍA")
    espuma = next(i for i in seccion["items"] if "ESPUMA" in i["nombre"].upper())
    assert espuma["cantidad"] == pytest.approx(2.0 * (1.8 * 1.9) / (1.6 * 1.9), rel=0.01)
