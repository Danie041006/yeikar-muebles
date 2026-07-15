#!/usr/bin/env python3
"""
YEIKAR API - Suite de Pruebas de Integración
Tests automáticos para: Auth, Filtros de Fecha, Endpoints de Usuarios Admin
"""
import sys
import requests
import json
from datetime import datetime

BASE = "http://localhost:8000"
PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS = []

def ok(name):
    global PASS_COUNT
    PASS_COUNT += 1
    RESULTS.append(f"  ✅  {name}")

def fail(name, detail=""):
    global FAIL_COUNT
    FAIL_COUNT += 1
    RESULTS.append(f"  ❌  {name}" + (f"\n      → {detail}" if detail else ""))

def section(title):
    RESULTS.append(f"\n{'─'*55}")
    RESULTS.append(f"  {title}")
    RESULTS.append(f"{'─'*55}")

# ─── Auth ──────────────────────────────────────────────────────────────────────
section("1. AUTENTICACIÓN")

r = requests.get(f"{BASE}/")
if r.status_code == 200 and "Welcome" in r.text:
    ok("GET /  →  API responde correctamente")
else:
    fail("GET /  →  API no responde", r.text[:80])

# Login con credenciales correctas
r = requests.post(f"{BASE}/api/auth/login", data={"username": "carolina", "password": "carolina2025$"})
if r.status_code == 200:
    tok = r.json()
    ACCESS  = tok.get("access_token")
    REFRESH = tok.get("refresh_token")
    ok("POST /api/auth/login  →  Token obtenido")
else:
    fail("POST /api/auth/login  →  Login fallido", r.text[:120])
    ACCESS = REFRESH = None

if not ACCESS:
    print("\n".join(RESULTS))
    sys.exit(1)

H = {"Authorization": f"Bearer {ACCESS}"}

# GET /me
r = requests.get(f"{BASE}/api/auth/me", headers=H)
if r.status_code == 200 and r.json().get("nombre_usuario") == "carolina":
    ok("GET /api/auth/me  →  Usuario cargado correctamente")
else:
    fail("GET /api/auth/me", r.text[:80])

# Login con credenciales incorrectas → 401
r = requests.post(f"{BASE}/api/auth/login", data={"username": "carolina", "password": "wrong"})
if r.status_code == 401:
    ok("POST /api/auth/login (credenciales incorrectas)  →  401 retornado")
else:
    fail("POST /api/auth/login (credenciales incorrectas)", f"status={r.status_code}")

# Refresh token
r = requests.post(f"{BASE}/api/auth/refresh", json={"refresh_token": REFRESH})
if r.status_code == 200 and "access_token" in r.json():
    ok("POST /api/auth/refresh  →  Token renovado")
else:
    fail("POST /api/auth/refresh", r.text[:80])

# ─── User Management Endpoints ────────────────────────────────────────────────
section("2. GESTIÓN DE USUARIOS (Admin)")

# List all users
r = requests.get(f"{BASE}/api/auth/users", headers=H)
if r.status_code == 200 and isinstance(r.json(), list):
    users = r.json()
    ok(f"GET /api/auth/users  →  {len(users)} usuarios listados")
else:
    fail("GET /api/auth/users", r.text[:80])
    users = []

# List roles
r = requests.get(f"{BASE}/api/auth/roles", headers=H)
if r.status_code == 200 and isinstance(r.json(), list):
    roles = r.json()
    ok(f"GET /api/auth/roles  →  {len(roles)} roles listados: {[rr['nombre'] for rr in roles]}")
else:
    fail("GET /api/auth/roles", r.text[:80])
    roles = []

# Create a test user
ts = int(datetime.now().timestamp())
TEST_USER = f"test_user_{ts}"
r = requests.post(f"{BASE}/api/auth/users", headers=H, json={
    "nombre_usuario": TEST_USER,
    "email": f"{TEST_USER}@yeikar.com",
    "password": "TestPass123"
})
if r.status_code == 201:
    new_user = r.json()
    new_uid = new_user["id"]
    ok(f"POST /api/auth/users  →  Usuario '{TEST_USER}' creado (ID={new_uid})")
else:
    fail("POST /api/auth/users", r.text[:120])
    new_uid = None

