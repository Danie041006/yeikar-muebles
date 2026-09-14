"""
test_blindaje_2fa.py — Fase 2 del blindaje: segundo factor con app (TOTP).

Cubre: activar 2FA con QR, login que exige código (ticket), código errado,
código correcto, cookie de equipo confiable (salta el 2FA), códigos de
respaldo de un solo uso, desactivar y reseteo por administrador.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import ADMIN_HEADERS

import uuid
import pyotp
from fastapi.testclient import TestClient
import sqlalchemy as sa

from app.db.session import session_local
from app.modules.users import service


def crear_usuario_test(client: TestClient, cleaner) -> dict:
    payload = {
        "nombre_usuario": f"test_2fa_{uuid.uuid4().hex[:8]}",
        "password": "clave-test-123",
        "nombre": "2FA Test",
    }
    r = client.post("/api/auth/users", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear usuario → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("usuario", body["id"])
    return body


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def _verificar_2fa(client: TestClient, ticket: str, secreto: str, recordar: bool = False):
    """Verifica el código TOTP tolerando el cruce de período (30s): si el
    código 'actual' cae justo en el borde, reintenta con el período siguiente."""
    import time
    codigos = (pyotp.TOTP(secreto).now(), pyotp.TOTP(secreto).at(time.time() + 31))
    r = None
    for codigo in codigos:
        r = client.post("/api/auth/2fa/verificar", json={
            "ticket": ticket, "codigo": codigo, "recordar_equipo": recordar,
        })
        if r.status_code == 200:
            return r
    return r


def _activar_2fa(client: TestClient, headers: dict) -> tuple[list, str]:
    """Activa 2FA vía API y devuelve (códigos de respaldo, secreto activo)."""
    rg = client.post("/api/auth/2fa/generar", headers=headers)
    assert rg.status_code == 200, rg.text
    uri = rg.json()["otpauth_uri"]
    assert uri.startswith("otpauth://totp/")
    assert len(rg.json()["qr_base64"]) > 100
    secreto = pyotp.parse_uri(uri).secret
    ra = client.post("/api/auth/2fa/activar", json={"codigo": pyotp.TOTP(secreto).now()}, headers=headers)
    assert ra.status_code == 200, ra.text
    codigos = ra.json()["codigos_respaldo"]
    assert len(codigos) == 10
    return codigos, secreto


def test_login_exige_codigo_cuando_2fa_activo(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    r0 = _login(client, user["nombre_usuario"], "clave-test-123")
    assert r0.status_code == 200, r0.text
    headers = {"Authorization": f"Bearer {r0.json()['access_token']}"}

    _, secreto = _activar_2fa(client, headers)

    # El siguiente login ya NO entrega tokens: pide código
    r1 = _login(client, user["nombre_usuario"], "clave-test-123")
    body = r1.json()
    assert r1.status_code == 200, r1.text
    assert body.get("requiere_2fa") is True
    assert body.get("ticket")
    assert "access_token" not in body

    # Código errado → 401
    rv = client.post("/api/auth/2fa/verificar", json={
        "ticket": body["ticket"], "codigo": "000000", "recordar_equipo": False,
    })
    assert rv.status_code == 401, rv.text

    # Código correcto → tokens
    rok = _verificar_2fa(client, body["ticket"], secreto)
    assert rok is not None and rok.status_code == 200, rok.text
    assert rok.json()["access_token"] and rok.json()["refresh_token"]


def test_codigo_respaldo_es_de_un_solo_uso(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    r0 = _login(client, user["nombre_usuario"], "clave-test-123")
    headers = {"Authorization": f"Bearer {r0.json()['access_token']}"}
    codigos, _ = _activar_2fa(client, headers)

    body = _login(client, user["nombre_usuario"], "clave-test-123").json()
    assert body.get("requiere_2fa") is True

    # Primer uso del respaldo → 200
    r1 = client.post("/api/auth/2fa/verificar", json={
        "ticket": body["ticket"], "codigo": codigos[0], "recordar_equipo": False,
    })
    assert r1.status_code == 200, r1.text

    # Reuso del MISMO código → 401
    body2 = _login(client, user["nombre_usuario"], "clave-test-123").json()
    r2 = client.post("/api/auth/2fa/verificar", json={
        "ticket": body2["ticket"], "codigo": codigos[0], "recordar_equipo": False,
    })
    assert r2.status_code == 401, r2.text

    # Un segundo respaldo distinto sí sirve
    r3 = client.post("/api/auth/2fa/verificar", json={
        "ticket": body2["ticket"], "codigo": codigos[1], "recordar_equipo": False,
    })
    assert r3.status_code == 200, r3.text


def test_cookie_de_equipo_confiable_salta_el_2fa(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    r0 = _login(client, user["nombre_usuario"], "clave-test-123")
    headers = {"Authorization": f"Bearer {r0.json()['access_token']}"}
    _activar_2fa(client, headers)

    body = _login(client, user["nombre_usuario"], "clave-test-123").json()
    assert body.get("requiere_2fa") is True

    # Verificar pidiendo recordar_equipo → la respuesta trae la cookie firmada
    rver = _verificar_2fa(client, body["ticket"], _secreto_activo(user["id"]), recordar=True)
    assert rver is not None and rver.status_code == 200, rver.text
    assert "yeikar_dispositivo" in rver.cookies

    # El siguiente login (mismo cliente, misma cookie) entra directo
    rd = _login(client, user["nombre_usuario"], "clave-test-123")
    assert rd.status_code == 200, rd.text
    assert rd.json().get("access_token"), "con cookie confiable no debe pedir 2FA"
    client.cookies.clear()


def test_desactivar_con_codigo_invalido_no_desactiva(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    r0 = _login(client, user["nombre_usuario"], "clave-test-123")
    headers = {"Authorization": f"Bearer {r0.json()['access_token']}"}
    _, secreto = _activar_2fa(client, headers)

    rmal = client.post("/api/auth/2fa/desactivar", json={"codigo": "000000"}, headers=headers)
    assert rmal.status_code == 400, rmal.text
    body = _login(client, user["nombre_usuario"], "clave-test-123").json()
    assert body.get("requiere_2fa") is True

    rok = client.post("/api/auth/2fa/desactivar", json={
        "codigo": pyotp.TOTP(secreto).now()}, headers=headers)
    assert rok.status_code == 200, rok.text
    rl = _login(client, user["nombre_usuario"], "clave-test-123")
    assert rl.json().get("access_token"), rl.text


def test_reset_admin_apaga_2fa_y_sesiones(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    r0 = _login(client, user["nombre_usuario"], "clave-test-123")
    headers = {"Authorization": f"Bearer {r0.json()['access_token']}"}
    _activar_2fa(client, headers)
    assert _login(client, user["nombre_usuario"], "clave-test-123").json().get("requiere_2fa") is True

    rr = client.post(f"/api/auth/users/{user['id']}/reset-2fa", headers=ADMIN_HEADERS)
    assert rr.status_code == 200, rr.text
    assert _login(client, user["nombre_usuario"], "clave-test-123").json().get("access_token")


def test_regenenerar_qr_no_apaga_el_2fa_activo(client, cleaner):
    user = crear_usuario_test(client, cleaner)
    r0 = _login(client, user["nombre_usuario"], "clave-test-123")
    headers = {"Authorization": f"Bearer {r0.json()['access_token']}"}
    _, secreto = _activar_2fa(client, headers)

    rg = client.post("/api/auth/2fa/generar", headers=headers)
    assert rg.status_code == 200, rg.text

    body = _login(client, user["nombre_usuario"], "clave-test-123").json()
    assert body.get("requiere_2fa") is True, "regenerar QR no debe apagar el 2FA"

    # El código del secreto ACTIVO (rotado) sigue siendo el que vale
    rok = _verificar_2fa(client, body["ticket"], _secreto_activo(user["id"]))
    assert rok is not None and rok.status_code == 200, rok.text


def _secreto_activo(usuario_id: int) -> str:
    """Lee el secreto ACTIVO del usuario (el que la app debe tener escaneado)."""
    db = session_local()
    try:
        fila = db.execute(
            sa.text("SELECT totp_secret FROM usuario WHERE id = :i"),
            {"i": usuario_id},
        ).fetchone()
        return fila[0]
    finally:
        db.close()
