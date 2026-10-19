"""Fecha de cotizaciones: la elige quien la crea (el formulario la manda;
fechas pasadas = pasar cotizaciones viejas) y si no se envía o viene null,
el servidor guarda HOY en hora Venezuela (`hoy_ve`).

Antes: el backend exigía `fecha` en el payload (422 si faltaba) y el frontend
mandaba la fecha UTC (de noche en Venezuela saltaba a mañana).
"""
from datetime import timedelta

from app.core.hora_ve import hoy_ve
from conftest import ADMIN_HEADERS, crear_cliente, crear_producto


def _payload(cliente_id, producto_id, **extra):
    payload = {
        "cliente_id": cliente_id,
        "estado": "BORRADOR",
        "total_estimado": 100.0,
        "moneda_id": 1,
        "tasa_cambio": 1.0,
        "detalles": [
            {
                "producto_id": producto_id,
                "cantidad": 1,
                "precio": 100.0,
                "ancho": 1.60,
                "largo": 1.90,
            }
        ],
    }
    payload.update(extra)
    return payload


def test_cotizacion_sin_fecha_guarda_hoy_ve(client, cleaner):
    """Payload sin `fecha` → 201 y se guarda hoy (VE), no un 422."""
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    r = client.post(
        "/api/v1/cotizacion/",
        json=_payload(cliente["id"], prod["id"]),
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    cot = r.json()
    cleaner.registrar("cotizacion", cot["id"])
    assert cot["fecha"] == str(hoy_ve())


def test_cotizacion_fecha_null_guarda_hoy_ve(client, cleaner):
    """`fecha: null` explícito → también se guarda hoy (VE)."""
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    r = client.post(
        "/api/v1/cotizacion/",
        json=_payload(cliente["id"], prod["id"], fecha=None),
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    cot = r.json()
    cleaner.registrar("cotizacion", cot["id"])
    assert cot["fecha"] == str(hoy_ve())


def test_cotizacion_fecha_pasada_se_respeta(client, cleaner):
    """Pasar cotizaciones viejas: la fecha pasada enviada se guarda tal cual."""
    cliente = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    fecha_vieja = hoy_ve() - timedelta(days=15)
    r = client.post(
        "/api/v1/cotizacion/",
        json=_payload(cliente["id"], prod["id"], fecha=str(fecha_vieja)),
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    cot = r.json()
    cleaner.registrar("cotizacion", cot["id"])
    assert cot["fecha"] == str(fecha_vieja)
