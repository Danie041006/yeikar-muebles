# -*- coding: utf-8 -*-
"""
test_ataques_dinero.py — Pentest de la lógica de dinero y validación de YEIKAR.

No arregla nada: cada test intenta un ataque y exige la respuesta correcta
(4xx claro / invariante intacta). Si el sistema ACEPTA lo indebido o devuelve
500, el test FALLA con un print de reproducción exacta (endpoint, payload,
status, respuesta) y documenta el bug en el reporte.

Áreas atacadas:
  1. Tasas de cambio absurdas en pagos (0, negativa, 1e15, irrealmente baja)
  2. Adelanto > total en la conversión de cotización (200%)
  3. Adelanto en moneda distinta sin tasa_cambio_adelanto
  4. Montos con 3+ decimales / micro-montos en pagos
  5. Devoluciones: más de lo pagado, venta sin pagos, devolución duplicada
  6. Mass assignment / FKs inexistentes en gastos
  7. Empleado con sueldo_semanal gigante / negativo (PUT)
  8. Concepto vario de nómina negativo / gigante
  9. Línea manual de nómina con precio_unitario negativo / gigante
 10. Fuzzing de tipos en pago / gasto / convertir (buscar 500)
 11. Nómina FIJO: ¿snapshot o cambio retroactivo al editar el sueldo?

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_ataques_dinero.py -v
"""
import sys
import uuid
from datetime import datetime, date

import pytest
from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_producto,
    crear_cotizacion,
    registrar_venta_de_pedido,
)

sys.path.insert(0, __import__("os").path.dirname(__file__))


# ---------------------------------------------------------------------------
# Helpers locales (todo registrado en el cleaner para no dejar rastro)
# ---------------------------------------------------------------------------
def _uniq(prefix: str) -> str:
    return f"test_{prefix}_{uuid.uuid4().hex[:8]}"


def _convertir(client, cleaner, cot_id, producto_id, precio, *,
               adelanto=None, moneda_adelanto_id=None, tasa_cambio_adelanto=None,
               metodo_pago=None):
    """Convierte una cotización a pedido. Registra el pedido si se creó."""
    body = {
        "detalles": [{
            "producto_id": producto_id,
            "cantidad": 1,
            "precio": precio,
            "costo_unitario": 1000,
            "porcentaje_ganancia": 40,
        }],
        "adelanto": adelanto,
        "moneda_adelanto_id": moneda_adelanto_id,
        "tasa_cambio_adelanto": tasa_cambio_adelanto,
        "metodo_pago": metodo_pago,
    }
    r = client.post(f"/api/v1/pedido/convertir/{cot_id}", json=body, headers=ADMIN_HEADERS)
    if r.status_code == 201:
        cleaner.registrar("pedido", r.json()["id"])
    return r


def _venta_de_pedido(client, cleaner, db, pedido_id):
    """Factura auto-generada del pedido, registrada para limpieza."""
    r = client.get("/api/v1/venta/", headers=ADMIN_HEADERS)
    venta_id = None
    if r.status_code == 200:
        for v in r.json():
            if v["pedido_id"] == pedido_id:
                venta_id = v["id"]
                break
    if venta_id is None:
        row = db.execute(text("SELECT id FROM venta WHERE pedido_id=:p"), {"p": pedido_id}).fetchone()
        venta_id = int(row[0]) if row else None
    if venta_id is None:
        return None
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    if det.status_code == 200:
        cleaner.registrar("venta", venta_id)
        for d in det.json().get("detalles", []):
            cleaner.registrar("detalle_venta", d["id"])
        for p in det.json().get("pagos", []):
            cleaner.registrar("pago", p["id"])
    return det.json()


