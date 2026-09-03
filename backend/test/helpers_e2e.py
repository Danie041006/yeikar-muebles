"""
helpers_e2e.py — Infraestructura compartida de las pruebas E2E (casos 1-4).

Simulan flujos COMPLETOS de negocio vía API real (TestClient): cotización →
pedido → producción por áreas (consumos + mano de obra) → venta → pagos
multi-moneda → factura fiscal → envío (admin/chofer/guía) → nómina/aguinaldo.

Reglas de oro de estas pruebas:
  * Todo dato creado se registra en el `cleaner` (borrado en teardown).
  * Se usan los headers firmados de conftest (ADMIN_HEADERS = jackson/Dueño).
  * Los montos monetarios se aseveran contra lo que devuelve la API (y contra
    movimiento_caja), nunca contra supuestos previos, para ser robustos al
    redondeo a la unidad de la moneda.
  * Monedas: COP=1, USD=2, VES=3. Tasas de prueba: 1 USD=3900 COP, 1 VES=10 COP
    (dentro del ±50% de la última tasa registrada; si el control lo rechaza,
    leer la tasa vigente de la tabla `tasa_cambio` y usarla).
"""
import unicodedata
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import text

from conftest import (
    ADMIN_HEADERS,
    crear_cliente,
    crear_material,
    crear_pago,
    registrar_inventario_de_material,
    registrar_venta_de_pedido,
    _firmar_token,
)

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _uniq(prefix: str) -> str:
    return f"test_e2e_{prefix}_{uuid.uuid4().hex[:8]}"


def _norm(nombre: str) -> str:
    return unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode().strip().lower()


def hoy() -> date:
    return date.today()


def semana_actual() -> tuple[date, date]:
    """Semana (lunes→domingo) que contiene hoy, con la que la nómina SIEMPRE
    tendrá datos (las etapas/mano de obra usan fecha now())."""
    d = hoy()
    desde = d - timedelta(days=d.weekday())
    return desde, desde + timedelta(days=6)


# ---------------------------------------------------------------------------
# Catálogos (se leen de la BD real, nunca se asumen ids)
# ---------------------------------------------------------------------------

def areas(db) -> dict[str, int]:
    """{nombre_normalizado: id} de todas las áreas."""
    return {_norm(r[1]): r[0] for r in db.execute(text("SELECT id, nombre FROM area")).fetchall()}


def area_id(db, nombre: str) -> int:
    return areas(db)[_norm(nombre)]


def cargos(db) -> dict[str, int]:
    """{nombre_normalizado: id} de todos los cargos."""
    return {_norm(r[1]): r[0] for r in db.execute(text("SELECT id, nombre FROM cargo")).fetchall()}


def cargo_id(db, nombre: str) -> int:
    return cargos(db)[_norm(nombre)]


# ---------------------------------------------------------------------------
# Empleados / productos de reventa / stock
# ---------------------------------------------------------------------------

