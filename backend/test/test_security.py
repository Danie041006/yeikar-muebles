#!/usr/bin/env python3
"""
test_security.py — Auditoría de autenticación y autorización del ERP YEIKAR.

Verifica que el sistema RECHAZA (401/403/400) lo que debe rechazar:
  - peticiones sin token, token inválido, con type="refresh", con sub
    inexistente, con exp pasado;
  - login con credenciales incorrectas;
  - replay de un refresh token ya rotado (revocado);
  - acceso a módulos sin permiso (gastos/usuarios con rol Ventas);
  - POST a /api/v1/pago/ con un rol sin gestión del módulo ventas;
  - desactivar el propio usuario administrador.

Y que ACEPTA lo que debe aceptar:
  - admin → /api/auth/users;
  - Ventas → /api/v1/venta/ y /api/v1/cotizacion/;
  - /api/auth/me con módulos completos para un Dueño.

Cualquier caso donde el sistema ACEPTE lo que debería rechazar se reporta
como bug de seguridad (no se arregla nada aquí, solo se documenta).

Ejecutar con PostgreSQL activo:
  cd /home/daniel-castellanos/YEIKAR/backend
  venv/bin/python -m pytest test/test_security.py -v
"""
import uuid
from datetime import datetime, timedelta
from hashlib import sha256

import pytest
from jose import jwt

from app.core.config import settings
from app.modules.catalogos.model import Rol
from app.modules.users import service as user_service
from app.modules.users.model import Usuario
from app.modules.users.deps import MODULOS_CATALOGO

try:
    from conftest import _firmar_token, ADMIN_HEADERS, VENTAS_HEADERS
except ImportError:  # pragma: no cover
    pytest.fail("No se pudo importar conftest (ADMIN_HEADERS/VENTAS_HEADERS/_firmar_token)")


def _firmar_payload(payload: dict) -> str:
    """Firma un payload JWT arbitrario con la clave del servidor."""
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ---------------------------------------------------------------------------
# 1) Autenticación: tokens ausentes / inválidos / mal tipados / expirados
# ---------------------------------------------------------------------------

def test_sin_token_401_en_negocio(client):
    """GET /api/v1/cotizacion/ sin Authorization debe ser 401."""
    r = client.get("/api/v1/cotizacion/")
    assert r.status_code == 401, (
        f"BUG: endpoint de negocio responde {r.status_code} sin token "
        f"(debe ser 401). Respuesta: {r.text[:300]}"
    )


def test_token_invalido_401(client):
    """Un Bearer token malformado ('token.falso') debe ser 401."""
    r = client.get("/api/v1/cotizacion/", headers={"Authorization": "Bearer token.falso"})
    assert r.status_code == 401, (
        f"BUG: token inválido aceptado → {r.status_code} (debe ser 401). "
        f"Respuesta: {r.text[:300]}"
    )


def test_token_con_refresh_type_rechazado(client):
    """Un JWT firmado con type='refresh' NO debe servir como access token."""
    token = _firmar_payload({
        "sub": "jackson",
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(hours=1),
    })
    r = client.get("/api/v1/cotizacion/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, (
        f"BUG: token type=refresh aceptado como access → {r.status_code} "
        f"(debe ser 401). Respuesta: {r.text[:300]}"
    )


def test_sub_inexistente_rechazado(client):
    """Token válido pero con sub que no existe en BD debe ser 401."""
    token = _firmar_token("usuario_que_no_existe_xyz")
    r = client.get("/api/v1/cotizacion/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, (
        f"BUG: token con sub inexistente aceptado → {r.status_code} "
        f"(debe ser 401). Respuesta: {r.text[:300]}"
    )


def test_token_expirado_rechazado(client):
    """Token con exp en el pasado debe ser 401."""
    token = _firmar_payload({
        "sub": "jackson",
        "type": "access",
        "exp": datetime.utcnow() - timedelta(minutes=5),
    })
    r = client.get("/api/v1/cotizacion/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, (
        f"BUG: token expirado aceptado → {r.status_code} (debe ser 401). "
        f"Respuesta: {r.text[:300]}"
    )


# ---------------------------------------------------------------------------
# 2) Login y rotación de refresh tokens
# ---------------------------------------------------------------------------

def test_login_incorrecto_401(client):
    """Login con usuario inexistente debe ser 401 (sin bloquear usuarios reales)."""
    username = f"noexiste_{uuid.uuid4().hex[:8]}"
    r = client.post("/api/auth/login", data={"username": username, "password": "clave-incorrecta-123"})
    assert r.status_code == 401, (
        f"BUG: login con credenciales incorrectas devuelve {r.status_code} "
        f"(debe ser 401). Respuesta: {r.text[:300]}"
    )