def _setup_venta(client, cleaner, db, precio=100000, moneda_id=1, tasa_cambio=1.0,
                 adelanto=None, moneda_adelanto_id=None, metodo_pago=None):
    """Cliente + producto + cotización + conversión. Devuelve dict con ids."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], precio,
                           moneda_id=moneda_id, tasa_cambio=tasa_cambio)
    r = _convertir(client, cleaner, cot["id"], prod["id"], precio,
                   adelanto=adelanto, moneda_adelanto_id=moneda_adelanto_id,
                   metodo_pago=metodo_pago)
    assert r.status_code == 201, f"setup convertir → {r.status_code}: {r.text}"
    pedido = r.json()
    venta = _venta_de_pedido(client, cleaner, db, pedido["id"])
    assert venta, "setup: no se generó factura"
    return {"cliente": cli, "producto": prod, "cotizacion": cot,
            "pedido": pedido, "venta": venta}


def _crear_empleado(client, cleaner, *, tipo_pago="FIJO", sueldo=None):
    payload = {
        "nombre": _uniq("emp"),
        "cargo_id": 1,
        "telefono": "555-7777",
        "activo": True,
        "en_nomina": True,
        "tipo_pago": tipo_pago,
    }
    if sueldo is not None:
        payload["sueldo_semanal"] = sueldo
    r = client.post("/api/v1/empleado/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_empleado → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("empleado", body["id"])
    return body


def _crear_nomina(client, cleaner, semana, descripcion):
    """Crea una nómina de NOVIEMBRE 2026 para la semana 'MM-DD..MM-DD'."""
    desde, hasta = semana
    r = client.post("/api/v1/nomina/", json={
        "periodo_desde": desde,
        "periodo_hasta": hasta,
        "descripcion": f"{descripcion} ({_uniq('nom')})",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_nomina → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("nomina", body["id"])
    return body


def _detalle_de(nomina, empleado_id):
    for d in nomina["detalles"]:
        if d["empleado_id"] == empleado_id:
            return d
    return None


# ===========================================================================
# 1) Tasas de cambio absurdas en pagos (VES sobre factura COP)
# ===========================================================================
def test_pago_ves_tasa_cero_negativa_gigante_rechazado(client, db, cleaner):
    """Pago en VES con tasa_cambio 0 / -5 / 1e15 debe ser 4xx (nunca 201) y
    no debe tocar la caja ni el saldo de la venta."""
    st = _setup_venta(client, cleaner, db, precio=100000)
    venta = st["venta"]
    base = {
        "venta_id": venta["id"],
        "moneda_id": 3,                       # VES
        "fecha": datetime.utcnow().isoformat(),
        "monto": 100,
        "metodo_pago": "EFECTIVO_VES",
    }
    for tasa in (0, -5, 1e15):
        r = client.post("/api/v1/pago/", json={**base, "tasa_cambio": tasa}, headers=ADMIN_HEADERS)
        print(f"  pago VES tasa={tasa} → status={r.status_code} body={r.text[:200]}")
        assert r.status_code in (400, 422), (
            f"BUG: pago VES con tasa {tasa} ACEPTADO ({r.status_code}) — monto_en_moneda_base "
            f"corrompido: {r.text[:300]}"
        )
    # Verificar invariantes: 0 pagos nuevos, caja intacta
    n_pagos = db.execute(text("SELECT count(*) FROM pago WHERE venta_id=:v"),
                         {"v": venta["id"]}).fetchone()[0]
    assert n_pagos == 0, f"BUG: se crearon pagos ({n_pagos}) pese al rechazo"
    n_mov = db.execute(text(
        "SELECT count(*) FROM movimiento_caja mc JOIN pago p ON p.id=mc.pago_id WHERE p.venta_id=:v"
    ), {"v": venta["id"]}).fetchone()[0]
    assert n_mov == 0, f"BUG: hay movimientos de caja ({n_mov}) pese al rechazo"
    print("  → PASS: tasas 0/negativa/gigante rechazadas, saldo y caja intactos")


def test_pago_moneda_extranjera_tasa_irrealmente_baja_aceptada(client, db, cleaner):
    """Documentar: pago VES con tasa 0.001 (pasa el mínimo 0.0001) sobre factura
    COP — el cobro entra a caja por centavos mientras físicamente se recibe VES.
    Este es el comportamiento ACTUAL; si el sistema lo acepta, es un bug."""
    st = _setup_venta(client, cleaner, db, precio=100000)
    venta = st["venta"]
    r = client.post("/api/v1/pago/", json={
        "venta_id": venta["id"],
        "moneda_id": 3,
        "fecha": datetime.utcnow().isoformat(),
        "monto": 1000,                       # 1000 VES recibidos
        "tasa_cambio": 0.001,                # irreal: 1000 VES = 1 COP
        "metodo_pago": "EFECTIVO_VES",
    }, headers=ADMIN_HEADERS)
    print(f"  pago VES monto=1000 tasa=0.001 → status={r.status_code} body={r.text[:300]}")
    if r.status_code == 201:
        pago = r.json()
        cleaner.registrar("pago", pago["id"])
        mov = db.execute(text(
            "SELECT monto, moneda_id, tasa_cambio, monto_en_moneda_base FROM movimiento_caja "
            "WHERE pago_id=:p"
        ), {"p": pago["id"]}).fetchone()
        print(f"  → BUG: pago ACEPTADO con tasa irreal; movimiento de caja={mov}")
        assert r.status_code in (400, 422), (
            f"BUG: pago VES con tasa 0.001 ACEPTADO ({r.status_code}) — el cobro queda "
            f"valuado en centavos en caja; se requiere validar contra la tasa vigente"
        )
    else:
        assert r.status_code in (400, 422), f"status inesperado: {r.status_code} {r.text[:200]}"
        print("  → PASS: tasa irrealmente baja rechazada")


# ===========================================================================
# 2) Adelanto mayor que el total (200%) al convertir
# ===========================================================================
def test_adelanto_200_porciento_rechazado(client, db, cleaner):
    """Adelanto = 200% del total debe ser 400 y NO crear pedido ni saldo negativo."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100000)
    r = _convertir(client, cleaner, cot["id"], prod["id"], 100000,
                   adelanto=200000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    print(f"  convertir adelanto=200000 (total 100000) → status={r.status_code} body={r.text[:300]}")
    assert r.status_code == 400, (
        f"BUG: adelanto del 200% ACEPTADO ({r.status_code}) → saldo de la venta quedaría "
        f"negativo: {r.text[:300]}"
    )
    n_pedidos = db.execute(text("SELECT count(*) FROM pedido WHERE cotizacion_id=:c"),
                           {"c": cot["id"]}).fetchone()[0]
    n_pagos = db.execute(text(
        "SELECT count(*) FROM pago p JOIN venta v ON v.id=p.venta_id JOIN pedido o ON o.id=v.pedido_id "
        "WHERE o.cotizacion_id=:c"
    ), {"c": cot["id"]}).fetchone()[0]
    assert n_pedidos == 0 and n_pagos == 0, (
        f"BUG: conversión rechazada dejó rastro: pedidos={n_pedidos} pagos={n_pagos}"
    )
    print("  → PASS: adelanto > total rechazado, sin pedido ni saldo negativo")


# ===========================================================================
# 3) Adelanto en moneda distinta sin tasa_cambio_adelanto
# ===========================================================================
def test_adelanto_moneda_distinta_sin_tasa_es_400(client, db, cleaner):
    """Adelanto en VES sobre factura USD sin tasa_cambio_adelanto → 400 claro
    (no 500) y sin pedido creado."""
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 500,
                           moneda_id=2, tasa_cambio=3900)
    r = _convertir(client, cleaner, cot["id"], prod["id"], 500,
                   adelanto=1000, moneda_adelanto_id=3, metodo_pago="EFECTIVO_VES")
    print(f"  convertir adelanto VES sin TRM → status={r.status_code} body={r.text[:300]}")
    assert r.status_code == 400, (
        f"BUG: adelanto en otra moneda sin tasa aceptado ({r.status_code}) o 500: {r.text[:300]}"
    )
    detail = (r.json().get("detail", "") if r.status_code == 400 else "").lower()
    assert "tasa" in detail or "trm" in detail, (
        f"BUG: el mensaje no es claro sobre la tasa requerida: {r.text[:300]}"
    )
    n_pedidos = db.execute(text("SELECT count(*) FROM pedido WHERE cotizacion_id=:c"),
                           {"c": cot["id"]}).fetchone()[0]
    assert n_pedidos == 0, f"BUG: se creó pedido pese al rechazo (n={n_pedidos})"
    print("  → PASS: moneda distinta sin tasa → 400 claro, sin rastro")


