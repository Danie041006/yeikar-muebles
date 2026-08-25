#!/usr/bin/env python3
"""
Pruebas del MODO MANUAL del Cotizador IA (sin API):
  - GET  /api/v1/intelligent-quotation/contexto-exportar
  - POST /api/v1/intelligent-quotation/import-structure

Ejecutar con el venv del backend:
  venv/bin/python -m pytest test/test_iqe_manual.py -v
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from jose import jwt

from app.main import app
from app.core.config import settings
from app.db.session import session_local
from app.modules.productos.model import Material, Producto

client = TestClient(app)


def _auth_headers() -> dict:
    token = jwt.encode(
        {"sub": "daniel", "type": "access", "exp": datetime.utcnow() + timedelta(hours=1)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


HEADERS = _auth_headers()


# ---------------------------------------------------------------------------
# 1) Paquete de contexto
# ---------------------------------------------------------------------------
def test_contexto_exportar_sin_producto(client, cleaner):
    r = client.get("/api/v1/intelligent-quotation/contexto-exportar", headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["inventario"]) > 0, "El paquete debe incluir el catálogo de inventario"
    assert "CATÁLOGO DE INVENTARIO" in data["instrucciones"]
    assert "preguntas clave" in data["instrucciones"]
    assert "texto" in data and "CÓMO USARLO" in data["texto"]


def test_contexto_exportar_incluye_libreria_de_4_prompts(client, cleaner):
    r = client.get("/api/v1/intelligent-quotation/contexto-exportar", headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "prompts" in data, "El paquete debe incluir la librería de prompts"
    assert len(data["prompts"]) == 4
    ids = {p["id"] for p in data["prompts"]}
    assert ids == {"entender_mueble", "estructura_costos", "preguntas_especificas", "reparar_pegar"}
    for p in data["prompts"]:
        assert p["titulo"] and p["instrucciones"]
        assert "CATÁLOGO DE INVENTARIO" in p["instrucciones"]
    # El prompt por defecto = "entender_mueble"
    assert data["instrucciones"] == data["prompts"][0]["instrucciones"]


def test_contexto_exportar_respuesta_formato_excel_sin_json(client, cleaner):
    r = client.get("/api/v1/intelligent-quotation/contexto-exportar", headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    estructura = next(p for p in data["prompts"] if p["id"] == "estructura_costos")
    # La respuesta que pedimos es formato Excel (tabla), NO JSON
    assert "MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL" in estructura["instrucciones"]
    assert "Devuelve la tabla en texto plano" in estructura["instrucciones"]
    for p in data["prompts"]:
        assert "estructura_propuesta" not in p["instrucciones"], "No debe exigir JSON visible al usuario"


def test_contexto_exportar_catalogo_limpio(client, cleaner):
    r = client.get("/api/v1/intelligent-quotation/contexto-exportar", headers=HEADERS)
    assert r.status_code == 200, r.text
    inventario = r.json()["inventario"]
    nombres = [m["nombre"] for m in inventario]
    # Sin materiales de prueba ni líneas-total
    assert not any(n.lower().startswith("test") for n in nombres)
    assert not any(n.upper().startswith("TOTAL") for n in nombres)
    # Sin duplicados exactos por nombre
    assert len(set(nombres)) == len(nombres)


def test_contexto_exportar_reglas_de_vocabulario_excel(client, cleaner):
    r = client.get("/api/v1/intelligent-quotation/contexto-exportar", headers=HEADERS)
    assert r.status_code == 200, r.text
    instr = r.json()["instrucciones"]
    assert "Mano de obra POR SECCIÓN" in instr, "La regla de labor por sección debe estar presente"
    assert "NO conviertas ni inventes unidades" in instr
    assert "LAMINA, LITRO, TIRA, PAR, PISTOLADA" in instr


def test_contexto_exportar_tipo_mueble_filtra_inventario_y_anatomia(client, cleaner):
    r_todo = client.get("/api/v1/intelligent-quotation/contexto-exportar", headers=HEADERS)
    r_cama = client.get(
        "/api/v1/intelligent-quotation/contexto-exportar",
        params={"tipo_mueble": "cama"},
        headers=HEADERS,
    )
    assert r_cama.status_code == 200, r_cama.text
    data = r_cama.json()
    # La anatomía de la cama debe estar presente en los prompts
    assert "ANATOMÍA DEL MUEBLE" in data["instrucciones"]
    assert "TENDIDO" in data["instrucciones"]
    assert "TAPICERÍA" in data["instrucciones"]
    # Con tipo conocido el catálogo del prompt se enfoca (puede ser menor o igual)
    assert len(data["inventario"]) <= len(r_todo.json()["inventario"])


def test_contexto_exportar_regla_de_piezas_y_secciones(client, cleaner):
    r = client.get("/api/v1/intelligent-quotation/contexto-exportar", headers=HEADERS)
    assert r.status_code == 200, r.text
    instr = r.json()["instrucciones"]
    assert "TENDIDO" in instr and "TERMINACIÓN" in instr
    # La regla de piezas (cama + nocheros, mesa + sillas) debe estar presente
    assert "NOMBRA la pieza entre paréntesis" in instr
    assert "EBANISTERÍA (CAMA)" in instr
    assert "EBANISTERÍA (NOCHEROS)" in instr
    # COLA DE PATO ya NO es una sección: es labor de TERMINACIÓN
    assert "COLA DE PATO (doblado de tela)" in instr


def test_contexto_exportar_anatomia_por_pieza_cama(client, cleaner):
    r = client.get("/api/v1/intelligent-quotation/contexto-exportar",
                   params={"tipo_mueble": "cama"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    instr = r.json()["instrucciones"]
    assert "Piezas del mueble: CAMA, NOCHEROS, PATAS" in instr
    assert "EBANISTERÍA (CAMA)" in instr and "PINTURA (NOCHEROS)" in instr
    assert "PINTURA (PATAS)" in instr



def test_contexto_exportar_con_producto_base(client, cleaner, db):
    db_local = session_local()
    try:
        producto = db_local.query(Producto).filter(Producto.materiales.any()).first()
    finally:
        db_local.close()
    if not producto:
        return  # sin recetas en esta BD, no se puede verificar el caso

    r = client.get(
        "/api/v1/intelligent-quotation/contexto-exportar",
        params={"producto_base_id": producto.id},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["producto_base_id"] == producto.id
    assert data["producto_base_nombre"] == producto.nombre
    assert data["receta_similar"] is not None
    # La estructura del producto base debe aparecer embebida como referencia
    assert "ESTRUCTURAS REALES QUE YA FABRICAMOS" in data["instrucciones"]
    assert producto.nombre in data["instrucciones"]


def test_contexto_exportar_producto_inexistente(client, cleaner):
    r = client.get(
        "/api/v1/intelligent-quotation/contexto-exportar",
        params={"producto_base_id": 999999},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["receta_similar"] is None  # producto inexistente → sin receta, no error


# ---------------------------------------------------------------------------
# 2) Importar estructura pegada por la IA de navegador
# ---------------------------------------------------------------------------
def test_import_structure_matchea_material_conocido(client, cleaner, db):
    db_local = session_local()
    try:
        mat = db_local.query(Material).filter(Material.activo == True).first()  # noqa: E712
        assert mat, "La BD debe tener al menos un material"
        nombre = mat.nombre
    finally:
        db_local.close()

    estructura = [{
        "seccion": "EBANISTERÍA",
        "items": [{
            "nombre_material": nombre,
            "cantidad_sugerida": 2,
            "unidad": "UN",
            "razon": "Prueba E2E manual",
            "es_opcional": False,
        }],
    }]
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={"estructura_propuesta": estructura,
                          "nuevo_ancho": 1.60, "nuevo_largo": 1.90},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["materiales_sin_precio"] == 0, f"El material conocido no se matcheó: {data['secciones']}"
    assert len(data["secciones"]) >= 1
    primer_item = data["secciones"][0]["items"][0]
    assert primer_item["material_id"] is not None
    assert primer_item["precio_pendiente"] is False
    assert primer_item["costo_unitario"] > 0


def test_import_structure_material_desconocido_queda_pendiente(client, cleaner):
    estructura = [{
        "seccion": "EBANISTERÍA",
        "items": [{
            "nombre_material": "MATERIAL INEXISTENTE E2E 9999",
            "cantidad_sugerida": 1,
            "unidad": "UN",
            "razon": "Prueba",
            "es_opcional": False,
        }],
    }]
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={"estructura_propuesta": estructura,
                          "nuevo_ancho": 1.60, "nuevo_largo": 1.90},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["materiales_sin_precio"] == 1
    primer_item = data["secciones"][0]["items"][0]
    assert primer_item["material_id"] is None
    assert primer_item["precio_pendiente"] is True


def test_import_structure_con_producto_base(client, cleaner, db):
    db_local = session_local()
    try:
        producto = db_local.query(Producto).filter(Producto.materiales.any()).first()
    finally:
        db_local.close()
    if not producto:
        return

    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={"estructura_propuesta": [{
                        "seccion": "EBANISTERÍA",
                        "items": [{
                            "nombre_material": "ADAPTACION PRUEBA E2E",
                            "cantidad_sugerida": 1,
                            "unidad": "UN",
                            "razon": "Prueba",
                            "es_opcional": False,
                        }],
                    }],
                          "producto_base_id": producto.id,
                          "nuevo_ancho": 1.60, "nuevo_largo": 1.90},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["producto_base_id"] == producto.id
    assert data["producto_base_nombre"] == producto.nombre
    # Con receta histórica: se agregan los materiales de la receta que la IA no mencionó
    assert len(data["secciones"]) > 0


def test_import_structure_producto_base_inexistente(client, cleaner):
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={"estructura_propuesta": [{
                        "seccion": "EBANISTERÍA",
                        "items": [{
                            "nombre_material": "MDF 18MM",
                            "cantidad_sugerida": 1,
                            "unidad": "UN",
                            "razon": "Prueba",
                            "es_opcional": False,
                        }],
                    }],
                          "producto_base_id": 999999,
                          "nuevo_ancho": 1.60, "nuevo_largo": 1.90},
                    headers=HEADERS)
    assert r.status_code == 400, r.text


def test_import_structure_vacio_devuelve_estructura_vacia(client, cleaner):
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={"estructura_propuesta": [],
                          "nuevo_ancho": 1.60, "nuevo_largo": 1.90},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["secciones"] == []


def test_import_structure_incluye_validacion_de_secciones(client, cleaner):
    """Con un tipo sin referencias en BD y una estructura incompleta, se reportan las secciones faltantes."""
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={
                        "estructura_propuesta": [{
                            "seccion": "EBANISTERÍA",
                            "items": [{
                                "nombre_material": "MDF 18MM",
                                "cantidad_sugerida": 2,
                                "unidad": "LAMINA",
                                "razon": "Prueba",
                                "es_opcional": False,
                            }],
                        }],
                        "tipo_mueble": "mueble_bano",
                        "nuevo_ancho": 1.60, "nuevo_largo": 1.90,
                    },
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "secciones_faltantes" in data
    assert "PINTURA" in data["secciones_faltantes"]
    assert "TERMINACIÓN" in data["secciones_faltantes"]
    assert "advertencia" in data and data["advertencia"] is not None
    assert "desviacion_vs_referencia" in data


# ---------------------------------------------------------------------------
# 2b) Anclaje a estructuras reales + líneas de labor
# ---------------------------------------------------------------------------
def test_contexto_exportar_incluye_referencias_reales(client, cleaner, db):
    db_local = session_local()
    try:
        hay_camas = db_local.query(Producto).filter(Producto.materiales.any()).count() > 0
    finally:
        db_local.close()
    if not hay_camas:
        return

    r = client.get("/api/v1/intelligent-quotation/contexto-exportar",
                   params={"tipo_mueble": "cama"},
                   headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    estructura = next(p for p in data["prompts"] if p["id"] == "estructura_costos")
    assert "ESTRUCTURAS REALES QUE YA FABRICAMOS" in estructura["instrucciones"]
    assert "PRODUCTO REAL:" in estructura["instrucciones"]
    # La regla de madera y la de TERMINACIÓN deben estar presentes
    assert "MADERA" in estructura["instrucciones"]
    assert "TERMINACIÓN" in estructura["instrucciones"]


def test_import_structure_linea_labor_no_bloquea(client, cleaner):
    """HECHURA (mano de obra) no debe quedar como 'precio pendiente'."""
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={
                        "estructura_propuesta": [{
                            "seccion": "EBANISTERÍA",
                            "items": [
                                {"nombre_material": "HECHURA", "cantidad_sugerida": 1, "unidad": "PAR", "razon": "", "es_opcional": False},
                                {"nombre_material": "MATERIAL INEXISTENTE E2E 7777", "cantidad_sugerida": 2, "unidad": "UN", "razon": "", "es_opcional": False},
                            ],
                        }],
                        "nuevo_ancho": 1.60, "nuevo_largo": 1.90,
                    },
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    # Solo el material físico desconocido cuenta como pendiente (1), no HECHURA
    assert data["materiales_sin_precio"] == 1, data["secciones"]


def test_import_structure_herrajes_en_terminacion_se_respetan(client, cleaner):
    """Si la IA agrupa herrajes en TERMINACIÓN (como el Excel), se respetan."""
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={
                        "estructura_propuesta": [{
                            "seccion": "TERMINACIÓN",
                            "items": [
                                {"nombre_material": "CORREDERAS", "cantidad_sugerida": 2, "unidad": "PAR", "razon": "", "es_opcional": False},
                                {"nombre_material": "EMBALAJE", "cantidad_sugerida": 1, "unidad": "UN", "razon": "", "es_opcional": False},
                            ],
                        }],
                        "nuevo_ancho": 1.60, "nuevo_largo": 1.90,
                    },
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    seccion_terminacion = next((s for s in data["secciones"] if s["seccion"] == "TERMINACIÓN"), None)
    assert seccion_terminacion is not None, data["secciones"]
    nombres = [i["nombre"] for i in seccion_terminacion["items"]]
    assert "CORREDERAS" in nombres, "El herraje debe permanecer en TERMINACIÓN"


def test_import_structure_auto_referencia_por_tipo(client, cleaner, db):
    """Sin producto_base_id, con tipo conocido, se auto-selecciona una referencia real."""
    db_local = session_local()
    try:
        hay_camas = db_local.query(Producto).filter(Producto.materiales.any()).count() > 0
    finally:
        db_local.close()
    if not hay_camas:
        return

    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={
                        "estructura_propuesta": [{
                            "seccion": "EBANISTERÍA",
                            "items": [{
                                "nombre_material": "MDF 18MM",
                                "cantidad_sugerida": 2,
                                "unidad": "LAMINA",
                                "razon": "Prueba",
                                "es_opcional": False,
                            }],
                        }],
                        "tipo_mueble": "cama",
                        "nuevo_ancho": 1.60, "nuevo_largo": 1.90,
                    },
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["producto_base_id"] is not None, "Debe auto-seleccionar una referencia real del tipo"
    assert data["producto_base_nombre"] is not None


# ---------------------------------------------------------------------------
# 2c) Secciones con pieza (sub-parte): EBANISTERÍA (CAMA), PINTURA (NOCHEROS)
# ---------------------------------------------------------------------------
def test_seccion_canonica_con_pieza():
    from app.modules.quotes.structure_builder import _seccion_canonica, _base_seccion
    assert _seccion_canonica("EBANISTERÍA (CAMA)") == "EBANISTERÍA (CAMA)"
    assert _seccion_canonica("PINTURA (NOCHEROS)") == "PINTURA (NOCHEROS)"
    assert _seccion_canonica("NOCHEROS EN CRUDO") == "NOCHEROS"
    assert _seccion_canonica("COLA_DE_PATO") == "TERMINACIÓN"
    assert _seccion_canonica("COLAPATO") == "TERMINACIÓN"
    assert _seccion_canonica(None) == "EBANISTERÍA"
    assert _base_seccion("EBANISTERÍA (CAMA)") == "EBANISTERÍA"
    assert _base_seccion("PINTURA (NOCHEROS)") == "PINTURA"


def test_import_texto_seccion_con_pieza(client, cleaner):
    """La IA responde con piezas (SECCION EBANISTERIA (CAMA)) y se respetan."""
    r = client.post("/api/v1/intelligent-quotation/import-texto",
                    json={
                        "texto": """```
SECCION EBANISTERIA (CAMA)
MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL
LAMINA DE 9 | 1 | LAMINA | 140000 | 140000
HECHURA (CAMA) | 1 | PAR |  |
SECCION PINTURA (NOCHEROS)
PREPARADO | 1 | PISTOLADA |  |
```
""",
                        "nuevo_ancho": 1.60, "nuevo_largo": 1.90,
                    },
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    nombres = {s["seccion"] for s in data["secciones"]}
    assert "EBANISTERÍA (CAMA)" in nombres, "La pieza debe conservarse"
    assert "PINTURA (NOCHEROS)" in nombres, "La pieza debe conservarse"
    # No debe caer a OTROS ni perder la pieza
    assert "OTROS" not in nombres


def test_import_structure_seccion_ia_con_pieza_respetada(client, cleaner):
    """Si la IA asigna 'PINTURA (NOCHEROS)', no se re-detecta desde el material."""
    r = client.post("/api/v1/intelligent-quotation/import-structure",
                    json={
                        "estructura_propuesta": [{
                            "seccion": "PINTURA (NOCHEROS)",
                            "items": [{
                                "nombre_material": "COLOR NEGRO",
                                "cantidad_sugerida": 2,
                                "unidad": "PISTOLADA",
                                "razon": "",
                                "es_opcional": False,
                            }],
                        }],
                        "nuevo_ancho": 1.60, "nuevo_largo": 1.90,
                    },
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    nombres = {s["seccion"] for s in data["secciones"]}
    assert "PINTURA (NOCHEROS)" in nombres, data["secciones"]


def test_import_texto_colapato_mapea_a_terminacion(client, cleaner):
    r = client.post("/api/v1/intelligent-quotation/import-texto",
                    json={
                        "texto": "SECCION COLA DE PATO\nCOLAPATO | 1 | UN\n",
                        "nuevo_ancho": 1.60, "nuevo_largo": 1.90,
                    },
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    nombres = {s["seccion"] for s in data["secciones"]}
    assert "TERMINACIÓN" in nombres, "COLA DE PATO debe mapearse a TERMINACIÓN"
    assert "COLA DE PATO" not in nombres and "OTROS" not in nombres


# ---------------------------------------------------------------------------
# 3) Importar respuesta en FORMATO EXCEL (import-texto)
# ---------------------------------------------------------------------------
def test_import_texto_parsea_respuesta_excel(client, cleaner, db):
    texto = """```
SECCION EBANISTERIA
MATERIAL | CANTIDAD | UNIDAD | V/UNIT | PRECIO TOTAL
LAMINA DE 9 | 1 | LAMINA | 140000 | 140000
COLBON | 0.7 | LITRO | 14000 | 9800
HECHURA | 1 | PAR |  |
SECCION PINTURA
PREPARADO | 1 | PISTOLADA |  |
```
"""
    r = client.post("/api/v1/intelligent-quotation/import-texto",
                    json={"texto": texto,
                          "tipo_mueble": "cama",
                          "nuevo_ancho": 1.60, "nuevo_largo": 1.90},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    nombres_secciones = {s["seccion"] for s in data["secciones"]}
    # La sección genérica EBANISTERÍA se fusiona con la pieza principal del
    # histórico (EBANISTERÍA (CAMA)) para no duplicar MO: verificar la base.
    assert any(n == "EBANISTERÍA" or n.startswith("EBANISTERÍA (") for n in nombres_secciones)
    assert any(n == "PINTURA" or n.startswith("PINTURA (") for n in nombres_secciones)
    # Los materiales se matchean o quedan pendientes, pero la sección PINTURA existe
    assert any(s["seccion"] == "PINTURA" or s["seccion"].startswith("PINTURA (")
               and len(s["items"]) > 0 for s in data["secciones"])


def test_import_texto_texto_ilegible_devuelve_400(client, cleaner):
    r = client.post("/api/v1/intelligent-quotation/import-texto",
                    json={"texto": "esto no es una estructura de costos",
                          "nuevo_ancho": 1.60, "nuevo_largo": 1.90},
                    headers=HEADERS)
    assert r.status_code == 400, r.text


def test_import_texto_con_producto_base(client, cleaner, db):
    db_local = session_local()
    try:
        producto = db_local.query(Producto).filter(Producto.materiales.any()).first()
    finally:
        db_local.close()
    if not producto:
        return
    texto = "SECCION EBANISTERIA\nMATERIAL | CANTIDAD | UNIDAD\nMDF 18MM | 2 | LAMINA\n"
    r = client.post("/api/v1/intelligent-quotation/import-texto",
                    json={"texto": texto,
                          "producto_base_id": producto.id,
                          "nuevo_ancho": 1.60, "nuevo_largo": 1.90},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["producto_base_id"] == producto.id

