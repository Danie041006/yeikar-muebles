"""
Retrabajo de piezas de exhibición (orden tipo RETRABAJO).

Flujo (el caso real que lo motivó):
  la Sra. quiere un mueble del showroom en OTRO color → no se fabrica otro:
  se retoca el existente → la pieza SALE del showroom (apartada, no vendible)
  → el taller registra materiales y mano de obra → al finalizar la pieza
  VUELVE con su costo X + el costo real del retoque Y. La venta posterior
  reporta la utilidad/pérdida real.

Lo que NO debe pasar (decisiones del dueño):
  - la receta ni el costo/precio del catálogo se tocan (la pieza es única);
  - no se crea stock nuevo (nada de pieza duplicada);
  - no se puede retrabajar dos veces la misma pieza a la vez;
  - cancelar/eliminar el retrabajo devuelve la pieza con su costo original.
"""
from decimal import Decimal

from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_material, crear_producto, registrar_inventario_de_material
from helpers_e2e import (
    area_id,
    cargos,
    crear_consumo,
    crear_empleado,
    crear_etapa,
    avanzar_etapa,
    entrar_stock_material,
    finalizar_orden,
    registrar_mano_obra,
    _uniq,
)


# ---------------------------------------------------------------------------
# Utilidades locales
# ---------------------------------------------------------------------------
def crear_producto_exhibicion(client, cleaner, nombre=None, moneda_id=1,
                              costo_estimado=30000.0, precio_venta=100000.0) -> dict:
    payload = {
        "nombre": nombre or _uniq("exh_ret"),
        "tipo_producto_id": 2,
        "es_reventa": False,
        "es_exhibicion": True,
        "moneda_id": moneda_id,
        "precio_costo_base": costo_estimado,
        "precio_venta_base": precio_venta,
        "activo": True,
    }
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear producto exhibición → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("producto", body["id"])
    return body


def ubicacion_exhibicion_id(db, cleaner) -> int:
    row = db.execute(text("SELECT id FROM ubicacion WHERE nombre = 'EXHIBICIÓN'")).fetchone()
    if row:
        return int(row[0])
    ubi_id = db.execute(text(
        "INSERT INTO ubicacion (nombre, descripcion, tipo, activo) "
        "VALUES ('EXHIBICIÓN', 'Showroom (test)', 'PUNTO_VENTA', TRUE) RETURNING id"
    )).scalar()
    db.commit()
    cleaner.registrar("ubicacion", ubi_id)
    return int(ubi_id)


def stock_y_costo(db, producto_id):
    """(cantidad total, costo_promedio) de la pieza en el inventario."""
    row = db.execute(text(
        "SELECT COALESCE(SUM(cantidad), 0), MAX(costo_promedio) "
        "FROM producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchone()
    return float(row[0]), (float(row[1]) if row[1] is not None else None)


def entrar_pieza_showroom(client, cleaner, db, producto_id, costo) -> dict:
    """Registra la pieza en el stock del showroom (como si ya estuviera hecha)."""
    ubi = ubicacion_exhibicion_id(db, cleaner)
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": producto_id,
        "ubicacion_id": ubi,
        "tipo": "ENTRADA",
        "cantidad": 1,
        "costo_unitario": costo,
        "observaciones": "Pieza de exhibición ya fabricada (test retrabajo)",
    }, headers=ADMIN_HEADERS)
    assert r.status_code in (200, 201), f"entrada showroom → {r.status_code}: {r.text}"
    cleaner.registrar("movimiento_producto_inventario", r.json()["id"])
    registrar_inventario_producto(db, cleaner, producto_id)
    return r.json()