if new_uid:
    # Toggle status to inactive
    r = requests.put(f"{BASE}/api/auth/users/{new_uid}/status", headers=H, params={"activo": "false"})
    if r.status_code == 200 and r.json()["activo"] == False:
        ok(f"PUT /api/auth/users/{new_uid}/status  →  Usuario desactivado")
    else:
        fail(f"PUT /api/auth/users/{new_uid}/status", r.text[:80])

    # Toggle status back to active
    r = requests.put(f"{BASE}/api/auth/users/{new_uid}/status", headers=H, params={"activo": "true"})
    if r.status_code == 200 and r.json()["activo"] == True:
        ok(f"PUT /api/auth/users/{new_uid}/status  →  Usuario reactivado")
    else:
        fail(f"PUT /api/auth/users/{new_uid}/status", r.text[:80])

    # Assign role (use first available role)
    if roles:
        rid = roles[0]["id"]
        r = requests.post(f"{BASE}/api/auth/usuario/{new_uid}/roles/{rid}", headers=H)
        if r.status_code == 200:
            ok(f"POST /api/auth/usuario/{new_uid}/roles/{rid}  →  Rol '{roles[0]['nombre']}' asignado")
        else:
            fail(f"POST /api/auth/usuario/{new_uid}/roles/{rid}", r.text[:80])

        # Remove role
        r = requests.delete(f"{BASE}/api/auth/usuario/{new_uid}/roles/{rid}", headers=H)
        if r.status_code == 200:
            ok(f"DELETE /api/auth/usuario/{new_uid}/roles/{rid}  →  Rol revocado")
        else:
            fail(f"DELETE /api/auth/usuario/{new_uid}/roles/{rid}", r.text[:80])

    # Delete test user
    r = requests.delete(f"{BASE}/api/auth/users/{new_uid}", headers=H)
    if r.status_code == 204:
        ok(f"DELETE /api/auth/users/{new_uid}  →  Usuario de prueba eliminado")
    else:
        fail(f"DELETE /api/auth/users/{new_uid}", r.text[:80])

# ─── Date Filtering ───────────────────────────────────────────────────────────
section("3. FILTROS HISTÓRICOS (Cotizaciones y Pedidos)")

now = datetime.now()

# Cotizaciones default (solo_mes_actual=True)
r = requests.get(f"{BASE}/api/v1/cotizacion/", headers=H, params={"solo_mes_actual": "true"})
if r.status_code == 200:
    data = r.json()
    ok(f"GET /cotizacion/?solo_mes_actual=true  →  {len(data)} cotizaciones del mes actual")
else:
    fail("GET /cotizacion/?solo_mes_actual=true", r.text[:80])

# Cotizaciones all history
r = requests.get(f"{BASE}/api/v1/cotizacion/", headers=H, params={"solo_mes_actual": "false"})
if r.status_code == 200:
    data_all = r.json()
    ok(f"GET /cotizacion/?solo_mes_actual=false  →  {len(data_all)} cotizaciones históricas")
else:
    fail("GET /cotizacion/?solo_mes_actual=false", r.text[:80])

# Cotizaciones by specific month/year
r = requests.get(f"{BASE}/api/v1/cotizacion/", headers=H, params={"mes": now.month, "anio": now.year})
if r.status_code == 200:
    ok(f"GET /cotizacion/?mes={now.month}&anio={now.year}  →  Filtro por mes/año funciona")
else:
    fail(f"GET /cotizacion/?mes={now.month}&anio={now.year}", r.text[:80])

# Pedidos default (solo_mes_actual=True)
r = requests.get(f"{BASE}/api/v1/pedido/", headers=H, params={"solo_mes_actual": "true"})
if r.status_code == 200:
    data = r.json()
    ok(f"GET /pedido/?solo_mes_actual=true  →  {len(data)} pedidos del mes actual")
else:
    fail("GET /pedido/?solo_mes_actual=true", r.text[:80])

# Pedidos all history
r = requests.get(f"{BASE}/api/v1/pedido/", headers=H, params={"solo_mes_actual": "false"})
if r.status_code == 200:
    data_all = r.json()
    ok(f"GET /pedido/?solo_mes_actual=false  →  {len(data_all)} pedidos históricos")
else:
    fail("GET /pedido/?solo_mes_actual=false", r.text[:80])

# Pedidos by specific month/year
r = requests.get(f"{BASE}/api/v1/pedido/", headers=H, params={"mes": now.month, "anio": now.year})
if r.status_code == 200:
    ok(f"GET /pedido/?mes={now.month}&anio={now.year}  →  Filtro por mes/año funciona")
else:
    fail(f"GET /pedido/?mes={now.month}&anio={now.year}", r.text[:80])

# ─── Summary ──────────────────────────────────────────────────────────────────
RESULTS.append(f"\n{'═'*55}")
RESULTS.append(f"  RESULTADO FINAL: {PASS_COUNT + FAIL_COUNT} pruebas ejecutadas")
RESULTS.append(f"  ✅  Aprobadas : {PASS_COUNT}")
RESULTS.append(f"  ❌  Fallidas  : {FAIL_COUNT}")
RESULTS.append(f"{'═'*55}\n")

print("\n".join(RESULTS))
sys.exit(0 if FAIL_COUNT == 0 else 1)
