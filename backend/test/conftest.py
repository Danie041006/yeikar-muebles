"""
conftest.py — Fixtures compartidos para los tests de riesgo de YEIKAR.

Todos los tests crean datos marcados con prefijo `test_` y registran sus IDs
en el fixture `cleaner`, que los borra en teardown en orden inverso de FKs
(los hijos antes que los padres). NUNCA se ejecuta `pytest test/` completo:
solo los archivos nuevos individualmente.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.main import app
from app.core.config import settings
from app.db.session import session_local


# ---------------------------------------------------------------------------
# Tokens JWT firmados (patrón ya usado en test_iqe.py)
# ---------------------------------------------------------------------------
def _firmar_token(username: str) -> str:
    return jwt.encode(
        {"sub": username, "type": "access", "exp": datetime.utcnow() + timedelta(hours=1)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


# Usuarios reales de la BD: jackson (Dueño), daniel (Ventas)
ADMIN_HEADERS = {"Authorization": f"Bearer {_firmar_token('jackson')}"}
VENTAS_HEADERS = {"Authorization": f"Bearer {_firmar_token('daniel')}"}


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture
def db():
    db = session_local()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Cleaner: registro + borrado estricto en orden inverso de FKs
# ---------------------------------------------------------------------------
ORDEN_LIMPIEZA = [
    "pago",
    "detalle_venta",
    "venta",
    "mano_obra",
    "consumo_material",
    "etapa_asignado_adicional",
    "etapa_produccion",
    "costo_produccion",
    "orden_produccion",
    "envio",
    "detalle_pedido",
    "pedido",
    "cotizacion_detalle_material",
    "detalle_cotizacion",
    "cotizacion",
    "detalle_compra",
    "compra",
    "producto_material",
    "movimiento_inventario",
    "inventario",
    "producto",
    "material",
    "gasto",
    "tasa_cambio",
    "cliente",
    "proveedor",
    "empleado",
    "usuario_rol",
    "usuario",
]


class Cleaner:
    """Acumula (tabla → ids) y los borra en el orden correcto al final."""

    def __init__(self):
        self._ids: dict[str, set] = {t: set() for t in ORDEN_LIMPIEZA}

    def registrar(self, tabla: str, id):
        id = int(id)
        self._ids.setdefault(tabla, set()).add(id)

    def registrar_muchos(self, tabla: str, ids):
        for id in ids:
            self.registrar(tabla, id)

    def registrar_gastos_like(self, db, descripcion_like: str):
        """Registra gastos (p.ej. los generados automáticamente por consumo)."""
        if "gasto" not in self._ids:
            self._ids["gasto"] = set()
        from sqlalchemy import text
        rows = db.execute(
            text("SELECT id FROM gasto WHERE descripcion LIKE :pat"),
            {"pat": f"%{descripcion_like}%"},
        ).fetchall()
        for (gid,) in rows:
            self._ids["gasto"].add(int(gid))

    def cleanup(self, db):
        from sqlalchemy import text
        errores = []
        for tabla in ORDEN_LIMPIEZA:
            ids = self._ids.get(tabla) or set()
            if not ids:
                continue
            ids_str = ",".join(str(i) for i in ids)
            try:
                db.execute(text(f"DELETE FROM {tabla} WHERE id IN ({ids_str})"))
                db.commit()
            except Exception as e:  # noqa: BLE001 — un fallo no debe romper el resto
                db.rollback()
                errores.append(f"{tabla}: {e}")
        self._ids = {t: set() for t in ORDEN_LIMPIEZA}
        if errores:
            raise AssertionError(f"Limpieza incompleta:\n" + "\n".join(errores))


@pytest.fixture
def cleaner(db):
    c = Cleaner()
    try:
        yield c
    finally:
        try:
            c.cleanup(db)
        except AssertionError as e:
            print(f"\n⚠️  CLEANUP: {e}")


# ---------------------------------------------------------------------------
# Helpers de creación vía API (registran en el cleaner automáticamente)
# ---------------------------------------------------------------------------
def _uniq(prefix: str) -> str:
    return f"test_{prefix}_{uuid.uuid4().hex[:8]}"


def crear_cliente(client, cleaner, nombre=None) -> dict:
    payload = {"nombre": nombre or _uniq("cliente"), "telefono": "555-0000"}
    r = client.post("/api/v1/cliente/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_cliente → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("cliente", body["id"])
    return body


def crear_producto(client, cleaner, nombre=None, tipo_producto_id=1) -> dict:
    payload = {
        "nombre": nombre or _uniq("prod"),
        "tipo_producto_id": tipo_producto_id,
        "ancho_base": 1.60,
        "largo_base": 1.90,
    }
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_producto → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("producto", body["id"])
    return body


def crear_material(client, cleaner, nombre=None, costo_base=1000.0, unidad_medida_id=2) -> dict:
    payload = {
        "nombre": nombre or _uniq("mat"),
        "unidad_medida_id": unidad_medida_id,
        "costo_base": costo_base,
    }
    r = client.post("/api/v1/material/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_material → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("material", body["id"])
    return body


def crear_receta(client, cleaner, producto_id, material_id, cantidad_base, tipo_escala="FIJO", seccion="EBANISTERIA"):
    payload = {
        "producto_id": producto_id,
        "material_id": material_id,
        "cantidad_base": cantidad_base,
        "tipo_escala": tipo_escala,
        "seccion": seccion,
    }
    r = client.post(f"/api/v1/producto/{producto_id}/receta", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_receta → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("producto_material", body["id"])
    return body


def crear_proveedor(client, cleaner, nombre=None) -> dict:
    payload = {"nombre": nombre or _uniq("prov"), "telefono": "555-1111"}
    r = client.post("/api/v1/proveedor/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_proveedor → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("proveedor", body["id"])
    return body


def crear_cotizacion(client, cleaner, cliente_id, producto_id, precio, cantidad=1,
                     moneda_id=1, tasa_cambio=1.0, estado="BORRADOR", observaciones=None) -> dict:
    payload = {
        "cliente_id": cliente_id,
        "fecha": str(datetime.today().date()),
        "estado": estado,
        "total_estimado": round(precio * cantidad, 2),
        "moneda_id": moneda_id,
        "tasa_cambio": tasa_cambio,
        "observaciones": observaciones or _uniq("cot"),
        "detalles": [
            {
                "producto_id": producto_id,
                "cantidad": cantidad,
                "precio": precio,
                "ancho": 1.60,
                "largo": 1.90,
            }
        ],
    }
    r = client.post("/api/v1/cotizacion/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_cotizacion → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("cotizacion", body["id"])
    return body


def crear_venta(client, cleaner, pedido_id, moneda_id=1) -> dict:
    r = client.post("/api/v1/venta/", json={"pedido_id": pedido_id, "moneda_id": moneda_id}, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_venta → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("venta", body["id"])
    return body


def crear_pago(client, cleaner, venta_id, moneda_id, monto, metodo_pago="EFECTIVO_COP",
               tasa_cambio=None, referencia=None) -> dict:
    payload = {
        "venta_id": venta_id,
        "moneda_id": moneda_id,
        "fecha": datetime.utcnow().isoformat(),
        "monto": monto,
        "metodo_pago": metodo_pago,
        "referencia": referencia,
    }
    if tasa_cambio is not None:
        payload["tasa_cambio"] = tasa_cambio
    r = client.post("/api/v1/pago/", json=payload, headers=ADMIN_HEADERS)
    body = r.json() if r.status_code in (200, 201) else r.text
    if r.status_code in (200, 201):
        cleaner.registrar("pago", body["id"])
    return r, body


def crear_movimiento(client, cleaner, material_id, tipo, cantidad, ubicacion_id=1) -> (tuple):
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material_id,
        "ubicacion_id": ubicacion_id,
        "tipo": tipo,
        "cantidad": cantidad,
    }, headers=ADMIN_HEADERS)
    body = r.json() if r.status_code in (200, 201) else r.text
    if r.status_code in (200, 201):
        cleaner.registrar("movimiento_inventario", body["id"])
        from sqlalchemy import text
        if not hasattr(cleaner, "_inventario_buscados"):
            cleaner._inventario_buscados = set()
        dbq = session_local()
        try:
            inv = dbq.execute(text(
                "SELECT id FROM inventario WHERE material_id=:m AND ubicacion_id=:u"
            ), {"m": material_id, "u": ubicacion_id}).fetchone()
            if inv:
                cleaner.registrar("inventario", inv[0])
        finally:
            dbq.close()
    return r, body


def crear_compra(client, cleaner, proveedor_id, material_id, cantidad, costo_unitario,
                 moneda_id=1, estado="BORRADOR", observaciones=None) -> dict:
    payload = {
        "proveedor_id": proveedor_id,
        "moneda_id": moneda_id,
        "fecha": str(datetime.today().date()),
        "estado": estado,
        "observaciones": observaciones or _uniq("compra"),
        "detalle": [
            {"material_id": material_id, "cantidad": cantidad, "costo_unitario": costo_unitario}
        ],
    }
    r = client.post("/api/v1/compras/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear_compra → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("compra", body["id"])
    return body


def actualizar_estado_compra(client, compra_id, estado) -> (tuple):
    r = client.put(f"/api/v1/compras/{compra_id}/estado", params={"estado": estado}, headers=ADMIN_HEADERS)
    body = r.json() if r.status_code in (200, 201) else r.text
    return r, body


def crear_orden_desde_pedido(client, cleaner, detalle_pedido_id) -> dict:
    r = client.post(f"/api/v1/produccion/orden/desde-pedido/{detalle_pedido_id}", headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"crear_orden_desde_pedido → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("orden_produccion", body["id"])
    return body


def registrar_inventario_de_material(db, cleaner, material_id):
    """Registra en el cleaner todos los movimientos e inventario de un material
    (incluye los creados internamente por consumos, reversas o compras RECIBIDA)."""
    from sqlalchemy import text
    for (mid,) in db.execute(
        text("SELECT id FROM movimiento_inventario WHERE material_id = :m"), {"m": material_id}
    ).fetchall():
        cleaner.registrar("movimiento_inventario", mid)
    for (iid,) in db.execute(
        text("SELECT id FROM inventario WHERE material_id = :m"), {"m": material_id}
    ).fetchall():
        cleaner.registrar("inventario", iid)


def registrar_venta_de_pedido(client, cleaner, pedido_id):
    """Registra en el cleaner la factura auto-generada por una conversión
    (venta + detalle_venta + pagos). Sin esto, borrar el pedido en el teardown
    falla por FK `venta → pedido` (RESTRICT) y deja basura en la BD."""
    venta_id = None
    r = client.get("/api/v1/venta/", params={"limite": 1000}, headers=ADMIN_HEADERS)
    if r.status_code == 200:
        for v in r.json():
            if v.get("pedido_id") == pedido_id:
                venta_id = v["id"]
                break
    if venta_id is None:
        dbq = session_local()
        try:
            row = dbq.execute(text("SELECT id FROM venta WHERE pedido_id = :p"), {"p": pedido_id}).fetchone()
            venta_id = int(row[0]) if row else None
        finally:
            dbq.close()
    if venta_id is None:
        return
    cleaner.registrar("venta", venta_id)
    det = client.get(f"/api/v1/venta/{venta_id}", headers=ADMIN_HEADERS)
    if det.status_code == 200:
        for d in det.json().get("detalles", []):
            cleaner.registrar("detalle_venta", d["id"])
        for p in det.json().get("pagos", []):
            cleaner.registrar("pago", p["id"])