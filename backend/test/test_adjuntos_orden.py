# -*- coding: utf-8 -*-
"""
test_adjuntos_orden.py — Orden de las fotos de PRODUCTO (portada = primera
subida) y regresión del orden opuesto para los comprobantes.

Motivo (caso real): un mueble se entiende mejor con 2 fotos. Las fotos de
PRODUCTO se listan en ORDEN DE SUBIDA: la primera es la portada (cotización,
tarjetas, factura y hero de la Hoja de Trabajo) y las nuevas se agregan como
vistas adicionales.

Los comprobantes (CRUDO/PAGO/GASTO/COMPRA) conservan "la más reciente
primero": en crudo, subir una foto nueva la convierte en la visible
(flujo "cambiar foto" del inventario — _foto_crudo).

Ejecutar:
  cd backend && venv/bin/python -m pytest test/test_adjuntos_orden.py -v
"""
import uuid as _uuid

from sqlalchemy import text

from conftest import ADMIN_HEADERS, crear_producto
from helpers_e2e import area_id, crear_empleado, crear_etapa


def _insertar_adjunto(db, cleaner, entidad_tipo: str, entidad_id: int, nombre: str):
    """Inserta un adjunto real (misma vía que el alta: uuid público).
    Devuelve (id, uuid)."""
    u = str(_uuid.uuid4())
    aid = db.execute(text(
        "INSERT INTO adjunto (entidad_tipo, entidad_id, uuid, nombre_original, mime, tamano, archivo) "
        "VALUES (:t, :e, :u, :n, 'image/webp', 4, :b) RETURNING id"
    ), {"t": entidad_tipo, "e": entidad_id, "u": u, "n": nombre, "b": b"abcd"}).scalar()
    db.commit()
    cleaner.registrar("adjunto", int(aid))
    return int(aid), u


# ---------------------------------------------------------------------------
# 1. Producto: la primera foto subida es la portada (fotos[0]), en detalle y
#    en listado (el listado usa el batch, que debe respetar el mismo orden).
# ---------------------------------------------------------------------------
def test_fotos_producto_en_orden_de_subida(client, db, cleaner):
    producto = crear_producto(client, cleaner)
    primera_id, _ = _insertar_adjunto(db, cleaner, "PRODUCTO", producto["id"], "portada.webp")
    segunda_id, _ = _insertar_adjunto(db, cleaner, "PRODUCTO", producto["id"], "detalle.webp")

    # Detalle: usa la propiedad producto.fotos (consultas por producto)
    r = client.get(f"/api/v1/producto/{producto['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    fotos = r.json()["fotos"]
    assert [f["id"] for f in fotos] == [primera_id, segunda_id], (
        f"la portada debe ser la PRIMERA subida → {fotos}"
    )
    assert fotos[0]["url"].startswith("/api/v1/adjunto/publico/"), fotos

    # Listado: usa adjuntos_info_batch (una query para toda la página)
    r_lista = client.get(
        "/api/v1/producto/",
        params={"buscar": producto["nombre"]},
        headers=ADMIN_HEADERS,
    )
    assert r_lista.status_code == 200, r_lista.text
    fila = next(p for p in r_lista.json() if p["id"] == producto["id"])
    assert [f["id"] for f in fila["fotos"]] == [primera_id, segunda_id], (
        f"el listado debe conservar el orden de subida → {fila['fotos']}"
    )


# ---------------------------------------------------------------------------
# 2. Hoja de Trabajo: la receta de referencia expone TODAS las fotos en orden
#    de subida (el hero usa la primera; las demás son "Vistas adicionales").
# ---------------------------------------------------------------------------
def test_referencia_receta_expone_fotos_en_orden(client, db, cleaner):
    pieza = crear_producto(client, cleaner)
    _, uuid1 = _insertar_adjunto(db, cleaner, "PRODUCTO", pieza["id"], "portada.webp")
    _, uuid2 = _insertar_adjunto(db, cleaner, "PRODUCTO", pieza["id"], "detalle.webp")

    r_orden = client.post("/api/v1/produccion/orden/", json={
        "estado": "PENDIENTE", "es_stock": True, "producto_id": pieza["id"],
    }, headers=ADMIN_HEADERS)
    assert r_orden.status_code == 201, f"crear orden → {r_orden.status_code}: {r_orden.text}"
    orden = r_orden.json()
    cleaner.registrar("orden_produccion", orden["id"])

    empleado = crear_empleado(client, cleaner)
    etapa = crear_etapa(client, cleaner, orden["id"], area_id(db, "Ebanistería"), empleado["id"])

    r = client.get(f"/api/v1/produccion/etapa/{etapa['id']}/referencia-receta",
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    fotos = r.json()["producto_fotos"]
    assert len(fotos) == 2, f"debe exponer ambas fotos → {fotos}"
    assert f"/publico/{uuid1}/" in fotos[0]["url"], (
        f"la primera del documento debe ser la portada → {fotos}"
    )
    assert f"/publico/{uuid2}/" in fotos[1]["url"], fotos


# ---------------------------------------------------------------------------
# 3. Regresión: crudo conserva "la más reciente primero" (cambiar foto sube
#    una nueva y esa pasa a ser la visible).
# ---------------------------------------------------------------------------
def test_crudo_conserva_la_foto_mas_reciente(client, db, cleaner):
    r = client.post("/api/v1/produccion/crudo/", json={
        "nombre": "test_crudo_orden_foto",
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear crudo → {r.status_code}: {r.text}"
    crudo = r.json()
    cleaner.registrar("producto_crudo_inventario", crudo["id"])
    assert crudo["foto_url"] is None

    _, uuid1 = _insertar_adjunto(db, cleaner, "CRUDO", crudo["id"], "foto-1.webp")
    r1 = client.get(f"/api/v1/produccion/crudo/{crudo['id']}", headers=ADMIN_HEADERS)
    assert r1.status_code == 200, r1.text
    assert f"/publico/{uuid1}/" in r1.json()["foto_url"], r1.json()

    _, uuid2 = _insertar_adjunto(db, cleaner, "CRUDO", crudo["id"], "foto-2.webp")
    r2 = client.get(f"/api/v1/produccion/crudo/{crudo['id']}", headers=ADMIN_HEADERS)
    assert r2.status_code == 200, r2.text
    assert f"/publico/{uuid2}/" in r2.json()["foto_url"], (
        f"en crudo la foto visible debe ser la MÁS RECIENTE → {r2.json()}"
    )
