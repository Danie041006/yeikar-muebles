"""
test_metodos_caja_permisos.py — El listado de métodos de caja alimenta los
combos de cobro (Ventas → Registrar cobro y Cotizaciones → adelanto de la
conversión). Debe ser accesible a CUALQUIER usuario autenticado: un vendedor
no-admin recibía 403 (el router de /reports exige es_admin) y el frontend
caía en su lista estática vieja — sin Banesco Jackson, Bancolombia Andrea ni
Bancolombia Karolay, y con nombres genéricos ("Zelle" en vez de "Zelle
Blanca Mendoza"). El CRUD de cuentas sigue siendo exclusivo de
Dueño/Administrador.
"""
from conftest import ADMIN_HEADERS, VENTAS_HEADERS

URL = "/api/v1/reports/metodos-caja"


def test_listar_metodos_caja_como_vendedor_no_admin(client):
    r = client.get(URL, headers=VENTAS_HEADERS)
    assert r.status_code == 200, r.text
    filas = r.json()
    assert isinstance(filas, list) and len(filas) > 0
    # El combo del frontend necesita estos campos para armar la opción
    # (value=codigo, label=nombre, moneda) y auto-seleccionar la moneda.
    fila = filas[0]
    for campo in ("id", "nombre", "codigo", "activo", "moneda_codigo"):
        assert campo in fila


def test_listar_metodos_caja_como_admin(client):
    r = client.get(URL, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text


def test_listar_metodos_caja_sin_token_es_401(client):
    r = client.get(URL)
    assert r.status_code == 401


def test_vendedor_no_admin_no_puede_mutar_cuentas(client):
    # El GET abierto no debe abrir la puerta al CRUD de cuentas.
    r = client.post(URL, headers=VENTAS_HEADERS, json={
        "nombre": "test_no_debe_crearse", "codigo": "TEST_NO_DEBE",
        "activo": True, "orden": 999,
    })
    assert r.status_code == 403, r.text

    r = client.put(f"{URL}/1", headers=VENTAS_HEADERS, json={"nombre": "test_hack"})
    assert r.status_code == 403, r.text

    r = client.delete(f"{URL}/1", headers=VENTAS_HEADERS)
    assert r.status_code == 403, r.text


def test_admin_sigue_creando_cuentas(client, cleaner):
    r = client.post(URL, headers=ADMIN_HEADERS, json={
        "nombre": "test_metodo_admin", "codigo": "TEST_METODO_ADMIN",
        "activo": True, "orden": 998,
    })
    assert r.status_code == 201, r.text
    cleaner.registrar("metodo_caja", r.json()["id"])


# ---------------------------------------------------------------------------
# Catálogo mínimo de cuentas para formularios operativos
# ---------------------------------------------------------------------------
URL_OPERATIVAS = "/api/v1/cuenta/operativas"


def test_cuentas_operativas_traen_nombre_y_moneda_sin_saldos(client):
    """Quien registra inventario/gastos necesita elegir la cuenta de la que
    salió el dinero, pero NO debe recibir saldos ni movimientos."""
    r = client.get(URL_OPERATIVAS, headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    filas = r.json()
    assert isinstance(filas, list) and len(filas) > 0
    fila = filas[0]
    for campo in ("id", "nombre", "moneda_id", "moneda_codigo"):
        assert campo in fila
    assert "saldo_por_moneda" not in fila


def test_cuentas_operativas_exigen_un_modulo_operativo(client):
    # El rol Ventas no tiene inventario/gastos/compras/nómina: no ve cuentas.
    r = client.get(URL_OPERATIVAS, headers=VENTAS_HEADERS)
    assert r.status_code == 403, r.text


def test_cuentas_operativas_sin_token_es_401(client):
    r = client.get(URL_OPERATIVAS)
    assert r.status_code == 401