# ===========================================================================
# 4) Montos con 3+ decimales / micro-montos en pagos
# ===========================================================================
def test_pago_micro_montos_aceptados(client, db, cleaner):
    """Pago de 0.001 / 1e-9 COP sobre factura COP: el sistema lo acepta (la
    columna numeric(15,2) lo redondea a 0.00). Documentar si no hay rechazo."""
    st = _setup_venta(client, cleaner, db, precio=100000)
    venta = st["venta"]
    base = {
        "venta_id": venta["id"],
        "moneda_id": 1,
        "fecha": datetime.utcnow().isoformat(),
        "metodo_pago": "EFECTIVO_COP",
    }
    for monto in (0.001, 1e-9):
        r = client.post("/api/v1/pago/", json={**base, "monto": monto}, headers=ADMIN_HEADERS)
        print(f"  pago monto={monto} → status={r.status_code} body={r.text[:250]}")
        if r.status_code == 201:
            cleaner.registrar("pago", r.json()["id"])
            # estado de la venta / saldo coherente?
            v2 = client.get(f"/api/v1/venta/{venta['id']}", headers=ADMIN_HEADERS).json()
            print(f"    venta tras pago: estado={v2['estado']} pagado={v2['total_pagado']} "
                  f"saldo={v2['saldo_pendiente']}")
            assert r.status_code in (400, 422), (
                f"BUG: pago micro ({monto}) ACEPTADO ({r.status_code}) — se registra un pago "
                f"fantasma de valor ~0 que contamina saldos/caja sin aportar dinero real"
            )
        else:
            assert r.status_code in (400, 422), f"status inesperado: {r.status_code}"
    # Coherencia del saldo tras micro-pagos aceptados
    n_pagos = db.execute(text("SELECT count(*) FROM pago WHERE venta_id=:v"),
                         {"v": venta["id"]}).fetchone()[0]
    print(f"  pagos fantasma registrados: {n_pagos} (venta total 100000)")
    if n_pagos > 0:
        print(f"  → BUG: {n_pagos} micro-pago(s) quedaron persistidos (monto redondeado a 0.00 en numeric(15,2))")
        pytest.fail(f"BUG: se aceptaron {n_pagos} pagos micro (0.001/1e-9) — quedan pagos fantasma")