def test_lockout_no_es_dos_entre_cuentas(client, db):
    """5 fallos contra la cuenta A no deben bloquear la cuenta B (anti-DoS)."""
    from app.modules.users.model import LoginIntento
    import time
    base = f"qa_lock_{uuid.uuid4().hex[:6]}"
    username_a = f"{base}_a"
    username_b = f"{base}_b"
    try:
        # Fallos contra una cuenta inexistente
        for _ in range(5):
            r = client.post("/api/auth/login", data={"username": username_a, "password": "clave-incorrecta-123"})
            assert r.status_code == 401
        # El usuario legítimo (otra cuenta) debe poder loguear sin bloqueo
        r = client.post("/api/auth/login", data={"username": "carolina", "password": "carolina2025$"})
        assert r.status_code == 200, (
            f"BUG DoS: fallos contra {username_a} bloquearon a carolina → {r.status_code}"
        )
    finally:
        db.query(LoginIntento).filter(LoginIntento.username.like(f"{base}%")).delete()
        db.commit()


def test_lockout_por_combinacion_cuenta_ip(client, db):
    """El contador es por (cuenta, IP): fallos de una cuenta desde una IP
    solo bloquean esa combinación, no la cuenta de forma global."""
    from app.modules.users.model import LoginIntento
    base = f"qa_combo_{uuid.uuid4().hex[:6]}"
    username = f"{base}_x"
    try:
        for _ in range(5):
            r = client.post("/api/auth/login", data={"username": username, "password": "clave-incorrecta-123"})
            assert r.status_code == 401
        # El 6º intento (misma cuenta, misma IP) debe ser 429 (combos bloqueados)
        r = client.post("/api/auth/login", data={"username": username, "password": "clave-incorrecta-123"})
        assert r.status_code == 429, (
            f"BUG: la combinación (cuenta, IP) debió bloquear tras 5 fallos → {r.status_code}"
        )
    finally:
        db.query(LoginIntento).filter(LoginIntento.username.like(f"{base}%")).delete()
        db.commit()


def test_refresh_rotation_replay(client, db):
    """Reusar un refresh token ya rotado (replay) debe ser rechazado con 401."""
    r_login = client.post("/api/auth/login", data={"username": "carolina", "password": "carolina2025$"})
    assert r_login.status_code == 200, f"Login de carolina falló: {r_login.text[:300]}"
    r1 = r_login.json()["refresh_token"]

    hashes_creados = [sha256(r1.encode("utf-8")).hexdigest()]
    try:
        r_refresh = client.post("/api/auth/refresh", json={"refresh_token": r1})
        assert r_refresh.status_code == 200, (
            f"El primer refresh con R1 debió ser 200, dio {r_refresh.status_code}: {r_refresh.text[:300]}"
        )
        r2 = r_refresh.json()["refresh_token"]
        assert r2 and r2 != r1, "El refresh devolvió el mismo token (no rotó)"
        hashes_creados.append(sha256(r2.encode("utf-8")).hexdigest())

        r_replay = client.post("/api/auth/refresh", json={"refresh_token": r1})
        assert r_replay.status_code == 401, (
            f"BUG DE REPLAY: reusar el refresh token R1 dio {r_replay.status_code} "
            f"(debe ser 401: R1 fue revocado al rotar). Respuesta: {r_replay.text[:300]}"
        )
    finally:
        # Limpieza: borrar las filas refresh_token creadas por este test.
        from sqlalchemy import text
        for h in hashes_creados:
            db.execute(text("DELETE FROM refresh_token WHERE token_hash = :h"), {"h": h})
        db.commit()


# ---------------------------------------------------------------------------
# 3) Autorización por rol / módulo
# ---------------------------------------------------------------------------

def test_acceso_admin_a_users(client):
    """Dueño debe poder listar usuarios (200)."""
    r = client.get("/api/auth/users", headers=ADMIN_HEADERS)
    assert r.status_code == 200, (
        f"BUG: admin no puede listar usuarios → {r.status_code}: {r.text[:300]}"
    )


def test_ventas_no_ve_gastos(client):
    """Ventas NO tiene módulo gastos → GET gastos debe ser 403."""
    r = client.get("/api/v1/gasto/gastos/", headers=VENTAS_HEADERS)
    assert r.status_code == 403, (
        f"BUG: usuario Ventas accede a gastos → {r.status_code} (debe ser 403). "
        f"Respuesta: {r.text[:300]}"
    )


def test_ventas_no_ve_usuarios(client):
    """Ventas NO es admin → GET /api/auth/users debe ser 403."""
    r = client.get("/api/auth/users", headers=VENTAS_HEADERS)
    assert r.status_code == 403, (
        f"BUG: usuario Ventas lista usuarios → {r.status_code} (debe ser 403). "
        f"Respuesta: {r.text[:300]}"
    )


