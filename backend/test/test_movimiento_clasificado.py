# -*- coding: utf-8 -*-
"""test_movimiento_clasificado.py — Salidas de caja con tipo de gasto.

Cuando se registra una SALIDA desde Cuentas con una clasificación
(G D/C/P/F/I o Préstamo):

  - se crea el Gasto clasificado (aparece en Gastos y reportes),
  - el movimiento de caja lo genera ese gasto (misma cuenta/monto/fecha),
  - la persona/entidad se conserva en el movimiento,
  - en ENTRADAS la clasificación se rechaza (no aplica).

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_movimiento_clasificado.py -v
"""
import uuid
from decimal import Decimal

import pytest

from app.modules.gastos.model import Gasto
from app.modules.gastos.service import normalizar_clasificacion
from app.modules.reports.model import MovimientoCaja
from conftest import ADMIN_HEADERS


def _crear_cuenta(client, cleaner, db):
    codigo = f"TEST_MOV_CLASIF_{uuid.uuid4().hex[:6].upper()}"
    r = client.post("/api/v1/cuenta/", json={
        "nombre": "Cuenta de prueba salida clasificada",
        "codigo": codigo,
        "moneda_id": 1,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    cuenta = r.json()
    cleaner.registrar("metodo_caja", cuenta["id"])
    db.query(MovimientoCaja).filter(
        MovimientoCaja.metodo_caja_id == cuenta["id"],
        MovimientoCaja.referencia == "Saldo inicial por defecto",
    ).delete(synchronize_session=False)
    db.commit()
    return cuenta


def _saldo(db, cuenta_id):
    movs = db.query(MovimientoCaja).filter(MovimientoCaja.metodo_caja_id == cuenta_id).all()
    return sum(
        (-Decimal(str(m.monto)) if m.tipo == "SALIDA" else Decimal(str(m.monto)))
        for m in movs
    )


# ---------------------------------------------------------------------------
# Normalizador (sin base de datos)
# ---------------------------------------------------------------------------
def test_normalizador_acepta_codigos_y_nombres():
    assert normalizar_clasificacion("G D") == "GASTO_DEDUCIBLE"
    assert normalizar_clasificacion("G C") == "GASTO_CASA"
    assert normalizar_clasificacion("G P") == "GASTO_PERSONAL"
    assert normalizar_clasificacion("G F") == "GASTO_FAMILIAR"
    # Decisión 30/10/2026: Familiar y Fábrica son canastas separadas (la
    # F del libro sigue siendo Familiar); los camiones también.
    assert normalizar_clasificacion("Familia") == "GASTO_FAMILIAR"
    assert normalizar_clasificacion("FABRICA") == "GASTO_FABRICA"
    assert normalizar_clasificacion("Gastos de Fábrica") == "GASTO_FABRICA"
    assert normalizar_clasificacion("G FABRICA") == "GASTO_FABRICA"
    assert normalizar_clasificacion("CAMIONES") == "GASTO_CAMIONES"
    assert normalizar_clasificacion("Gastos de Camiones") == "GASTO_CAMIONES"
    assert normalizar_clasificacion("G CAMION") == "GASTO_CAMIONES"
    assert normalizar_clasificacion("G I") == "GASTO_INVERSION"
    assert normalizar_clasificacion("PRESTAMO") == "PRESTAMO"
    assert normalizar_clasificacion("Gasto Préstamo") == "PRESTAMO"
    assert normalizar_clasificacion("IMPUESTO") == "IMPUESTO"
    assert normalizar_clasificacion("Impuestos y Tasas") == "IMPUESTO"
    assert normalizar_clasificacion(None) is None
    with pytest.raises(ValueError):
        normalizar_clasificacion("G X")


# ---------------------------------------------------------------------------
# Alta con clasificación
# ---------------------------------------------------------------------------
def test_salida_clasificada_crea_gasto_y_movimiento(client, cleaner, db):
    cuenta = _crear_cuenta(client, cleaner, db)
    descripcion = f"Pago de luz prueba {uuid.uuid4().hex[:6]}"

    r = client.post(f"/api/v1/cuenta/{cuenta['id']}/movimiento", json={
        "metodo_caja_id": cuenta["id"],
        "fecha": "2026-10-20",
        "tipo": "SALIDA",
        "monto": 100000,
        "moneda_id": 1,
        "persona_entidad": "CAMARA DE COMERCIO",
        "concepto": descripcion,
        "clasificacion": "G C",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    mov = r.json()

    db.expire_all()
    gasto = db.query(Gasto).filter(Gasto.descripcion == descripcion).first()
    assert gasto is not None, "debe crear el Gasto clasificado"
    cleaner.registrar("gasto", gasto.id)
    assert gasto.clasificacion == "GASTO_CASA"
    assert gasto.tipo_gasto is not None and gasto.tipo_gasto.nombre == "Gasto de Casa"
    assert Decimal(str(gasto.monto)) == Decimal("100000")

    assert mov["tipo"] == "SALIDA"
    assert mov["referencia"] == f"Gasto #{gasto.id}"
    assert mov["persona_entidad"] == "CAMARA DE COMERCIO"
    assert mov["concepto"] == descripcion
    cleaner.registrar_caja_ref(mov["referencia"])

    assert _saldo(db, cuenta["id"]) == Decimal("-100000")


def test_salida_impuestos_crea_gasto_impuestos(client, cleaner, db):
    """Salida de caja marcada como Impuestos: crea el Gasto con el motivo
    'Impuestos y Tasas' (el mismo del catálogo) y su movimiento espejo."""
    cuenta = _crear_cuenta(client, cleaner, db)
    descripcion = f"Pago de impuestos prueba {uuid.uuid4().hex[:6]}"

    r = client.post(f"/api/v1/cuenta/{cuenta['id']}/movimiento", json={
        "metodo_caja_id": cuenta["id"],
        "fecha": "2026-10-20",
        "tipo": "SALIDA",
        "monto": 250000,
        "moneda_id": 1,
        "persona_entidad": "CAMARA DE COMERCIO",
        "concepto": descripcion,
        "clasificacion": "IMPUESTO",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    mov = r.json()

    db.expire_all()
    gasto = db.query(Gasto).filter(Gasto.descripcion == descripcion).first()
    assert gasto is not None, "debe crear el Gasto de impuestos"
    cleaner.registrar("gasto", gasto.id)
    assert gasto.clasificacion == "IMPUESTO"
    assert gasto.tipo_gasto is not None
    assert gasto.tipo_gasto.nombre == "Impuestos y Tasas"
    assert Decimal(str(gasto.monto)) == Decimal("250000")

    assert mov["tipo"] == "SALIDA"
    assert mov["referencia"] == f"Gasto #{gasto.id}"
    cleaner.registrar_caja_ref(mov["referencia"])

    assert _saldo(db, cuenta["id"]) == Decimal("-250000")


def test_entrada_con_clasificacion_se_rechaza(client, cleaner, db):
    cuenta = _crear_cuenta(client, cleaner, db)

    r = client.post(f"/api/v1/cuenta/{cuenta['id']}/movimiento", json={
        "metodo_caja_id": cuenta["id"],
        "fecha": "2026-10-20",
        "tipo": "ENTRADA",
        "monto": 50000,
        "moneda_id": 1,
        "concepto": "No debería clasificarse",
        "clasificacion": "GASTO_PERSONAL",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 400, r.text
    assert "solo las salidas" in r.json()["detail"].lower()


def test_salida_con_prestamo_crea_gasto_prestamo(client, cleaner, db):
    cuenta = _crear_cuenta(client, cleaner, db)
    descripcion = f"Préstamo a Lorenzo {uuid.uuid4().hex[:6]}"

    r = client.post(f"/api/v1/cuenta/{cuenta['id']}/movimiento", json={
        "metodo_caja_id": cuenta["id"],
        "fecha": "2026-10-19",
        "tipo": "SALIDA",
        "monto": 3500000,
        "moneda_id": 1,
        "persona_entidad": "LORENZO",
        "concepto": descripcion,
        "clasificacion": "PRESTAMO",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    mov = r.json()

    db.expire_all()
    gasto = db.query(Gasto).filter(Gasto.descripcion == descripcion).first()
    assert gasto is not None
    cleaner.registrar("gasto", gasto.id)
    assert gasto.clasificacion == "PRESTAMO"
    assert gasto.tipo_gasto is not None and gasto.tipo_gasto.nombre == "Préstamo"
    cleaner.registrar_caja_ref(mov["referencia"])


def test_salida_sin_clasificacion_no_crea_gasto(client, cleaner, db):
    cuenta = _crear_cuenta(client, cleaner, db)
    descripcion = f"Salida sin clasificar {uuid.uuid4().hex[:6]}"

    r = client.post(f"/api/v1/cuenta/{cuenta['id']}/movimiento", json={
        "metodo_caja_id": cuenta["id"],
        "fecha": "2026-10-20",
        "tipo": "SALIDA",
        "monto": 45000,
        "moneda_id": 1,
        "concepto": descripcion,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    mov = r.json()
    assert mov["referencia"] is None
    cleaner.registrar("movimiento_caja", mov["id"])

    db.expire_all()
    assert db.query(Gasto).filter(Gasto.descripcion == descripcion).first() is None


def test_editar_movimiento_clasificado_sincroniza_gasto(client, cleaner, db):
    """Corregir el movimiento espejo también corrige el Gasto y los reportes."""
    cuenta = _crear_cuenta(client, cleaner, db)
    descripcion = f"Pago de luz para corregir {uuid.uuid4().hex[:6]}"

    r = client.post(f"/api/v1/cuenta/{cuenta['id']}/movimiento", json={
        "metodo_caja_id": cuenta["id"],
        "fecha": "2026-10-20",
        "tipo": "SALIDA",
        "monto": 100000,
        "moneda_id": 1,
        "persona_entidad": "CAMARA DE COMERCIO",
        "concepto": descripcion,
        "clasificacion": "G C",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    mov = r.json()

    db.expire_all()
    gasto = db.query(Gasto).filter(Gasto.descripcion == descripcion).first()
    assert gasto is not None
    cleaner.registrar("gasto", gasto.id)
    cleaner.registrar_caja_ref(mov["referencia"])

    r = client.put(
        f"/api/v1/cuenta/movimiento/{mov['id']}",
        json={
            "monto": 80000,
            "fecha": "2026-10-21",
            "concepto": "Pago de luz corregido",
            "persona_entidad": "CAMARA DE COMERCIO",
        },
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    gasto = db.query(Gasto).filter(Gasto.id == gasto.id).first()
    assert Decimal(str(gasto.monto)) == Decimal("80000")
    assert gasto.fecha.isoformat() == "2026-10-21"
    assert gasto.descripcion == "Pago de luz corregido"
    assert Decimal(str(gasto.monto_en_moneda_base)) == Decimal("80000")
    assert gasto.observaciones == "Persona/entidad: CAMARA DE COMERCIO"
    assert _saldo(db, cuenta["id"]) == Decimal("-80000")
