#!/usr/bin/env python3
"""
Pruebas de integración del Motor de Cotización Inteligente (IQE).

Ejecutar con el venv del backend (requiere PostgreSQL activo):
  backend/venv/bin/python backend/test/test_iqe.py

Si find-similar devuelve vacío, ejecutar primero:
  backend/venv/bin/python backend/scripts/importar_atributos_historicos.py
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
from app.modules.clients.model import Client
from app.modules.productos.model import Producto, CamaHistoricaAtributos, MuebleAtributos

client = TestClient(app)

# IQE ahora exige autenticación: obtenemos un token de un usuario con
# el módulo cotizaciones_ia (carolina tiene Ventas + Producción + Inventario).
def _get_headers() -> dict:
    r_login = client.post("/api/auth/login", data={"username": "carolina", "password": "carolina2025$"})
    assert r_login.status_code == 200, f"Login falló: {r_login.text}"
    return {"Authorization": f"Bearer {r_login.json()['access_token']}"}


def _auth_headers() -> dict:
    """Token JWT de un usuario Dueño (acceso total) para los endpoints del IQE."""
    token = jwt.encode(
        {"sub": "daniel", "type": "access", "exp": datetime.utcnow() + timedelta(hours=1)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


HEADERS = _auth_headers()


def _ensure_atributos_historicos(db) -> int:
    """Si las tablas históricas están vacías, las genera desde las recetas."""
    n_cama = db.query(CamaHistoricaAtributos).count()
    n_mueble = db.query(MuebleAtributos).filter(MuebleAtributos.tipo_mueble == "cama").count()
    if n_cama > 0 or n_mueble > 0:
        return n_cama + n_mueble

    print("⚙️  Tablas históricas vacías — ejecutando importar_atributos_historicos...")
    from scripts.importar_atributos_historicos import main as importar
    importar()
    db.expire_all()
    return db.query(CamaHistoricaAtributos).count() + db.query(MuebleAtributos).count()


def test_iqe_flow():
    print("🚀 Iniciando pruebas del Motor de Cotización Inteligente (IQE)...")

    # 1. Health
    r_health = client.get("/api/v1/intelligent-quotation/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"
    print("✅ GET /health funciona correctamente.")

    # Resto de endpoints requieren autenticación
    HEADERS = _get_headers()

    db = session_local()
    client_id: int | None = None
    cama_id: int | None = None
    cama_nombre: str | None = None
    try:
        _ensure_atributos_historicos(db)
        real_client = db.query(Client).first()
        real_cama = db.query(Producto).filter(Producto.nombre.ilike("%Cama%")).first()
        if real_client:
            client_id = real_client.id
        if real_cama:
            cama_id = real_cama.id
            cama_nombre = real_cama.nombre
    finally:
        db.close()

    if client_id is None:
        print("⚠️  No hay clientes en la BD — omitiendo pruebas de integración.")
        return
    if cama_id is None:
        print("⚠️  No hay camas en la BD — omitiendo pruebas de integración.")
        return

    print(f"📌 Cliente ID: {client_id} | Cama ID: {cama_id} ('{cama_nombre}')")

    # 2. find-similar
    r_similar = client.post("/api/v1/intelligent-quotation/find-similar", headers=HEADERS, json={
        "tipo_mueble": "cama",
        "tiene_tapiceria": True,
        "tiene_nocheros": True,
        "tiene_espejo": False,
        "tiene_luces": False,
        "tipo_patas": "madera",
        "estilo_general": "moderno",
        "top_n": 3,
    })
    assert r_similar.status_code == 200, r_similar.text
    data_similar = r_similar.json()
    assert "resultados" in data_similar
    assert len(data_similar["resultados"]) > 0, (
        "find-similar devolvió vacío. Ejecuta: "
        "backend/venv/bin/python backend/scripts/importar_atributos_historicos.py"
    )
    print(f"✅ POST /find-similar → {len(data_similar['resultados'])} resultados "
          f"(top: {data_similar['resultados'][0]['nombre']}, "
          f"score={data_similar['resultados'][0]['score_pct']}%)")

    producto_base_id = data_similar["resultados"][0]["producto_id"]

    # 3. create-draft (flujo v1)
    r_draft = client.post("/api/v1/intelligent-quotation/create-draft", headers=HEADERS, json={
        "producto_base_id": producto_base_id,
        "nuevo_ancho": 1.60,
        "nuevo_largo": 1.90,
        "ganancia_porcentaje": 40.0,
        "iva_porcentaje": 0.0,
        "pct_mano_obra": 15.0,
        "pct_gastos": 10.0,
    })
    assert r_draft.status_code == 200, r_draft.text
    data_draft = r_draft.json()
    assert "materiales" in data_draft
    assert len(data_draft["materiales"]) > 0
    print(f"✅ POST /create-draft → {len(data_draft['materiales'])} materiales")

    materiales_payload = [
        {"material_id": m["material_id"], "cantidad_calculada": m["cantidad_calculada"], "activo": m["activo"]}
        for m in data_draft["materiales"]
    ]

    # 4. recalculate (flujo v1)
    r_recalc = client.post("/api/v1/intelligent-quotation/recalculate", headers=HEADERS, json={
        "producto_base_id": producto_base_id,
        "nuevo_ancho": 1.80,
        "nuevo_largo": 1.90,
        "materiales": materiales_payload,
        "ganancia_porcentaje": 40.0,
        "iva_porcentaje": 0.0,
        "pct_mano_obra": 15.0,
        "pct_gastos": 10.0,
    })
    assert r_recalc.status_code == 200, r_recalc.text
    assert r_recalc.json()["nuevo_ancho"] == 1.80
    print("✅ POST /recalculate funciona correctamente.")

    # 5. generate-structure (flujo v2)
    estructura_ia = [
        {
            "seccion": "EBANISTERÍA",
            "items": [
                {
                    "nombre_material": "MDF RH 15MM",
                    "cantidad_sugerida": 2.5,
                    "unidad": "m2",
                    "razon": "Estructura principal de la cama",
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

    r_gen = client.post("/api/v1/intelligent-quotation/generate-structure", headers=HEADERS, json={
        "tipo_mueble": "cama",
        "atributos": {
            "tiene_tapiceria": True,
            "tiene_luces": False,
            "tipo_patas": "madera",
            "estilo_general": "moderno",
            "atributos_extra": {"tiene_nocheros": True, "tiene_espejo": False},
        },
        "estructura_propuesta": estructura_ia,
        "nuevo_ancho": 1.60,
        "nuevo_largo": 1.90,
        "ganancia_porcentaje": 40.0,
        "iva_porcentaje": 0.0,
        "pct_mano_obra": 15.0,
        "pct_gastos": 10.0,
    })
    assert r_gen.status_code == 200, r_gen.text
    data_gen = r_gen.json()
    assert "secciones" in data_gen
    assert len(data_gen["secciones"]) > 0
    assert "resumen" in data_gen
    assert data_gen["resumen"]["precio_con_iva"] >= 0
    print(f"✅ POST /generate-structure → {len(data_gen['secciones'])} secciones, "
          f"base={data_gen.get('producto_base_nombre')}")

    # 6. recalculate-structure (flujo v2)
    r_recalc_struct = client.post("/api/v1/intelligent-quotation/recalculate-structure", headers=HEADERS, json={
        "secciones": data_gen["secciones"],
        "ganancia_porcentaje": 45.0,
        "iva_porcentaje": 0.0,
        "pct_mano_obra": 15.0,
        "pct_gastos": 10.0,
    })
    assert r_recalc_struct.status_code == 200, r_recalc_struct.text
    data_recalc_struct = r_recalc_struct.json()
    assert data_recalc_struct["resumen"]["ganancia_porcentaje"] == 45.0
    print("✅ POST /recalculate-structure funciona correctamente.")

    # 7. finalize (flujo v1)
    r_finalize = client.post("/api/v1/intelligent-quotation/finalize", headers=HEADERS, json={
        "cliente_id": client_id,
        "producto_base_id": producto_base_id,
        "nuevo_ancho": 1.60,
        "nuevo_largo": 1.90,
        "materiales": materiales_payload,
        "ganancia_porcentaje": 40.0,
        "iva_porcentaje": 0.0,
        "pct_mano_obra": 15.0,
        "pct_gastos": 10.0,
        "observaciones": "Test unitario IQE",
    })
    assert r_finalize.status_code == 200, r_finalize.text
    cot_id = r_finalize.json()["cotizacion_id"]
    assert cot_id > 0
    print(f"✅ POST /finalize → Cotización #{cot_id}")

    # 8. finalize-structure como cotización (flujo v2)
    r_fin_struct = client.post("/api/v1/intelligent-quotation/finalize-structure", headers=HEADERS, json={
        "guardar_como": "cotizacion",
        "cliente_id": client_id,
        "producto_base_id": producto_base_id,
        "nuevo_ancho": 1.60,
        "nuevo_largo": 1.90,
        "secciones": data_recalc_struct["secciones"],
        "ganancia_porcentaje": 45.0,
        "iva_porcentaje": 0.0,
        "pct_mano_obra": 15.0,
        "pct_gastos": 10.0,
        "observaciones": "Test unitario IQE v2 estructura",
    })
    assert r_fin_struct.status_code == 200, r_fin_struct.text
    cot_id_v2 = r_fin_struct.json()["cotizacion_id"]
    assert cot_id_v2 > 0
    print(f"✅ POST /finalize-structure → Cotización #{cot_id_v2}")

    print("🎉 ¡Todas las pruebas del módulo IQE pasaron exitosamente!")


if __name__ == "__main__":
    test_iqe_flow()
