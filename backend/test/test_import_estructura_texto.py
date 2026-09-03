"""
test_import_estructura_texto.py
===============================
Regresión del importador de estructura de costos pegado desde Excel
(POST /producto/importar-estructura-texto).

Bug histórico corregido: `dec()` interpretaba la coma como separador DECIMAL,
dividiendo todo por 1000 ("163,800.00" → 163.8; TOTAL 2,051,090 → $2 y una
desviación absurda de 99904%). Ahora soporta US (163,800.00) y latino
(163.800,00) con la convención colombiana para un solo separador ("3.200").

La fixture es el pegado REAL de "CAMA NUBE" (18/5/2026) con sus totales
declarados: los totales calculados deben cuadrar a centavos.

Ejecutar:  pytest test/test_import_estructura_texto.py -v
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from conftest import ADMIN_HEADERS

# ── Pegado REAL del Excel (tab separado, 2 bloques de producto) ─────────────
EXCEL_CAMA_NUBE = (
    "NOMBRE DEL PRODUCTO:  \t\t18/5/2026 CAMA NUBE\t\t\t\n"
    "MATERIA PRIMA\t\tUNIDAD DE MEDIDA\t\tV/UNIT\tPRECIO TOTAL\n"
    "MADERA\t1170\tCMS\t\t140.00\t163,800.00\n"
    "LAM MFF 9\"\t\tLAMINA\t\t140,000.00\t0.00\n"
    "TABLA DE 30X30X2,5\t1\t\t\t50,000.00\t50,000.00\n"
    "LAM MDF 15\t0.13\tDE 80*50\t\t220,000.00\t28,600.00\n"
    "LAM MDF 2.7\t1\tLAMINA\t\t65,000.00\t65,000.00\n"
    "COLBON\t3\tlitros\t\t13,000.00\t39,000.00\n"
    "GANCHOS\t1\tPAR\t\t20,000.00\t20,000.00\n"
    "GRAPAS\t0.5\tCAJAS\t\t12,000.00\t6,000.00\n"
    "CLAVILLOS\t10\tTIRA\t\t1,000.00\t10,000.00\n"
    "TORNILLOS DE 2\"\t200\tUnidad\t\t100.00\t20,000.00\n"
    "FABRICACION 3240.000 *5%\t\t\t\t\t324,000.00\n"
    "MATERIA PRIMA \t\t\t\t\t726,400.00\n"
    "gastos de Ebanisteria e 10%\t\t\tgastos\t\t72,640.00\n"
    "TOTAL GASTOS EBANISTERIA CRUDO\t\t\t\t\t799,040.00\n"
    "SECCION PINTURA\tCAMA\t\t\t\t\n"
    "PREPARADO CAMA\t\tCON EL 5%\t\t31,500.00\t0.00\n"
    "PINTURA CAMA\t\tCON EL 5%\t\t21,000.00\t0.00\n"
    "PREPARADO BURRO\t\tCON EL 5%\t\t9450\t0.00\n"
    "PINTURA BURRO\t\tCON EL 5%\t\t12600\t0.00\n"
    "SELLADOR\t\tPISTOLADAS\t\t18,000.00\t0.00\n"
    "LIJA\t\tunidad\t\t2,000.00\t0.00\n"
    "LIJA 2000\t\tUNIDAD\t\t2,000.00\t0.00\n"
    "COLOR NACARADO\t\tPISTOLADA\t\t23,000.00\t0.00\n"
    "COLOR BLANCO\t\tPISTOLADA \t\t22,000.00\t0.00\n"
    "RESANE \t\tLITRO\t\t10,000.00\t0.00\n"
    "LACA\t\tPISTOLADA\t\t23,000.00\t0.00\n"
    "sub total\t\t\t\t\t0.00\n"
    "Gastos de Pintura 10%\t\t\t\t\t0.00\n"
    "TOTAL GASTOS EN PINTURA\t\t\t\t\t0.00\n"
    "NOMBRE DEL PRODUCTO:  \t\tNOCHEROS EN CRUDO \t\t\t\n"
    "MATERIA PRIMA\tCANTIDAD\tUNIDAD DE MEDIDA\t\tV/UNIT\tPRECIO TOTAL\n"
    "CORREDERAS \t\tUNIDADES \t\t$ 10,000\t$ 0\n"
    "HECHURA\t\tLUIS ALFONSO AL COSTO\t\t$ 250,000\t$ 0\n"
    "\t\t\t\t\t$ 0\n"
    "MATERIA PRIMA \t\t\t\t\t$ 0\n"
    "TOTAL GASTOS EBANISTERIA CRUDO\t\t\t\t\t0.00\n"
    "SECCION PINTURA\tNOCHEROS\t\t\t\t\n"
    "PREPARADO \t\tCON EL 5%\t\t36,750.00\t0.00\n"
    "PINTURA\t\tCON EL 5%\t\t36,750.00\t0.00\n"
    "SELLADOR\t\tPISTOLADAS\t\t18,000.00\t0.00\n"
    "LIJA 400\t\tunidad\t\t2,000.00\t0.00\n"
    "LIJA 120\t\tunidades\t\t2,000.00\t0.00\n"
    "COLOR BLANCO\t\tPISTOLADAS\t\t22,000.00\t0.00\n"
    "COLOR NACARADO\t\tPISTOLADA \t\t23,000.00\t0.00\n"
    "RESANE \t\tLITRO \t\t10,000.00\t0.00\n"
    "LACA\t\tPISTOLADAS\t\t23,000.00\t0.00\n"
    "sub total\t\t\t\t\t0.00\n"
    "Gastos de Pintura 10%\t\t\t\t\t0.00\n"
    "TOTAL GASTOS EN PINTURA\t\t\t\t\t0.00\n"
    "SECCION TERMINACION\t\t\t\t\t\n"
    "DANIEL\t\tMANO DE OBRA\t\t73,500.00\t0.00\n"
    "ESPEJO\t\t50*80\t\t45,000.00\t0.00\n"
    "APAGADOR CAFETERO\t\tunidades\t\t2,000.00\t0.00\n"
    "CABLE\t\tMETROS\t\t1,500.00\t0.00\n"
    "TOMA EXPANDIBLE\t\tunidades\t\t260,000.00\t0.00\n"
    "EMBALADA \t1\tunidades\t\t100,000.00\t100,000.00\n"
    "TOTAL DE  GASTOS DE TERMINACION \t\t\t\t\t100,000.00\n"
    "SECCION TENDIDO\t\t\t\t\t\n"
    "MADERA \t840\tCMS\t\t140.00\t117,600.00\n"
    "lamina de 2.5 mdf\t1\tLAMINA\t\t65,000.00\t65,000.00\n"
    "COLBON\t0.3\tLITRO\t\t14,000.00\t4,200.00\n"
    "CLAVILLO f.50\t3\tTIRAS \t\t1,000.00\t3,000.00\n"
    "PEOPLE\t3.2\tMETROS\t\t4,000.00\t12,800.00\n"
    "grapas \t0.5\tCAJA DE GRAPAS\t\t12,000.00\t6,000.00\n"
    "HECHURA TAPICERIA \t\t\t\t\t0.00\n"
    "HECHURA TENDIDO\t1\t*8%\t\t64,800.00\t64,800.00\n"
    "postura\t1\tPEOPLE\t\t10,500.00\t10,500.00\n"
    "TOTAL GASTOS TENDIDO\t\t\t\t\t283,900.00\n"
    "SECCION TAPICERIA\t\t\t\t\t\n"
    "TELA BRUNA\t12\tMETROS\t\t32,000.00\t384,000.00\n"
    "ESPUMA DE 2  ROSADA\t3\tLAMINAS \t\t48,000.00\t144,000.00\n"
    "ESPUMA DE 1/2 ROSADA\t1\tLAMINAS \t\t30,000.00\t30,000.00\n"
    "CIERRE MAGICO \t6\t\t\t1,000.00\t6,000.00\n"
    "COSTAL\t2.5\tMETRO \t\t3,500.00\t8,750.00\n"
    "CABULLA \t0.5\tUNIDAD \t\t12,000.00\t6,000.00\n"
    "GRAPAS\t0.5\tCAJA\t\t12,000.00\t6,000.00\n"
    "TORNILLOS DE 2  \t24\tUNIDAD  0\t\t100.00\t2,400.00\n"
    "HILO \t0.5\t UNIIDAD \t\t25,000.00\t12,500.00\n"
    "SUPER \t1.5\tLITRO\t\t19,000.00\t28,500.00\n"
    "CARTON\t5\tUNIDAD\t\t6,000.00\t30,000.00\n"
    "hechura\t1\tMANO DE OBRA \t\t210,000.00\t210,000.00\n"
    "TOTAL GASTOS TAPICERIA\t\t\t\t\t868,150.00\n"
    "TOTAL PRODUCCION\t\t\t\t\t2,051,090.00\n"
)


# ============================================================================
# 1. Parser de números `dec()` — los dos formatos y los casos bordes
# ============================================================================

@pytest.mark.parametrize("crudo,esperado", [
    # Formato US (este Excel): coma = miles, punto = decimal
    ("163,800.00", Decimal("163800.00")),
    ("2,051,090.00", Decimal("2051090.00")),
    ("$ 250,000", Decimal("250000")),
    ("140,000.00", Decimal("140000.00")),
    ("$ 0", Decimal("0")),
    # Formato latino: punto = miles, coma = decimal
    ("163.800,00", Decimal("163800.00")),
    ("2.051.090,00", Decimal("2051090.00")),
    ("0,5", Decimal("0.5")),
    # Convención colombiana: UN separador con grupo de 3 → miles (dinero)
    ("3.200", Decimal("3200")),
    ("10,000", Decimal("10000")),
    ("140.000", Decimal("140000")),
    # Decimales normales
    ("140.00", Decimal("140.00")),
    ("0.13", Decimal("0.13")),
    ("3.2", Decimal("3.2")),
    ("9450", Decimal("9450")),
    ("0", Decimal("0")),
    # Parte entera de 4+ dígitos con 3 decimales → decimal (no miles)
    ("3240.000", Decimal("3240.000")),
    # Números embebidos en texto: primer número, sin unir fragmentos
    ("50*80", Decimal("50")),
    ("$ 10,000", Decimal("10000")),
    ("x", None),
    ("", None),
    (None, None),
    (1170, Decimal("1170")),
])
def test_dec_formatos_de_numero(crudo, esperado):
    from app.modules.productos.estructura_import import dec
    assert dec(crudo) == esperado


# ============================================================================
# 2. Parseo completo del pegado real: totales EXACTOS del Excel
# ============================================================================

def _por_nombre(estructura, nombre):
    for sec in estructura["secciones"]:
        if sec["nombre"] == nombre:
            return sec
    pytest.fail(f"No se encontró la sección {nombre}: {[s['nombre'] for s in estructura['secciones']]}")


def test_parseo_cama_nube_totales_por_seccion_exactos():
    from app.modules.productos import estructura_import as ei

    estructura = ei.parsear_texto_estructura(EXCEL_CAMA_NUBE)
    nombres = [s["nombre"] for s in estructura["secciones"]]

    # EBANISTERÍA (CAMA): 10 insumos con total + FABRICACIÓN como costo de producción
    eba = _por_nombre(estructura, "EBANISTERÍA (CAMA)")
    insumos_eba = ei.subtotal_insumos(eba)
    assert insumos_eba == Decimal("402400.00"), f"Insumos ebanistería: {insumos_eba}"
    cp_eba = ei.subtotal_costos_prod(eba)
    assert cp_eba == Decimal("324000.00"), f"FABRICACIÓN (mano de obra): {cp_eba}"
    assert eba["pct_gastos"] == Decimal("10")
    assert eba["total_declarado_seccion"] == Decimal("799040.00")

    # TAPICERÍA: tela 384,000 + espumas + hechura 210,000 → 868,150
    tapi = _por_nombre(estructura, "TAPICERÍA")
    assert ei.subtotal_insumos(tapi) + ei.subtotal_costos_prod(tapi) == Decimal("868150.00")

    # TENDIDO: 283,900 (incluye HECHURA TENDIDO 64,800)
    tend = _por_nombre(estructura, "TENDIDO")
    assert ei.subtotal_insumos(tend) + ei.subtotal_costos_prod(tend) == Decimal("283900.00")

    # TERMINACIÓN: solo EMBALADA tiene total → 100,000
    term = _por_nombre(estructura, "TERMINACIÓN")
    assert ei.subtotal_insumos(term) + ei.subtotal_costos_prod(term) == Decimal("100000.00")

    # TOTAL declarado del Excel
    assert estructura["totales"]["TOTAL_PRODUCCION"] == Decimal("2051090.00")


def test_resumen_cuadra_con_total_declarado():
    from app.modules.productos import estructura_import as ei

    estructura = ei.parsear_texto_estructura(EXCEL_CAMA_NUBE)
    resumen = ei.resumen_calculo(estructura, ganancia_pct=40, impuesto_pct=7)

    assert resumen["total_declarado_excel"] == 2051090.00
    assert resumen["costo_produccion"] == pytest.approx(2051090.00, abs=0.02)
    assert resumen["desviacion_porcentual"] is not None
    assert resumen["desviacion_porcentual"] < 0.01, (
        f"El calculado ({resumen['costo_produccion']}) no cuadra con el "
        f"declarado ({resumen['total_declarado_excel']}): desviación {resumen['desviacion_porcentual']}%"
    )
    assert resumen["excede_gate_15"] is False

    # Precio sugerido: 2,051,090 × 1.07 = 2,194,666.30 × 1.4 = 3,072,532.82 → redondeo COP al millar
    assert resumen["impuestos"] == pytest.approx(143576.30, abs=0.02)
    assert resumen["precio_sin_iva"] == 3073000


def test_referencias_sin_total_se_descartan():
    from app.modules.productos import estructura_import as ei

    estructura = ei.parsear_texto_estructura(EXCEL_CAMA_NUBE)
    nombres_desc = [r["nombre"] for r in estructura["referencias_descartadas"]]
    # Las filas de pintura/terminación con PRECIO TOTAL 0.00 son referencias,
    # no montos: se descartan (o se ignoran) en lugar de multiplicar fantasmas.
    assert "LACA" in nombres_desc
    assert "SELLADOR" in nombres_desc
    assert "EMBALADA" not in nombres_desc  # esta SÍ tiene total (100,000)
    # Las filas PREPARADO/PINTURA "CON EL 5%" con total 0.00 se ignoran: no son
    # insumos ni costos de producción con monto. Por eso la sección PINTURA ni
    # siquiera aparece (sin insumos ni costos reales).
    nombres_secciones = [s["nombre"] for s in estructura["secciones"]]
    assert not any("PINTURA" in n for n in nombres_secciones)


# ============================================================================
# 3. Vista previa vía API (dry_run): sin desviación, sin gate
# ============================================================================

def test_api_import_estructura_texto_dry_run_cuadra(client, cleaner):
    payload = {
        "texto": EXCEL_CAMA_NUBE,
        "nombre": "CAMA NUBE (prueba import)",
        "tipo_producto_id": 1,
        "dry_run": True,
    }
    r = client.post("/api/v1/producto/importar-estructura-texto", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    resumen = body["resumen"]
    assert resumen["total_declarado_excel"] == 2051090.00
    assert resumen["costo_produccion"] == pytest.approx(2051090.00, abs=0.02)
    assert resumen["excede_gate_15"] is False
    assert body["totales_excel"]["TOTAL_PRODUCCION"] == 2051090.00
