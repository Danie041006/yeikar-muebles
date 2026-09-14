"""
test_blindaje_huella.py — Fase 3 del blindaje: huella / passkeys (WebAuthn).

Las ceremonias criptográficas completas requieren un navegador real; aquí se
cubre el alambre: generación de opciones, rechazo de ceremonias inválidas,
listado/borrado de huellas y que el login biométrico no entienda basura.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import ADMIN_HEADERS, _uniq

import uuid
from fastapi.testclient import TestClient


def crear_usuario_test(client: TestClient, cleaner) -> dict:
    payload = {
        "nombre_usuario": f"test_huella_{uuid.uuid4().hex[:8]}",
        "password": "clave-test-123",
        "nombre": "Huella Test",
    }
    r = client.post("/api/auth/users", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear usuario → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("usuario", body["id"])
    return body


def _token_para(nombre: str) -> dict:
    from conftest import _firmar_token
    return {"Authorization": f"Bearer {_firmar_token(nombre)}"}


def test_opciones_registro_exigen_sesion(client, cleaner):
    r = client.post("/api/auth/webauthn/registro/inicio")
    assert r.status_code == 401, r.text


def test_opciones_registro_con_sesion(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    r = client.post("/api/auth/webauthn/registro/inicio", headers=_token_para(user["nombre_usuario"]))
    assert r.status_code == 200, r.text
    opciones = r.json()
    assert opciones["rp"]["id"] and opciones["rp"]["name"]
    assert opciones["challenge"]
    assert opciones["user"]["name"] == user["nombre_usuario"]


def test_login_inicio_sin_huellas_registradas(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    r = client.post("/api/auth/webauthn/login/inicio", json={"nombre_usuario": user["nombre_usuario"]})
    assert r.status_code == 404, r.text


def test_login_inicio_usuario_desconocido_no_filtra(client, cleaner):
    r = client.post("/api/auth/webauthn/login/inicio", json={"nombre_usuario": "nadie_falso_999"})
    assert r.status_code == 404, r.text


def test_registro_fin_con_respuesta_basura_rechazado(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    headers = _token_para(user["nombre_usuario"])
    client.post("/api/auth/webauthn/registro/inicio", headers=headers)
    r = client.post("/api/auth/webauthn/registro/fin", json={
        "dispositivo": "Test",
        "respuesta": {"id": "basura", "rawId": "basura", "type": "public-key",
                      "response": {"clientDataJSON": "basura", "attestationObject": "basura"}},
    }, headers=headers)
    assert r.status_code == 400, r.text


def test_login_fin_con_respuesta_basura_rechazado(client, cleaner):
    r = client.post("/api/auth/webauthn/login/fin", json={
        "nombre_usuario": "test_huella_inexistente",
        "respuesta": {"id": "basura", "rawId": "basura", "type": "public-key",
                      "response": {"clientDataJSON": "basura", "authenticatorData": "basura",
                                   "signature": "basura", "userHandle": "basura"}},
    })
    assert r.status_code == 401, r.text


def test_huellas_listar_y_borrar(client, cleaner, db):
    from sqlalchemy import text as sql
    user = crear_usuario_test(client, cleaner)
    headers = _token_para(user["nombre_usuario"])

    # Huella sembrada directo (la ceremonia real necesita navegador)
    fila = db.execute(sql(
        "INSERT INTO credencial_webauthn (usuario_id, credential_id, llave_publica, dispositivo) "
        "VALUES (:u, :c, :k, :d) RETURNING id"
    ), {"u": user["id"], "c": _uniq("cred"), "k": "c2VtaWxsYQ==", "d": "Huella de prueba"}).fetchone()
    huella_id = int(fila[0])
    db.commit()  # la API lee en otra sesión: sin commit no se ve la fila

    # Se limpia sola con el usuario (FK CASCADE) — registrar de todos modos
    cleaner.registrar("credencial_webauthn", huella_id)

    rl = client.get("/api/auth/webauthn/huellas", headers=headers)
    assert rl.status_code == 200, rl.text
    huellas = rl.json()
    assert len(huellas) == 1 and huellas[0]["dispositivo"] == "Huella de prueba"

    rb = client.delete(f"/api/auth/webauthn/huellas/{huella_id}", headers=headers)
    assert rb.status_code == 204, rb.text
    assert client.get("/api/auth/webauthn/huellas", headers=headers).json() == []