def crear_empleado(client, cleaner, nombre=None, cargo_id=1, en_nomina=False,
                   tipo_pago="DESTAJO", sueldo_semanal=None,
                   porcentaje_aguinaldo=None, activo=True) -> dict:
    payload = {
        "nombre": nombre or _uniq("emp"),
        "cargo_id": cargo_id,
        "telefono": "555-7777",
        "activo": activo,
        "en_nomina": en_nomina,
        "tipo_pago": tipo_pago,
    }
    if sueldo_semanal is not None:
        payload["sueldo_semanal"] = sueldo_semanal
    if porcentaje_aguinaldo is not None:
        payload["porcentaje_aguinaldo"] = porcentaje_aguinaldo
    r = client.post("/api/v1/empleado/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_empleado → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("empleado", body["id"])
    return body


def crear_producto_reventa(client, cleaner, nombre=None, costo_base=50000.0) -> dict:
    payload = {
        "nombre": nombre or _uniq("rev"),
        "tipo_producto_id": 1,
        "es_reventa": True,
        "ancho_base": 1.60,
        "largo_base": 1.90,
        "costo_base": costo_base,
    }
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_producto_reventa → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("producto", body["id"])
    return body


def crear_producto_fabricado(client, cleaner, nombre=None, costo_base=80000.0) -> dict:
    payload = {
        "nombre": nombre or _uniq("fab"),
        "tipo_producto_id": 1,
        "es_reventa": False,
        "ancho_base": 1.60,
        "largo_base": 1.90,
        "costo_base": costo_base,
    }
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_producto_fabricado → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("producto", body["id"])
    return body


def crear_stock_producto(client, cleaner, db, producto_id, cantidad, costo_unitario) -> dict:
    """ENTRADA de inventario a un producto de reventa."""
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": producto_id,
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": cantidad,
        "costo_unitario": costo_unitario,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"stock producto → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("movimiento_producto_inventario", body["id"])
    row = db.execute(text(
        "SELECT id FROM producto_inventario WHERE producto_id = :p AND ubicacion_id = 1"
    ), {"p": producto_id}).fetchone()
    if row:
        cleaner.registrar("producto_inventario", row[0])
    return body


def stock_producto(db, producto_id) -> float:
    return float(db.execute(text(
        "SELECT COALESCE(SUM(cantidad), 0) FROM producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).scalar())


def stock_material(db, material_id, ubicacion_id=1) -> float:
    row = db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id = :m AND ubicacion_id = :u"
    ), {"m": material_id, "u": ubicacion_id}).fetchone()
    return float(row[0]) if row else 0.0


def entrar_stock_material(client, cleaner, material_id, cantidad, ubicacion_id=1):
    """ENTRADA de stock a un material vía API (la que usan los consumos)."""
    from conftest import crear_movimiento
    r, body = crear_movimiento(client, cleaner, material_id, "ENTRADA", cantidad, ubicacion_id=ubicacion_id)
    assert r.status_code in (200, 201), f"entrar stock material → {r.status_code}: {r.text}"
    return body


# ---------------------------------------------------------------------------
# Cotización → Pedido (con detalles múltiples / REVENTA / INSUMO)
# ---------------------------------------------------------------------------

def crear_cotizacion_multidetalle(client, cleaner, cliente_id, detalles, moneda_id=1,
                                  tasa_cambio=1.0, estado="BORRADOR") -> dict:
    """detalles: lista de dicts {producto_id|material_id, tipo_item, cantidad,
    precio, ancho?, largo?}."""
    total = round(sum(float(d["cantidad"]) * float(d["precio"]) for d in detalles), 2)
    payload = {
        "cliente_id": cliente_id,
        "fecha": str(hoy()),
        "estado": estado,
        "total_estimado": total,
        "moneda_id": moneda_id,
        "tasa_cambio": tasa_cambio,
        "observaciones": _uniq("cot"),
        "detalles": detalles,
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_cotizacion_multidetalle → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("cotizacion", body["id"])
    for d in body.get("detalles", []):
        cleaner.registrar("detalle_cotizacion", d["id"])
    return body


def convertir_cotizacion(client, cleaner, cot_id, detalles, adelanto=None,
                         moneda_adelanto_id=None, tasa_cambio_adelanto=None,
                         metodo_pago=None, fecha_entrega_estimada=None):
    """Convierte la cotización en pedido (auto-crea la venta + adelanto).
    Registra pedido/detalles/venta/pagos en el cleaner. Devuelve (r, pedido)."""
    payload = {"detalles": detalles}
    if fecha_entrega_estimada:
        payload["fecha_entrega_estimada"] = fecha_entrega_estimada
    if adelanto is not None:
        payload["adelanto"] = adelanto
        payload["metodo_pago"] = metodo_pago
        if moneda_adelanto_id is not None:
            payload["moneda_adelanto_id"] = moneda_adelanto_id
        if tasa_cambio_adelanto is not None:
            payload["tasa_cambio_adelanto"] = tasa_cambio_adelanto
    r = client.post(f"/api/v1/pedido/convertir/{cot_id}", json=payload, headers=ADMIN_HEADERS)
    if r.status_code not in (200, 201):
        return r, None
    pedido = r.json()
    cleaner.registrar("pedido", pedido["id"])
    for d in pedido.get("detalles", []):
        cleaner.registrar("detalle_pedido", d["id"])
    registrar_venta_de_pedido(client, cleaner, pedido["id"])
    return r, pedido


def venta_de_pedido(client, db, pedido_id) -> dict | None:
    r = client.get("/api/v1/venta/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    if r.status_code == 200:
        for v in r.json():
            if v.get("pedido_id") == pedido_id:
                return v
    row = db.execute(text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}).fetchone()
    if not row:
        return None
    return client.get(f"/api/v1/venta/{row[0]}", headers=ADMIN_HEADERS).json()


def detalle_pedido_id(pedido, index=0) -> int:
    return pedido["detalles"][index]["id"]


# ---------------------------------------------------------------------------
# Producción por áreas
# ---------------------------------------------------------------------------

def crear_etapa(client, cleaner, orden_id, area_id, empleado_id, estado="ASIGNADA",
                observaciones=None) -> dict:
    payload = {
        "orden_produccion_id": orden_id,
        "area_id": area_id,
        "empleado_responsable_id": empleado_id,
        "estado": estado,
    }
    if observaciones:
        payload["observaciones"] = observaciones
    r = client.post("/api/v1/produccion/etapa/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_etapa → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("etapa_produccion", body["id"])
    return body


def avanzar_etapa(client, etapa_id, estado):
    r = client.put(f"/api/v1/produccion/etapa/{etapa_id}/estado",
                   params={"estado": estado}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"avanzar etapa {estado} → {r.status_code}: {r.text}"
    return r.json()


def crear_consumo(client, cleaner, db, etapa_id, material_id, cantidad, solicitante_id,
                  fecha=None, seccion=None, observaciones=None,
                  unidad_captura=None, pieza_largo=None, pieza_ancho=None, pieza_espesor=None):
    """Registra un consumo de material (requiere etapa EN_PROCESO) y registra
    el gasto automático + movimientos de inventario en el cleaner."""
    payload = {
        "etapa_produccion_id": etapa_id,
        "material_id": material_id,
        "cantidad": cantidad,
        "fecha": (fecha or datetime.utcnow()).isoformat(),
        "solicitante_empleado_id": solicitante_id,
        "observaciones": observaciones or _uniq("consumo"),
    }
    if seccion:
        payload["seccion"] = seccion
    if unidad_captura:
        payload["unidad_captura"] = unidad_captura
    if pieza_largo:
        payload.update(pieza_largo=pieza_largo, pieza_ancho=pieza_ancho, pieza_espesor=pieza_espesor)
    r = client.post("/api/v1/produccion/consumo/", json=payload, headers=ADMIN_HEADERS)
    if r.status_code not in (200, 201):
        return r, None
    body = r.json()
    cleaner.registrar("consumo_material", body["id"])
    # El gasto automático lleva el marcador [consumo {id}] en OBSERVACIONES
    # (no en descripcion): registrar_gastos_like busca solo descripcion.
    for (gid,) in db.execute(text(
        "SELECT id FROM gasto WHERE observaciones LIKE :pat"
    ), {"pat": f"%[consumo {body['id']}]%"}).fetchall():
        cleaner.registrar("gasto", gid)
    registrar_inventario_de_material(db, cleaner, material_id)
    return r, body


def registrar_mano_obra(client, cleaner, etapa_id, empleado_id, monto,
                        porcentaje_recargo=0.0, precio_produccion_id=None,
                        listo_nomina=True, observaciones=None) -> dict:
    payload = {
        "etapa_produccion_id": etapa_id,
        "empleado_id": empleado_id,
        "monto": monto,
        "porcentaje_recargo": porcentaje_recargo,
        "listo_nomina": listo_nomina,
        "observaciones": observaciones or _uniq("mo"),
    }
    if precio_produccion_id:
        payload["precio_produccion_id"] = precio_produccion_id
    r = client.post("/api/v1/produccion/mano-obra/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"registrar_mano_obra → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("mano_obra", body["id"])
    return body


def crear_tarifa_produccion(client, cleaner, area_id, producto_id, precio,
                            descripcion=None) -> dict:
    r = client.post("/api/v1/costo-produccion/", json={
        "area_id": area_id,
        "descripcion": descripcion or _uniq("tarifa"),
        "precio": precio,
        "producto_id": producto_id,
        "activo": True,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_tarifa_produccion → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("precio_produccion", body["id"])
    return body


def finalizar_orden(client, orden_id) -> dict:
    r = client.put(f"/api/v1/produccion/orden/{orden_id}/estado",
                   params={"estado": "FINALIZADA"}, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"finalizar_orden → {r.status_code}: {r.text}"
    return r.json()


def envio_de_pedido(db, pedido_id):
    row = db.execute(text("SELECT * FROM envio WHERE pedido_id = :p"), {"p": pedido_id}).fetchone()
    return dict(row._mapping) if row else None


def avanzar_envio(client, envio_id, estado):
    r = client.put(f"/api/v1/envio/{envio_id}/estado", params={"estado": estado},
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"avanzar_envio {estado} → {r.status_code}: {r.text}"
    return r.json()


def asignar_chofer(client, envio_id, empleado_id) -> dict:
    r = client.put(f"/api/v1/envio/{envio_id}", json={"empleado_id": empleado_id},
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"asignar_chofer → {r.status_code}: {r.text}"
    return r.json()


# ---------------------------------------------------------------------------
# Ventas / pagos / factura fiscal
# ---------------------------------------------------------------------------

def pagar_venta(client, cleaner, venta_id, moneda_id, monto, metodo_pago,
                tasa_cambio=None, referencia=None):
    """Pago parcial/total; devuelve (r, body). El caller decide los asserts."""
    return crear_pago(client, cleaner, venta_id, moneda_id, monto,
                      metodo_pago=metodo_pago, tasa_cambio=tasa_cambio,
                      referencia=referencia)


def venta_actualizada(client, venta_id) -> dict:
    return client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS).json()


def emitir_factura(client, cleaner, db, pedido_id, lineas, tasa_usd_ves=50.0,
                   permitir_saldo_pendiente=False, observaciones=None):
    """lineas: [{detalle_pedido_id, precio_usd}]. Devuelve (r, body)."""
    payload = {
        "pedido_id": pedido_id,
        "tasa_usd_ves": tasa_usd_ves,
        "lineas": lineas,
        "permitir_saldo_pendiente": permitir_saldo_pendiente,
    }
    if observaciones:
        payload["observaciones"] = observaciones
    r = client.post("/api/v1/factura/", json=payload, headers=ADMIN_HEADERS)
    if r.status_code not in (200, 201):
        return r, None
    body = r.json()
    cleaner.registrar("factura", body["id"])
    det = client.get(f"/api/v1/factura/{body['id']}", headers=ADMIN_HEADERS)
    if det.status_code == 200:
        for d in det.json().get("detalles", []):
            cleaner.registrar("detalle_factura", d["id"])
    return r, body


# ---------------------------------------------------------------------------
# Caja / dinero
# ---------------------------------------------------------------------------

def movimientos_caja_de_pedido(db, pedido_id) -> list[dict]:
    """Movimientos de caja generados por los pagos de la venta del pedido."""
    rows = db.execute(text(
        """SELECT mc.tipo, mc.monto, mc.moneda_id, mc.tasa_cambio,
                  mc.monto_en_moneda_base, mc.referencia, mca.codigo AS cuenta
           FROM movimiento_caja mc
           JOIN metodo_caja mca ON mca.id = mc.metodo_caja_id
           JOIN pago p ON p.id = mc.pago_id
           JOIN venta v ON v.id = p.venta_id
           WHERE v.pedido_id = :pedido
           ORDER BY mc.id"""
    ), {"pedido": pedido_id}).fetchall()
    return [dict(r._mapping) for r in rows]


def saldo_cuenta(client, codigo: str, moneda_id: int | None = None) -> float:
    """Saldo total (o de una moneda) de una cuenta (metodo_caja por codigo)."""
    r = client.get("/api/v1/cuenta/resumen", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"cuenta/resumen → {r.status_code}: {r.text}"
    cuenta = next((x for x in r.json() if x["metodo_caja"]["codigo"] == codigo), None)
    if cuenta is None:
        return 0.0
    if moneda_id is None:
        return float(cuenta.get("saldo_total", 0) or 0)
    linea = next((l for l in cuenta["saldo_por_moneda"] if l["moneda_id"] == moneda_id), None)
    return float(linea["monto"]) if linea else 0.0


# ---------------------------------------------------------------------------
# Usuario chofer (para la vista del chofer: empleado_id + rol con envios)
# ---------------------------------------------------------------------------

def crear_usuario_chofer(db, cleaner, empleado_id, nombre_usuario=None) -> dict:
    """Crea (vía SQL, sin password real: el JWT se firma a mano) un usuario
    ligado al empleado chofer con rol propio que solo abre el módulo envios.
    Devuelve los headers para llamar como chofer."""
    username = nombre_usuario or _uniq("chofer")
    rol_id = db.execute(text(
        "INSERT INTO rol (nombre, descripcion, activo) VALUES (:n, 'Rol E2E chofer', true) RETURNING id"
    ), {"n": f"ROL_{username}"}).scalar()
    rmid = db.execute(text(
        "INSERT INTO rol_modulo (rol_id, modulo, gestionar) VALUES (:r, 'envios', true) RETURNING id"
    ), {"r": rol_id}).scalar()
    uid = db.execute(text(
        "INSERT INTO usuario (empleado_id, nombre_usuario, email, password_hash, activo) "
        "VALUES (:e, :u, NULL, 'e2e', true) RETURNING id"
    ), {"e": empleado_id, "u": username}).scalar()
    urid = db.execute(text(
        "INSERT INTO usuario_rol (usuario_id, rol_id) VALUES (:u, :r) RETURNING id"
    ), {"u": uid, "r": rol_id}).scalar()
    db.commit()
    cleaner.registrar("usuario", uid)
    cleaner.registrar("usuario_rol", urid)
    cleaner.registrar("rol_modulo", rmid)
    cleaner.registrar("rol", rol_id)
    return {"Authorization": f"Bearer {_firmar_token(username)}"}


# ---------------------------------------------------------------------------
# Nómina semanal + aguinaldo
# ---------------------------------------------------------------------------

def crear_nomina(client, cleaner, desde=None, hasta=None, descripcion=None):
    """Crea la nómina semanal del periodo (default: semana actual). Devuelve
    (r, body). Si la semana ya está ocupada (409), el caller cambia de semana."""
    desde = desde or semana_actual()[0]
    hasta = hasta or semana_actual()[1]
    payload = {
        "periodo_desde": str(desde),
        "periodo_hasta": str(hasta),
        "descripcion": descripcion or _uniq("nomina"),
    }
    r = client.post("/api/v1/nomina/", json=payload, headers=ADMIN_HEADERS)
    if r.status_code not in (200, 201):
        return r, None
    body = r.json()
    cleaner.registrar("nomina", body["id"])
    for det in body.get("detalles", []):
        cleaner.registrar("nomina_detalle", det["id"])
        for linea in det.get("lineas", []):
            cleaner.registrar("nomina_linea", linea["id"])
    return r, body


def preview_nomina(client, desde, hasta) -> dict:
    r = client.post("/api/v1/nomina/generar", json={
        "periodo_desde": str(desde), "periodo_hasta": str(hasta),
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"nomina/generar → {r.status_code}: {r.text}"
    return r.json()


def pagar_nomina(client, cleaner, db, nomina_id, metodo_caja_id=1) -> dict:
    """Asigna cuenta de caja a cada detalle y paga la nómina."""
    nomina = client.get(f"/api/v1/nomina/{nomina_id}", headers=ADMIN_HEADERS).json()
    for det in nomina.get("detalles", []):
        if float(det.get("monto_a_pagar", 0) or 0) > 0:
            r = client.put(f"/api/v1/nomina/detalle/{det['id']}",
                           json={"metodo_caja_id": metodo_caja_id}, headers=ADMIN_HEADERS)
            assert r.status_code == 200, f"nomina detalle → {r.status_code}: {r.text}"
    r = client.post(f"/api/v1/nomina/{nomina_id}/pagar", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"pagar_nomina → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar_gastos_like(db, f"{nomina['periodo_desde']} al {nomina['periodo_hasta']}")
    return body


def saldos_aguinaldo(client, empleado_id) -> float:
    r = client.get("/api/v1/nomina/saldos-aguinaldo", headers=ADMIN_HEADERS)
    assert r.status_code == 200, f"saldos-aguinaldo → {r.status_code}: {r.text}"
    for fila in r.json():
        if fila["empleado_id"] == empleado_id:
            return float(fila.get("saldo_aguinaldo", 0) or 0)
    return 0.0


def pagar_aguinaldo(client, cleaner, db, empleado_id, metodo_caja_id=1) -> dict:
    r = client.post("/api/v1/nomina/aguinaldo/pagar", json={
        "empleado_id": empleado_id, "metodo_caja_id": metodo_caja_id,
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"pagar_aguinaldo → {r.status_code}: {r.text}"
    body = r.json()
    # Gasto "Aguinaldo {año} — {empleado}" + su salida de caja (referencia "Gasto #{id}").
    for (gid,) in db.execute(text(
        "SELECT id FROM gasto WHERE descripcion LIKE 'Aguinaldo %'"
    )).fetchall():
        cleaner.registrar("gasto", gid)
        cleaner.registrar_caja_ref(f"Gasto #{gid}")
    return body