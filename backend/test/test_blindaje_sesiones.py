"""
test_blindaje_sesiones.py — Fase 1 del blindaje de login.

Cubre: una fila de sesión por login (con rotación de refresh sin duplicar),
listado con la sesión actual marcada, cerrar las demás sesiones (revoca su
refresh) y cambio de contraseña con revocación total de sesiones.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import ADMIN_HEADERS, _uniq

from fastapi.testclient import TestClient

from app.core.config import settings
from app.modules.users import service


def crear_usuario_test(client: TestClient, cleaner) -> dict:
    nombre = _uniq("sec")
    payload = {"nombre_usuario": nombre, "password": "clave-test-123", "nombre": "Sec Test"}
    r = client.post("/api/auth/users", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear usuario → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("usuario", body["id"])
    return body


def _login(client: TestClient, username: str, password: str, extra: dict | None = None):
    form = {"username": username, "password": password}
    if extra:
        form.update(extra)
    return client.post("/api/auth/login", data=form)


def test_login_crea_sesion_y_rotacion_no_duplica(client, cleaner):
    user = crear_usuario_test(client, cleaner)

    r1 = _login(client, user["nombre_usuario"], "clave-test-123")
    assert r1.status_code == 200, r1.text
    tokens1 = r1.json()
    assert tokens1["access_token"] and tokens1["refresh_token"]

    r2 = _login(client, user["nombre_usuario"], "clave-test-123")
    tokens2 = r2.json()

    ses = client.get("/api/auth/sesiones", headers={"Authorization": f"Bearer {tokens1['access_token']}"})
    assert ses.status_code == 200, ses.text
    lista = ses.json()
    assert len(lista) == 2, f"debe haber 2 sesiones: {lista}"
    actual = [s for s in lista if s["actual"]]
    assert len(actual) == 1 and actual[0]["id"] >= 1

    # Rotación del refresh 1: la misma sesión continúa, no se crea una nueva
    rfr = client.post("/api/auth/refresh", json={"refresh_token": tokens1["refresh_token"]})
    assert rfr.status_code == 200, rfr.text
    ses2 = client.get("/api/auth/sesiones", headers={"Authorization": f"Bearer {rfr.json()['access_token']}"})
    assert len(ses2.json()) == 2, "la rotación no debe duplicar sesiones"


def test_cerrar_otras_revoca_el_refresh_de_las_demas(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    tokens1 = _login(client, user["nombre_usuario"], "clave-test-123").json()
    tokens2 = _login(client, user["nombre_usuario"], "clave-test-123").json()

    rc = client.post("/api/auth/sesiones/cerrar-otras", headers={"Authorization": f"Bearer {tokens1['access_token']}"})
    assert rc.status_code == 200, rc.text
    assert rc.json()["revocadas"] == 1

    # El refresh de la sesión CERRADA ya no sirve
    rv = client.post("/api/auth/refresh", json={"refresh_token": tokens2["refresh_token"]})
    assert rv.status_code == 401, f"el refresh de una sesión cerrada debe morir: {rv.text}"
    # El refresh de la sesión ACTUAL sigue vivo
    ro = client.post("/api/auth/refresh", json={"refresh_token": tokens1["refresh_token"]})
    assert ro.status_code == 200, ro.text


def test_cerrar_sesion_individual(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    tokens1 = _login(client, user["nombre_usuario"], "clave-test-123").json()
    tokens2 = _login(client, user["nombre_usuario"], "clave-test-123").json()

    lista = client.get("/api/auth/sesiones", headers={"Authorization": f"Bearer {tokens2['access_token']}"}).json()
    actual_id = next(s["id"] for s in lista if s["actual"])

    rdel = client.delete(f"/api/auth/sesiones/{actual_id}", headers={"Authorization": f"Bearer {tokens2['access_token']}"})
    assert rdel.status_code == 204, rdel.text
    assert client.post("/api/auth/refresh", json={"refresh_token": tokens2["refresh_token"]}).status_code == 401


def test_cambio_password_revoca_todas_las_sesiones(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    tokens1 = _login(client, user["nombre_usuario"], "clave-test-123").json()
    tokens2 = _login(client, user["nombre_usuario"], "clave-test-123").json()

    # Contraseña actual incorrecta → no cambia nada
    rmal = client.put("/api/auth/me/password", json={
        "password_actual": "otra-cosa", "password_nueva": "nueva-segura-456",
    }, headers={"Authorization": f"Bearer {tokens1['access_token']}"})
    assert rmal.status_code == 401, rmal.text
    assert client.post("/api/auth/refresh", json={"refresh_token": tokens1["refresh_token"]}).status_code == 200

    # Cambio correcto → TODAS las sesiones mueren (incluida la que pidió)
    rok = client.put("/api/auth/me/password", json={
        "password_actual": "clave-test-123", "password_nueva": "nueva-segura-456",
    }, headers={"Authorization": f"Bearer {tokens1['access_token']}"})
    assert rok.status_code == 200, rok.text

    assert client.post("/api/auth/refresh", json={"refresh_token": tokens1["refresh_token"]}).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": tokens2["refresh_token"]}).status_code == 401

    # La nueva contraseña sirve; la vieja no
    assert _login(client, user["nombre_usuario"], "clave-test-123").status_code == 401
    assert _login(client, user["nombre_usuario"], "nueva-segura-456").status_code == 200


def test_captcha_invisible_tras_fallos_repetidos(client, cleaner, monkeypatch):
    user = crear_usuario_test(client, cleaner)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", "test-secret", raising=False)
    monkeypatch.setattr(service, "verificar_turnstile", lambda token, ip: token == "tok-bueno")

    # 3 fallos acumulados (umbral CAPTCHA_LUEGO_DE_FALLOS)
    for _ in range(3):
        rf = _login(client, user["nombre_usuario"], "mal")
        assert rf.status_code == 401, rf.text

    # 4º intento con credenciales correctas: exige captcha
    rs = _login(client, user["nombre_usuario"], "clave-test-123")
    assert rs.status_code == 400, rs.text
    assert rs.json()["detail"]["requiere_captcha"] is True

    # Con token de captcha inválido sigue rechazando
    rmal_tok = _login(client, user["nombre_usuario"], "clave-test-123", {"turnstile_token": "tok-malo"})
    assert rmal_tok.status_code == 400, rmal_tok.text

    # Con token válido pasa
    rok = _login(client, user["nombre_usuario"], "clave-test-123", {"turnstile_token": "tok-bueno"})
    assert rok.status_code == 200, rok.text
