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
from sqlalchemy import text

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
from app.modules.quotes.atributos import FurnitureAttributes

import conftest as cf


def _crear_material_db(db, cleaner, nombre, costo_base=10000.0, unidad_medida_id=2) -> Material:
    """Crea un Material directamente en BD (para tests que no usan el client).

    El nombre NO puede empezar por "test": el matcher del cotizador excluye
    los placeholders (structure_builder._es_placeholder_matcheo) para que los
    datos de prueba nunca se cuelen en una cotización real."""
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
        # Sin prefijo "test": el matcher excluye placeholders de prueba.
        nombre = f"IQE MELAMINA {uuid.uuid4().hex[:6]}"
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
# Integración: import-structure (API actual del Cotizador Manual)
# ---------------------------------------------------------------------------
# Flujo real: contexto-exportar → import-structure → recalculate-structure →
# finalize-structure. La IA SOLO propone materiales/cantidades; el ERP matchea
# contra el inventario y calcula costos con precios vigentes.
#
# Regla del matcher: los materiales cuyo nombre empieza por "test" se excluyen
# del matcheo (structure_builder._es_placeholder_matcheo). Por eso estos tests
# crean materiales con prefijo "IQE" + uuid: únicos y matchables.

def _estructura_ia(secciones_items) -> list[dict]:
    """Convierte {SECCION: [items...]} al JSON que espera import-structure."""
    return [
        {"seccion": sec, "items": items}
        for sec, items in secciones_items.items()
    ]


def _item_ia(nombre, cantidad, unidad="m2", razon="Propuesto por IA") -> dict:
    return {
        "nombre_material": nombre,
        "cantidad_sugerida": cantidad,
        "unidad": unidad,
        "razon": razon,
        "es_opcional": False,
    }


_PAYLOAD_BASE = {
    "tipo_mueble": "cama",
    "nuevo_ancho": 1.80,
    "nuevo_largo": 1.90,
    "nuevo_alto": 0.60,
    "dimensiones_referencia": {"ancho": 1.60, "largo": 1.90, "alto": 0.50},
    "ganancia_porcentaje": 40.0,
    "iva_porcentaje": 0.0,
    "impuesto_porcentaje": 7.0,
    "pct_mano_obra": 15.0,
    "pct_gastos": 10.0,
}