def registrar_inventario_producto(db, cleaner, producto_id):
    for (mid,) in db.execute(text(
        "SELECT id FROM movimiento_producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchall():
        cleaner.registrar("movimiento_producto_inventario", mid)
    for (iid,) in db.execute(text(
        "SELECT id FROM producto_inventario WHERE producto_id = :p"
    ), {"p": producto_id}).fetchall():
        cleaner.registrar("producto_inventario", iid)


def abrir_retrabajo(client, cleaner, producto_id, motivo="Cambio de color",
                    cliente_nombre="Sra. Prueba"):
    r = client.post("/api/v1/produccion/orden/retrabajo", json={
        "producto_id": producto_id,
        "motivo": motivo,
        "cliente_nombre": cliente_nombre,
    }, headers=ADMIN_HEADERS)
    if r.status_code == 201:
        cleaner.registrar("orden_produccion", r.json()["id"])
    return r


def _area_para(db, fragmento: str, respaldo: str = "Ebanistería") -> int:
    row = db.execute(text(
        "SELECT id FROM area WHERE nombre ILIKE :f ORDER BY id LIMIT 1"
    ), {"f": f"%{fragmento}%"}).fetchone()
    return int(row[0]) if row else area_id(db, respaldo)


# ---------------------------------------------------------------------------
# 1. El flujo completo: retoque → la pieza vuelve con X + Y y el catálogo
#    queda intacto (sin receta nueva, sin stock duplicado)
# ---------------------------------------------------------------------------
def test_retrabajo_completo_suma_costo_y_no_toca_catalogo(client, db, cleaner):
    pieza = crear_producto_exhibicion(client, cleaner, costo_estimado=30000.0, precio_venta=100000.0)
    entrar_pieza_showroom(client, cleaner, db, pieza["id"], costo=55000.0)

    # ── Abrir el retrabajo: la pieza sale del showroom (apartada) ──
    r = abrir_retrabajo(client, cleaner, pieza["id"],
                        motivo="Cambio de color para la clienta",
                        cliente_nombre="Sra. Prueba")
    assert r.status_code == 201, f"abrir retrabajo → {r.status_code}: {r.text}"
    orden = r.json()
    assert orden["tipo"] == "RETRABAJO"
    assert orden["producto_inventario_id"] is not None
    assert "Cambio de color" in (orden["observaciones"] or "")
    assert "Sra. Prueba" in (orden["observaciones"] or "")

    stock, costo = stock_y_costo(db, pieza["id"])
    assert stock == 0.0, "la pieza debe salir del showroom mientras se retrabaja"
    assert costo == 55000.0, "el costo de la fila no cambia al salir"

    salida = db.execute(text(
        "SELECT id FROM movimiento_producto_inventario "
        "WHERE producto_id = :p AND tipo = 'SALIDA' "
        "AND referencia_tipo = 'PRODUCCION_RETRABAJO' AND referencia_id = :o"
    ), {"p": pieza["id"], "o": orden["id"]}).fetchone()
    assert salida is not None, "falta el movimiento de salida del retrabajo"

    # El listado de retrabajos abiertos la marca (para el chip EN RETRABAJO).
    abiertos = client.get("/api/v1/produccion/orden/retrabajos-abiertos", headers=ADMIN_HEADERS).json()
    assert any(o["id"] == orden["id"] for o in abiertos)

    # ── El taller trabaja: material + mano de obra (trabajo nuevo, se paga) ──
    emp = crear_empleado(client, cleaner, cargo_id=cargos(db)["ebanista"], en_nomina=True)
    etapa = crear_etapa(client, cleaner, orden["id"], _area_para(db, "tapic"), emp["id"])
    avanzar_etapa(client, etapa["id"], "EN_PROCESO")

    mat = crear_material(client, cleaner, costo_base=2000.0)
    entrar_stock_material(client, cleaner, mat["id"], 100)
    r_consumo, consumo = crear_consumo(client, cleaner, db, etapa["id"], mat["id"], 10, emp["id"])
    assert r_consumo.status_code in (200, 201), f"consumo → {r_consumo.status_code}: {r_consumo.text}"
    registrar_mano_obra(client, cleaner, etapa["id"], emp["id"], monto=30000.0)
    avanzar_etapa(client, etapa["id"], "COMPLETADA")

    final = finalizar_orden(client, orden["id"])
    assert final["tipo"] == "RETRABAJO"
    assert not final.get("estructura_generada"), (
        "el retrabajo NO debe generar receta del producto (la pieza es única)"
    )

    # ── Costo del retoque y revaluación de la pieza ──
    costo_ret = client.get(
        f"/api/v1/produccion/costo/{orden['id']}", headers=ADMIN_HEADERS
    ).json()
    assert abs(float(costo_ret["costo_material"]) - 20000.0) < 0.01
    assert abs(float(costo_ret["costo_mano_obra"]) - 30000.0) < 0.01
    y = float(costo_ret["costo_total"])
    # El total del retoque = materiales + mano de obra + gastos de sección
    # (el % vigente de la regla; puede ser 0 según la configuración).
    assert abs(y - (20000.0 + 30000.0 + float(costo_ret["costo_gastos"]))) < 0.01
    assert y >= 50000.0

    stock, costo_nuevo = stock_y_costo(db, pieza["id"])
    assert stock == 1.0, "la pieza vuelve al showroom (no se duplica)"
    assert abs(costo_nuevo - (55000.0 + y)) < 0.01, (
        f"la pieza debe volver con X+Y = {55000.0 + y}, llegó {costo_nuevo}"
    )

    entrada = db.execute(text(
        "SELECT id FROM movimiento_producto_inventario "
        "WHERE producto_id = :p AND tipo = 'ENTRADA' "
        "AND referencia_tipo = 'PRODUCCION_RETRABAJO' AND referencia_id = :o"
    ), {"p": pieza["id"], "o": orden["id"]}).fetchone()
    assert entrada is not None, "falta el movimiento de entrada del retrabajo"

    # Ya no está abierto: el chip EN RETRABAJO desaparece.
    abiertos = client.get("/api/v1/produccion/orden/retrabajos-abiertos", headers=ADMIN_HEADERS).json()
    assert not any(o["id"] == orden["id"] for o in abiertos)

    # ── El catálogo quedó intacto: coste/precio de siempre y sin receta nueva ──
    prod = client.get(f"/api/v1/producto/{pieza['id']}", headers=ADMIN_HEADERS).json()
    assert abs(float(prod["precio_costo_base"]) - 30000.0) < 0.01, (
        "el retrabajo no debe reescribir el costo base del producto"
    )
    assert abs(float(prod["precio_venta_base"]) - 100000.0) < 0.01
    n_estructura = db.execute(text(
        "SELECT COUNT(*) FROM seccion_producto WHERE producto_id = :p"
    ), {"p": pieza["id"]}).scalar()
    assert n_estructura == 0, "no debe generarse estructura/receta desde un retrabajo"


# ---------------------------------------------------------------------------
# 2. Una pieza sin stock no se puede retrabajar
# ---------------------------------------------------------------------------
def test_retrabajo_requiere_stock(client, db, cleaner):
    pieza = crear_producto_exhibicion(client, cleaner)  # sin entrada al showroom
    r = abrir_retrabajo(client, cleaner, pieza["id"])
    assert r.status_code == 400
    assert "no tiene stock" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 3. Solo piezas de exhibición entran por esta vía
# ---------------------------------------------------------------------------
def test_retrabajo_solo_piezas_de_exhibicion(client, db, cleaner):
    prod = crear_producto(client, cleaner)  # fabricado normal, no exhibición
    r = abrir_retrabajo(client, cleaner, prod["id"])
    assert r.status_code == 400
    assert "exhibición" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. Un solo retrabajo abierto por pieza
# ---------------------------------------------------------------------------
def test_retrabajo_unico_abierto(client, db, cleaner):
    pieza = crear_producto_exhibicion(client, cleaner)
    entrar_pieza_showroom(client, cleaner, db, pieza["id"], costo=55000.0)

    r1 = abrir_retrabajo(client, cleaner, pieza["id"])
    assert r1.status_code == 201
    r2 = abrir_retrabajo(client, cleaner, pieza["id"])
    assert r2.status_code == 400
    assert "ya hay un retrabajo" in r2.json()["detail"].lower()

    registrar_inventario_producto(db, cleaner, pieza["id"])


# ---------------------------------------------------------------------------
# 5. Cancelar el retrabajo devuelve la pieza con su costo ORIGINAL
# ---------------------------------------------------------------------------
def test_cancelar_retrabajo_devuelve_pieza(client, db, cleaner):
    pieza = crear_producto_exhibicion(client, cleaner)
    entrar_pieza_showroom(client, cleaner, db, pieza["id"], costo=55000.0)

    r = abrir_retrabajo(client, cleaner, pieza["id"])
    assert r.status_code == 201, f"abrir retrabajo → {r.status_code}: {r.text}"
    orden = r.json()
    stock, _ = stock_y_costo(db, pieza["id"])
    assert stock == 0.0

    rc = client.put(f"/api/v1/produccion/orden/{orden['id']}/estado",
                    params={"estado": "CANCELADA"}, headers=ADMIN_HEADERS)
    assert rc.status_code == 200, f"cancelar → {rc.status_code}: {rc.text}"

    stock, costo = stock_y_costo(db, pieza["id"])
    assert stock == 1.0, "la pieza vuelve al showroom al cancelar"
    assert costo == 55000.0, "vuelve con su costo original (sin el retoque)"

    entrada = db.execute(text(
        "SELECT observaciones FROM movimiento_producto_inventario "
        "WHERE producto_id = :p AND tipo = 'ENTRADA' "
        "AND referencia_tipo = 'PRODUCCION_RETRABAJO' AND referencia_id = :o"
    ), {"p": pieza["id"], "o": orden["id"]}).fetchone()
    assert entrada is not None and "cancelado" in (entrada[0] or "").lower()

    registrar_inventario_producto(db, cleaner, pieza["id"])


# ---------------------------------------------------------------------------
# 6. Eliminar un retrabajo recién abierto (sin etapas) también devuelve la pieza
# ---------------------------------------------------------------------------
def test_eliminar_retrabajo_sin_etapas_devuelve_pieza(client, db, cleaner):
    pieza = crear_producto_exhibicion(client, cleaner)
    entrar_pieza_showroom(client, cleaner, db, pieza["id"], costo=55000.0)

    r = abrir_retrabajo(client, cleaner, pieza["id"])
    assert r.status_code == 201, f"abrir retrabajo → {r.status_code}: {r.text}"
    orden = r.json()

    rd = client.delete(f"/api/v1/produccion/orden/{orden['id']}", headers=ADMIN_HEADERS)
    assert rd.status_code == 204, f"eliminar → {rd.status_code}: {rd.text}"

    stock, costo = stock_y_costo(db, pieza["id"])
    assert stock == 1.0, "la pieza no debe quedar perdida fuera del showroom"
    assert costo == 55000.0

    registrar_inventario_producto(db, cleaner, pieza["id"])