def test_ventas_accede_a_ventas_y_cotizaciones(client):
    """Ventas SÍ tiene módulos ventas y cotizaciones → ambos GET deben ser 200."""
    r_ventas = client.get("/api/v1/venta/", headers=VENTAS_HEADERS)
    assert r_ventas.status_code == 200, (
        f"Ventas no pudo leer /api/v1/venta/ → {r_ventas.status_code}: {r_ventas.text[:300]}"
    )
    r_cotiz = client.get("/api/v1/cotizacion/", headers=VENTAS_HEADERS)
    assert r_cotiz.status_code == 200, (
        f"Ventas no pudo leer /api/v1/cotizacion/ → {r_cotiz.status_code}: {r_cotiz.text[:300]}"
    )


def test_pago_requiere_modulo_ventas(client, db, cleaner):
    """POST /api/v1/pago/ exige gestión del módulo ventas.

    - Dueño (carolina): pasa la barrera de permisos → 422 por body inválido (no 403).
    - Fletes (sin gestionar ventas): debe ser 403 ANTES de validar el body.
    """
    # 1) Dueño: la validación de permisos no debe frenarlo (llega a validación de datos).
    r_dueno = client.post("/api/v1/pago/", json={}, headers={
        "Authorization": f"Bearer {_firmar_token('carolina')}"
    })
    assert r_dueno.status_code != 403, (
        f"BUG: Dueño rechazado por permisos en POST /api/v1/pago/ → {r_dueno.status_code}"
    )

    # 2) Usuario temporal con rol Fletes (sin gestionar ventas).
    nombre = f"test_sec_{uuid.uuid4().hex[:8]}"
    rol_fletes = db.query(Rol).filter(Rol.nombre == "Fletes").first()
    assert rol_fletes is not None, "Rol 'Fletes' no existe en la BD"
    usr = Usuario(
        nombre_usuario=nombre,
        email=f"{nombre}@test.local",
        password_hash=user_service.obtener_password_hash("clave-prueba-123"),
        activo=True,
    )
    db.add(usr)
    db.commit()
    db.refresh(usr)
    usr.roles.append(rol_fletes)
    db.commit()
    cleaner.registrar("usuario", usr.id)

    token = _firmar_token(nombre)
    r_fletes = client.post("/api/v1/pago/", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r_fletes.status_code == 403, (
        f"BUG DE SEGURIDAD: usuario Fletes pudo operar POST /api/v1/pago/ "
        f"→ {r_fletes.status_code} (debe ser 403). Respuesta: {r_fletes.text[:300]}"
    )


# ---------------------------------------------------------------------------
# 4) /me y auto-desactivación de admin
# ---------------------------------------------------------------------------

def test_me_incluye_modulos_correctos(client):
    """Un Dueño debe ver TODOS los módulos del catálogo con gestionar=True."""
    r = client.get("/api/auth/me", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"/me falló → {r.status_code}: {r.text[:300]}"
    body = r.json()
    modulos = {m["modulo"]: m["gestionar"] for m in body["modulos"]}
    esperados = {m["clave"] for m in MODULOS_CATALOGO}
    faltantes = esperados - set(modulos)
    assert not faltantes, f"BUG: /me de Dueño no incluye módulos: {faltantes}"
    gestionar_false = [m for m, g in modulos.items() if not g]
    assert not gestionar_false, (
        f"BUG: Dueño debería gestionar todos los módulos, faltan permisos: {gestionar_false}"
    )


def test_no_se_puede_modificar_estado_propio(client):
    """Un admin no puede desactivarse a sí mismo → 400.

    Usamos jackson (ADMIN_HEADERS): se obtiene su propio id vía /me y se intenta
    `PUT /users/{id}/status?activo=false`. Si el sistema lo permitiera (200),
    se reactiva de inmediato en el finally para no dejar al admin desactivado.
    """
    r_me = client.get("/api/auth/me", headers=ADMIN_HEADERS)
    assert r_me.status_code == 200, f"/me falló → {r_me.status_code}: {r_me.text[:300]}"
    mi_id = r_me.json()["id"]

    r = None
    try:
        r = client.put(
            f"/api/auth/users/{mi_id}/status",
            params={"activo": False},
            headers=ADMIN_HEADERS,
        )
        assert r.status_code == 400, (
            f"BUG: admin pudo desactivarse a sí mismo → {r.status_code} "
            f"(debe ser 400). Respuesta: {r.text[:300]}"
        )
    finally:
        if r is not None and r.status_code == 200:
            # El admin quedó desactivado: reactívalo de inmediato.
            r_restore = client.put(
                f"/api/auth/users/{mi_id}/status",
                params={"activo": True},
                headers=ADMIN_HEADERS,
            )
            assert r_restore.status_code == 200, (
                f"REACTIVACIÓN de emergencia falló → {r_restore.status_code}: {r_restore.text[:300]}"
            )