# ===========================================================================
# 5) Devoluciones de venta
# ===========================================================================
def _crear_devolucion(client, cleaner, venta_id, monto, moneda_id=1, tasa=1.0):
    r = client.post("/api/v1/reports/devoluciones", json={
        "venta_id": venta_id,
        "fecha": str(date.today()),
        "monto_devuelto": monto,
        "moneda_id": moneda_id,
        "tasa_cambio": tasa,
        "motivo": "test devolucion",
    }, headers=ADMIN_HEADERS)
    if r.status_code == 201:
        cleaner.registrar("devolucion_venta", r.json()["id"])
        cleaner.registrar_caja_ref(f"Devolución venta #{venta_id}")
    return r


def test_devolucion_mas_de_lo_pagado_rechazada(client, db, cleaner):
    """Devolver más de lo cobrado → 400 (el check existe)."""
    st = _setup_venta(client, cleaner, db, precio=100000,
                      adelanto=100000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    venta = st["venta"]
    assert venta["estado"] == "PAGADA"
    r = _crear_devolucion(client, cleaner, venta["id"], 100001)
    print(f"  devolución 100001 sobre 100000 cobrado → status={r.status_code} body={r.text[:300]}")
    assert r.status_code == 400, (
        f"BUG: devolución por más de lo pagado ACEPTADA ({r.status_code}) → se reembolsa "
        f"dinero que no entró: {r.text[:300]}"
    )
    print("  → PASS: devolver más de lo pagado rechazado")


def test_devolucion_venta_sin_pagos_rechazada(client, db, cleaner):
    """Devolver de una venta sin pagos → 400 (nada que reembolsar)."""
    st = _setup_venta(client, cleaner, db, precio=100000)
    venta = st["venta"]
    assert venta["estado"] == "PENDIENTE"
    r = _crear_devolucion(client, cleaner, venta["id"], 10000)
    print(f"  devolución 10000 sobre venta sin pagos → status={r.status_code} body={r.text[:300]}")
    assert r.status_code == 400, (
        f"BUG: devolución sobre venta sin pagos ACEPTADA ({r.status_code}) → egreso de caja "
        f"sin ingreso previo: {r.text[:300]}"
    )
    print("  → PASS: devolución de venta sin pagos rechazada")


def test_devolucion_duplicada_aceptada(client, db, cleaner):
    """Devolución DUPLICADA de la misma venta: cada una valida contra el total
    cobrado (no descuenta devoluciones previas) → se puede reembolsar 2×.
    Si la 2ª devolución es aceptada, es un bug de doble reembolso."""
    st = _setup_venta(client, cleaner, db, precio=100000,
                      adelanto=100000, moneda_adelanto_id=1, metodo_pago="EFECTIVO_COP")
    venta = st["venta"]
    assert venta["estado"] == "PAGADA"
    r1 = _crear_devolucion(client, cleaner, venta["id"], 100000)
    print(f"  devolución #1 (100000) → status={r1.status_code} body={r1.text[:200]}")
    assert r1.status_code == 201, f"precondición falló: {r1.status_code} {r1.text[:200]}"
    r2 = _crear_devolucion(client, cleaner, venta["id"], 100000)
    print(f"  devolución #2 duplicada (100000) → status={r2.status_code} body={r2.text[:200]}")
    assert r2.status_code == 400, (
        f"BUG: devolución duplicada ACEPTADA ({r2.status_code}) — la 2ª devolución de 100000 "
        f"se valida solo contra el total cobrado (100000) sin restar la 1ª devolución, "
        f"permitiendo reembolsar 200000 por una venta de 100000 (doble egreso de caja)"
    )
    print("  → PASS: devolución duplicada rechazada")


# ===========================================================================
# 6) Mass assignment / FKs inexistentes en gastos
# ===========================================================================
def test_gasto_ids_inexistentes_son_4xx(client, cleaner):
    """area_id / moneda_id / tipo_gasto_id / metodo_caja_id inexistentes → 400,
    nunca 500."""
    casos = [
        {"area_id": 999999},
        {"moneda_id": 999999},
        {"tipo_gasto_id": 999999},
        {"metodo_caja_id": 999999},
    ]
    for extra in casos:
        payload = {
            "tipo_gasto_id": 1,
            "moneda_id": 1,
            "fecha": str(date.today()),
            "monto": 100,
            "descripcion": _uniq("gasto"),
            **extra,
        }
        r = client.post("/api/v1/gasto/gastos/", json=payload, headers=ADMIN_HEADERS)
        print(f"  gasto {extra} → status={r.status_code} body={r.text[:200]}")
        assert r.status_code == 400, (
            f"BUG: gasto con {extra} → {r.status_code} (esperado 400). "
            f"Si es 500, hay un fallo de validación: {r.text[:300]}"
        )
    print("  → PASS: FKs inexistentes en gastos → 400 limpio")


# ===========================================================================
# 7) Empleado con sueldo_semanal gigante / negativo
# ===========================================================================
def test_empleado_sueldo_semanal_gigante_y_negativo(client, cleaner):
    """PUT sueldo_semanal: negativo debe ser 422; 1e12 debe rechazarse (no hay
    límite superior → infla la nómina semanal)."""
    emp = _crear_empleado(client, cleaner, tipo_pago="FIJO", sueldo=500000)
    # negativo
    r = client.put(f"/api/v1/empleado/{emp['id']}", json={"sueldo_semanal": -100}, headers=ADMIN_HEADERS)
    print(f"  PUT sueldo_semanal=-100 → status={r.status_code} body={r.text[:200]}")
    assert r.status_code in (400, 422), (
        f"BUG: sueldo negativo ACEPTADO ({r.status_code}) → la nómina pagaría salarios negativos"
    )
    # gigante
    r = client.put(f"/api/v1/empleado/{emp['id']}", json={"sueldo_semanal": 1e12}, headers=ADMIN_HEADERS)
    print(f"  PUT sueldo_semanal=1e12 → status={r.status_code} body={r.text[:300]}")
    assert r.status_code in (400, 422), (
        f"BUG: sueldo_semanal de 1e12 ACEPTADO ({r.status_code}) — el salario semanal "
        f"gigante infla la nómina de TODOS los periodos futuros y no hay límite superior"
    )
    # verificar que no quedó corrompido
    r = client.get(f"/api/v1/empleado/{emp['id']}", headers=ADMIN_HEADERS)
    sueldo = r.json().get("sueldo_semanal")
    print(f"  sueldo_semanal final = {sueldo}")
    assert float(sueldo or 0) <= 500000, f"BUG: sueldo quedó en {sueldo}"
    print("  → PASS: sueldo negativo y gigante rechazados")


def test_crear_empleado_sueldo_gigante(client, cleaner):
    """POST /empleado/ con sueldo_semanal gigante también debe rechazarse."""
    r = client.post("/api/v1/empleado/", json={
        "nombre": _uniq("empgig"),
        "cargo_id": 1,
        "en_nomina": True,
        "tipo_pago": "FIJO",
        "sueldo_semanal": 999999999999,
    }, headers=ADMIN_HEADERS)
    print(f"  POST empleado sueldo=999999999999 → status={r.status_code} body={r.text[:300]}")
    if r.status_code == 201:
        cleaner.registrar("empleado", r.json()["id"])
    assert r.status_code in (400, 422), (
        f"BUG: empleado creado con sueldo de ~1e12 ({r.status_code}) → cada nómina semanal "
        f"pagaría ese monto automáticamente"
    )
    print("  → PASS: creación con sueldo gigante rechazada")


# ===========================================================================
# 8) Concepto vario de nómina negativo / gigante
# ===========================================================================
def test_nomina_concepto_vario_negativo_y_gigante(client, cleaner):
    """Concepto vario: negativo → 422; gigante (1e12) → no debe inflar total_nomina."""
    nom = _crear_nomina(client, cleaner, ("2026-11-02", "2026-11-08"), "concepto")
    total_antes = float(nom["total_nomina"])
    # negativo
    r = client.post(f"/api/v1/nomina/{nom['id']}/concepto-vario", json={
        "descripcion": "test negativo", "monto": -1000000,
    }, headers=ADMIN_HEADERS)
    print(f"  concepto -1000000 → status={r.status_code} body={r.text[:200]}")
    assert r.status_code in (400, 422), (
        f"BUG: concepto vario NEGATIVO ACEPTADO ({r.status_code}) → baja el total a pagar"
    )
    # gigante
    r = client.post(f"/api/v1/nomina/{nom['id']}/concepto-vario", json={
        "descripcion": "test gigante", "monto": 1e12,
    }, headers=ADMIN_HEADERS)
    print(f"  concepto 1e12 → status={r.status_code} body={r.text[:300]}")
    assert r.status_code in (400, 422), (
        f"BUG: concepto vario de 1e12 ACEPTADO ({r.status_code}) → el total de la nómina "
        f"se dispara en un billón (pago de dinero inexistente)"
    )
    total_despues = float(client.get(f"/api/v1/nomina/{nom['id']}", headers=ADMIN_HEADERS).json()["total_nomina"])
    assert total_despues == total_antes, (
        f"BUG: el total de la nómina cambió {total_antes} → {total_despues}"
    )
    print("  → PASS: concepto vario negativo/gigante rechazado, total intacto")


# ===========================================================================
# 9) Línea manual de nómina con precio_unitario negativo / gigante
# ===========================================================================
def test_nomina_linea_manual_precio_gigante_y_negativo(client, cleaner):
    """Línea manual de destajo: precio_unitario negativo → 422; gigante → no
    debe inflar el monto a pagar del empleado."""
    emp = _crear_empleado(client, cleaner, tipo_pago="DESTAJO")
    nom = _crear_nomina(client, cleaner, ("2026-11-09", "2026-11-15"), "linea manual")
    det = _detalle_de(nom, emp["id"])
    assert det, "el empleado DESTAJO no aparece en la nómina"
    # negativo
    r = client.post(f"/api/v1/nomina/detalle/{det['id']}/linea", json={
        "descripcion": "test neg", "cantidad": 1, "precio_unitario": -1,
    }, headers=ADMIN_HEADERS)
    print(f"  línea precio=-1 → status={r.status_code} body={r.text[:200]}")
    assert r.status_code in (400, 422), (
        f"BUG: línea manual con precio_unitario NEGATIVO ACEPTADA ({r.status_code})"
    )
    # gigante
    r = client.post(f"/api/v1/nomina/detalle/{det['id']}/linea", json={
        "descripcion": "test gig", "cantidad": 1, "precio_unitario": 1e12,
    }, headers=ADMIN_HEADERS)
    print(f"  línea precio=1e12 → status={r.status_code} body={r.text[:300]}")
    assert r.status_code in (400, 422), (
        f"BUG: línea manual de 1e12 ACEPTADA ({r.status_code}) → el monto a pagar del "
        f"destajo se infla en un billón sin validación de tope"
    )
    nom2 = client.get(f"/api/v1/nomina/{nom['id']}", headers=ADMIN_HEADERS).json()
    det2 = _detalle_de(nom2, emp["id"])
    assert float(det2["monto_a_pagar"]) <= 0.01, (
        f"BUG: monto_a_pagar del destajo quedó en {det2['monto_a_pagar']}"
    )
    print("  → PASS: línea manual negativa/gigante rechazada, monto a pagar intacto")


# ===========================================================================
# 10) Fuzzing de tipos en 3 endpoints clave (buscar 500)
# ===========================================================================
def test_fuzzing_pago_tipos_no_500(client, db, cleaner):
    st = _setup_venta(client, cleaner, db, precio=100000)
    venta = st["venta"]
    base = {
        "venta_id": venta["id"],
        "moneda_id": 1,
        "fecha": datetime.utcnow().isoformat(),
        "monto": 100,
        "metodo_pago": "EFECTIVO_COP",
    }
    casos = [
        {**base, "monto": "abc"},
        {**base, "monto": None},
        {**base, "monto": {"a": 1}},
        {**base, "monto": [1, 2]},
        {**base, "moneda_id": "x"},
        {**base, "moneda_id": 3, "tasa_cambio": "inf", "metodo_pago": "EFECTIVO_VES"},
        {**base, "fecha": "no-fecha"},
        {**base, "monto": 1e308},
    ]
    for payload in casos:
        r = client.post("/api/v1/pago/", json=payload, headers=ADMIN_HEADERS)
        print(f"  pago {payload} → status={r.status_code}")
        assert r.status_code < 500, (
            f"BUG: 500 en POST /api/v1/pago/ con payload {payload}: {r.text[:300]}"
        )
        if r.status_code in (200, 201) and payload.get("moneda_id") == 1:
            cleaner.registrar("pago", r.json().get("id"))
    print("  → PASS: fuzzing de pago no produce 500")


def test_fuzzing_gasto_tipos_no_500(client, cleaner):
    base = {
        "tipo_gasto_id": 1,
        "moneda_id": 1,
        "fecha": str(date.today()),
        "monto": 100,
        "descripcion": _uniq("fz"),
    }
    casos = [
        {**base, "monto": "abc"},
        {**base, "monto": None},
        {**base, "tipo_gasto_id": None},
        {**base, "moneda_id": "1"},
        {**base, "moneda_id": 2, "tasa_cambio": "inf"},
        {**base, "fecha": "abc"},
        {**base, "monto": 1e308},
    ]
    for payload in casos:
        r = client.post("/api/v1/gasto/gastos/", json=payload, headers=ADMIN_HEADERS)
        print(f"  gasto {payload} → status={r.status_code}")
        assert r.status_code < 500, (
            f"BUG: 500 en POST /api/v1/gasto/gastos/ con payload {payload}: {r.text[:300]}"
        )
        if r.status_code in (200, 201):
            cleaner.registrar("gasto", r.json().get("id"))
    print("  → PASS: fuzzing de gasto no produce 500")


def test_fuzzing_convertir_tipos_no_500(client, db, cleaner):
    cli = crear_cliente(client, cleaner)
    prod = crear_producto(client, cleaner)
    cot = crear_cotizacion(client, cleaner, cli["id"], prod["id"], 100000)
    det_ok = {"producto_id": prod["id"], "cantidad": 1, "precio": 100000}
    casos = [
        {"detalles": []},
        {"detalles": None},
        {"detalles": [{"producto_id": prod["id"], "cantidad": "x", "precio": 100000}]},
        {"detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": None}]},
        {"detalles": [{"producto_id": prod["id"], "cantidad": 1, "precio": 100000,
                       "ancho": {"nested": [1, 2, {"deep": True}]}}]},
        {"detalles": [det_ok], "adelanto": "abc"},
        {"detalles": [det_ok], "adelanto": {"a": 1}},
    ]
    for payload in casos:
        r = client.post(f"/api/v1/pedido/convertir/{cot['id']}", json=payload, headers=ADMIN_HEADERS)
        print(f"  convertir {str(payload)[:80]} → status={r.status_code}")
        assert r.status_code < 500, (
            f"BUG: 500 en convertir con payload {str(payload)[:200]}: {r.text[:300]}"
        )
        if r.status_code in (200, 201):
            cleaner.registrar("pedido", r.json()["id"])
            registrar_venta_de_pedido(client, cleaner, r.json()["id"])
    # La cotización no debe quedar consumida por los intentos inválidos
    n_pedidos = db.execute(text("SELECT count(*) FROM pedido WHERE cotizacion_id=:c"),
                           {"c": cot["id"]}).fetchone()[0]
    assert n_pedidos == 0, f"BUG: los intentos inválidos dejaron {n_pedidos} pedidos"
    print("  → PASS: fuzzing de convertir no produce 500 ni consume la cotización")