def test_import_structure_con_receta_base_escala_por_area(client, cleaner):
    """Con producto base + receta AREA, la cantidad se escala a las medidas
    nuevas (motor paramétrico) y el precio sale del inventario."""
    import uuid
    from conftest import ADMIN_HEADERS

    sufijo = uuid.uuid4().hex[:6]
    nombre_mat = f"IQE TABLERO MDF {sufijo}"
    mat = cf.crear_material(client, cleaner, nombre=nombre_mat,
                            costo_base=40000.0, unidad_medida_id=2)
    # Producto base con medidas reales (largo ≠ 1.90 → escala habilitada).
    r = client.post("/api/v1/producto/", json={
        "nombre": f"IQE Cama {sufijo}",
        "tipo_producto_id": 1,
        "es_reventa": False,
        "ancho_base": 1.60,
        "largo_base": 2.00,
        "costo_base": 300000.0,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    producto = r.json()
    cleaner.registrar("producto", producto["id"])
    cf.crear_receta(client, cleaner, producto["id"], mat["id"],
                    cantidad_base=2.5, tipo_escala="AREA", seccion="EBANISTERIA")

    payload = {**_PAYLOAD_BASE, "producto_base_id": producto["id"],
               "estructura_propuesta": _estructura_ia({
                   "EBANISTERÍA": [_item_ia(nombre_mat, 1.0, "m2", "Estructura principal")],
               })}
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["producto_base_id"] == producto["id"]
    assert data["score_similitud"] == 1.0

    seccion_eb = next(s for s in data["secciones"] if s["seccion"] == "EBANISTERÍA")
    linea = next(i for i in seccion_eb["items"] if nombre_mat.upper() in i["nombre"].upper())
    # Escala AREA: 2.5 × (1.80×1.90) / (1.60×2.00) = 2.5 × 1.06875 = 2.6719
    assert linea["cantidad"] == pytest.approx(2.5 * (1.8 * 1.9) / (1.6 * 2.0), rel=0.01)
    # Precio vigente del inventario, no el sugerido por la IA.
    assert linea["material_id"] == mat["id"]
    assert linea["costo_unitario"] == 40000.0
    assert linea["precio_pendiente"] is False
    assert linea["confianza_cantidad"] == "alta"
    assert data["resumen"]["precio_con_iva"] >= 0


def test_import_structure_sin_receta_matchea_inventario(client, cleaner):
    """Sin receta histórica, la estructura IA se matchea contra el inventario
    y los totales son consistentes con las líneas (precios vigentes)."""
    import uuid
    from conftest import ADMIN_HEADERS

    sufijo = uuid.uuid4().hex[:6]
    nombre_esp = f"IQE ESPUMA {sufijo}"
    nombre_tela = f"IQE TELA {sufijo}"
    mat_esp = cf.crear_material(client, cleaner, nombre=nombre_esp,
                                costo_base=10000.0, unidad_medida_id=2)
    mat_tela = cf.crear_material(client, cleaner, nombre=nombre_tela,
                                 costo_base=30000.0, unidad_medida_id=2)

    payload = {**_PAYLOAD_BASE, "producto_base_id": None, "tipo_mueble": "otro",
               "estructura_propuesta": _estructura_ia({
                   "TAPICERÍA": [
                       _item_ia(nombre_esp, 2.0, "m2", "Relleno"),
                       _item_ia(nombre_tela, 3.0, "m", "Cabecera tapizada"),
                   ],
               })}
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()

    nombres = {f"IQE ESPUMA {sufijo}".upper(): mat_esp["id"],
               f"IQE TELA {sufijo}".upper(): mat_tela["id"]}
    for seccion in data["secciones"]:
        for linea in seccion["items"]:
            if linea["nombre"].upper() in nombres:
                # Precio vigente del inventario (nuestro material exacto).
                assert linea["material_id"] == nombres[linea["nombre"].upper()]
                assert linea["costo_unitario"] > 0
                assert linea["precio_pendiente"] is False
                assert linea["cantidad"] > 0

    # Consistencia contable: costo_materiales = Σ cantidad × costo_unitario.
    esperado = round(sum(
        l["cantidad"] * l["costo_unitario"]
        for s in data["secciones"] for l in s["items"] if l["activo"]
    ), 2)
    assert data["resumen"]["costo_materiales"] == pytest.approx(esperado, abs=0.01)
    assert data["resumen"]["costo_produccion"] > 0


def test_recalculate_structure_refresca_totales(client, cleaner):
    """Tras editar cantidades, recalculate-structure recalcula subtotales y
    desglose; los precios siguen viniendo del inventario (material_id)."""
    import uuid
    from conftest import ADMIN_HEADERS

    sufijo = uuid.uuid4().hex[:6]
    nombre_mat = f"IQE QUIMICO {sufijo}"
    mat = cf.crear_material(client, cleaner, nombre=nombre_mat,
                            costo_base=20000.0, unidad_medida_id=1)
    # Producto base propio → la línea es 100% nuestra (sin matcheo histórico).
    r = client.post("/api/v1/producto/", json={
        "nombre": f"IQE Base {sufijo}",
        "tipo_producto_id": 1,
        "es_reventa": False,
        "ancho_base": 1.60,
        "largo_base": 2.00,
        "costo_base": 100000.0,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    producto = r.json()
    cleaner.registrar("producto", producto["id"])
    cf.crear_receta(client, cleaner, producto["id"], mat["id"],
                    cantidad_base=1.0, tipo_escala="FIJO", seccion="PINTURA")

    payload = {**_PAYLOAD_BASE, "producto_base_id": producto["id"],
               "estructura_propuesta": _estructura_ia({
                   "PINTURA": [_item_ia(nombre_mat, 1.0, "UN", "Acabado")],
               })}
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    linea = next(l for s in data["secciones"] for l in s["items"]
                 if l["nombre"].upper() == nombre_mat.upper())
    assert linea["material_id"] == mat["id"]
    costo_linea = linea["cantidad"] * linea["costo_unitario"]
    costo_materiales_1 = data["resumen"]["costo_materiales"]

    # El vendedor duplica la cantidad.
    linea_editada = {**linea, "cantidad": linea["cantidad"] * 2}
    r = client.post("/api/v1/intelligent-quotation/recalculate-structure",
                    json={
                        "secciones": [{"seccion": "PINTURA", "items": [linea_editada], "subtotal": 0}],
                        **_PAYLOAD_BASE,
                    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    recalc = r.json()
    assert recalc["resumen"]["costo_materiales"] == pytest.approx(
        costo_materiales_1 + costo_linea, abs=0.01
    )
    # Desglose: costo_produccion = materiales × (1 + 15% + 10%)
    assert recalc["resumen"]["costo_produccion"] == pytest.approx(
        recalc["resumen"]["costo_materiales"] * 1.25, abs=0.01
    )
    # Precio final con impuesto 7% y ganancia 40%.
    assert recalc["resumen"]["precio_sin_iva"] == pytest.approx(
        recalc["resumen"]["base_con_impuestos"] * 1.4, abs=0.01
    )


def test_finalize_structure_guarda_cotizacion(client, cleaner, db):
    """Cierra el flujo: import-structure → finalize-structure como cotización
    con su estructura de costos (antes: producto_id 'or 1' reventaba si el
    producto 1 no existía, y el GET de la cotización fallaba al serializar)."""
    import uuid
    from conftest import ADMIN_HEADERS, crear_cliente

    sufijo = uuid.uuid4().hex[:6]
    nombre_mat = f"IQE MADERA PINO {sufijo}"
    mat = cf.crear_material(client, cleaner, nombre=nombre_mat,
                            costo_base=5000.0, unidad_medida_id=2)
    # Producto base propio: evita que el motor fusione recetas históricas
    # reales de la BD y mantiene el test determinista.
    r = client.post("/api/v1/producto/", json={
        "nombre": f"IQE Cama Base {sufijo}",
        "tipo_producto_id": 1,
        "es_reventa": False,
        "ancho_base": 1.60,
        "largo_base": 2.00,
        "costo_base": 100000.0,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    producto = r.json()
    cleaner.registrar("producto", producto["id"])
    cf.crear_receta(client, cleaner, producto["id"], mat["id"],
                    cantidad_base=10.0, tipo_escala="FIJO", seccion="EBANISTERIA")
    cliente = crear_cliente(client, cleaner)

    payload = {**_PAYLOAD_BASE, "producto_base_id": producto["id"],
               "estructura_propuesta": _estructura_ia({
                   "EBANISTERÍA": [_item_ia(nombre_mat, 10.0, "m", "Estructura")],
               })}
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["score_similitud"] == 1.0
    secciones = [{"seccion": s["seccion"], "items": s["items"], "subtotal": s["subtotal"]}
                 for s in data["secciones"]]

    r = client.post("/api/v1/intelligent-quotation/finalize-structure", json={
        "guardar_como": "cotizacion",
        "cliente_id": cliente["id"],
        "producto_base_id": producto["id"],
        "secciones": secciones,
        "nuevo_ancho": 1.80,
        "nuevo_largo": 1.90,
        "nuevo_alto": 0.60,
        **_PAYLOAD_BASE,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    final = r.json()
    assert final["cotizacion_id"] > 0, final
    assert final["total_estimado"] > 0
    cleaner.registrar("cotizacion", final["cotizacion_id"])

    # La cotización guardada tiene el detalle con la estructura de costos.
    det = client.get(f"/api/v1/cotizacion/{final['cotizacion_id']}", headers=ADMIN_HEADERS)
    assert det.status_code == 200, det.text
    cot = det.json()
    assert len(cot["detalles"]) == 1
    d = cot["detalles"][0]
    cleaner.registrar("detalle_cotizacion", d["id"])
    assert d["costo_materiales"] == pytest.approx(
        data["resumen"]["costo_materiales"], abs=0.01
    )
    # Líneas de materiales de la estructura (cotizacion_detalle_material).
    rows = db.execute(text(
        "SELECT id FROM cotizacion_detalle_material WHERE detalle_cotizacion_id = :did"
    ), {"did": d["id"]}).fetchall()
    assert len(rows) == 1
    cleaner.registrar_muchos("cotizacion_detalle_material", [r[0] for r in rows])
    print(f"[IQE finalize] cotización #{final['cotizacion_id']} con estructura "
          f"({d['costo_materiales']} COP materiales)")


def test_import_structure_vacio_devuelve_vacio(client, cleaner):
    """Sin estructura pegada no se arrastra receta histórica: respuesta vacía."""
    from conftest import ADMIN_HEADERS

    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={**_PAYLOAD_BASE, "estructura_propuesta": []},
                    headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["secciones"] == []
    assert data["resumen"]["costo_materiales"] == 0.0
    assert data["resumen"]["precio_con_iva"] == 0.0