# ===========================================================================
# 11) Nómina FIJO: ¿snapshot o cambio retroactivo del sueldo?
# ===========================================================================
def test_nomina_fijo_snapshot_vs_cambio_retroactivo(client, db, cleaner):
    """Crear nómina con FIJO (sueldo 500000), luego subir el sueldo a 900000 y
    agregar una línea manual: la nómina ya creada debe MANTENER 500000.
    Si tras la línea manual el monto_a_pagar salta a 900000, hay cambio retroactivo."""
    emp = _crear_empleado(client, cleaner, tipo_pago="FIJO", sueldo=500000)
    nom = _crear_nomina(client, cleaner, ("2026-11-16", "2026-11-22"), "fijo snapshot")
    det = _detalle_de(nom, emp["id"])
    assert det, "el empleado FIJO no aparece en la nómina"
    monto_original = float(det["monto_a_pagar"])
    print(f"  nómina creada: monto_a_pagar={monto_original} (sueldo 500000)")
    assert monto_original == pytest.approx(500000, abs=0.01), "precondición de sueldo falló"

    # 1) subir el sueldo del empleado
    r = client.put(f"/api/v1/empleado/{emp['id']}", json={"sueldo_semanal": 900000}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"PUT sueldo → {r.status_code}: {r.text}"

    # 2) la nómina (sin tocarla) debe conservar el snapshot
    nom1 = client.get(f"/api/v1/nomina/{nom['id']}", headers=ADMIN_HEADERS).json()
    det1 = _detalle_de(nom1, emp["id"])
    print(f"  tras PUT sueldo=900000 (sin tocar nómina): monto_a_pagar={det1['monto_a_pagar']}")
    assert float(det1["monto_a_pagar"]) == pytest.approx(500000, abs=0.01), (
        f"BUG: la nómina ya creada cambió de 500000 a {det1['monto_a_pagar']} solo por "
        f"editar el sueldo del empleado (cambio retroactivo)"
    )

    # 3) agregar una línea manual cualquiera → ¿recomputation con el sueldo actual?
    r = client.post(f"/api/v1/nomina/detalle/{det1['id']}/linea", json={
        "descripcion": "nota", "cantidad": 1, "precio_unitario": 1,
    }, headers=ADMIN_HEADERS)
    print(f"  línea manual → status={r.status_code}")
    if r.status_code == 201:
        cleaner.registrar("nomina_linea", r.json()["id"])
    nom2 = client.get(f"/api/v1/nomina/{nom['id']}", headers=ADMIN_HEADERS).json()
    det2 = _detalle_de(nom2, emp["id"])
    print(f"  tras línea manual: monto_a_pagar={det2['monto_a_pagar']} (esperado snapshot 500000)")
    assert float(det2["monto_a_pagar"]) == pytest.approx(500000, abs=0.01), (
        f"BUG CRÍTICO: al agregar una línea manual a un detalle FIJO, el monto_a_pagar "
        f"se recalculó con el sueldo ACTUAL ({det2['monto_a_pagar']}) en lugar del "
        f"snapshot (500000) → editar el sueldo revaloriza RETROACTIVAMENTE nóminas ya creadas"
    )
    print("  → PASS: la nómina conserva el snapshot del sueldo (sueldo no revaloriza retroactivamente)")
