"""
test_producto_composicion.py — Composición de un conjunto en piezas (Fase 1).

Un comedor = mesa ×1 + sillas ×6. Cada pieza es un producto del catálogo con
su costo y su precio; la composición NO toca la receta de materiales.

Cubre:
  1. Definir la composición: marca el conjunto y las piezas, y concilia la
     suma de las piezas contra el costo/precio del conjunto.
  2. Reemplazo completo (contrato de lista): quitar piezas y vaciar.
  3. Validaciones: auto-referencia, duplicados, pieza inexistente y conjuntos
     anidados.
  4. Permisos: escribir la composición es solo Dueño/Administrador.
  5. Un producto que es pieza de un conjunto no se puede borrar (409 claro).
  6. La tabla nueva quedó dentro de la réplica offline (trigger de sync).

Ejecutar:  pytest test/test_producto_composicion.py -v
"""
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text

from conftest import ADMIN_HEADERS, VENTAS_HEADERS


def _uniq(prefijo: str) -> str:
    return f"test_{prefijo}_{uuid.uuid4().hex[:8]}"


def _producto(client, cleaner, costo=None, precio=None, **extra) -> dict:
    payload = {
        "nombre": _uniq("pieza"),
        "tipo_producto_id": 2,
        "moneda_id": 1,
        "activo": True,
        "precio_costo_base": costo,
        "precio_venta_base": precio,
    }
    payload.update(extra)
    r = client.post("/api/v1/producto/", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear producto → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("producto", body["id"])
    return body


def _poner_piezas(client, producto_id, piezas, headers=ADMIN_HEADERS):
    return client.put(
        f"/api/v1/producto/{producto_id}/piezas",
        json={"piezas": piezas},
        headers=headers,
    )


def test_composicion_marca_conjunto_y_piezas_y_concilia(client, cleaner):
    mesa = _producto(client, cleaner, costo=500000.0, precio=700000.0)
    sillas = _producto(client, cleaner, costo=80000.0, precio=112000.0)
    comedor = _producto(client, cleaner, costo=900000.0, precio=1300000.0)

    r = _poner_piezas(client, comedor["id"], [
        {"pieza_producto_id": mesa["id"], "cantidad": 1, "orden": 0},
        {"pieza_producto_id": sillas["id"], "cantidad": 6, "orden": 1},
    ])
    assert r.status_code == 200, f"PUT piezas → {r.status_code}: {r.text}"
    body = r.json()
    assert body["es_conjunto"] is True
    assert len(body["piezas"]) == 2

    # Suma de las piezas: 1×500.000 + 6×80.000 = 980.000 de costo y
    # 1×700.000 + 6×112.000 = 1.372.000 de precio.
    resumen = body["resumen"]
    assert abs(resumen["costo_piezas"] - 980000.0) < 0.01
    assert abs(resumen["precio_piezas"] - 1372000.0) < 0.01
    # Conciliación contra el conjunto: se REPORTA la diferencia, no se corrige.
    assert abs(resumen["diferencia_costo"] - (900000.0 - 980000.0)) < 0.01
    assert abs(resumen["diferencia_precio"] - (1300000.0 - 1372000.0)) < 0.01
    assert resumen["piezas_sin_costo"] == 0
    assert resumen["piezas_sin_precio"] == 0

    # Las piezas quedan marcadas como tales y el conjunto se expone en la ficha.
    for pieza in (mesa, sillas):
        detalle = client.get(f"/api/v1/producto/{pieza['id']}", headers=ADMIN_HEADERS).json()
        assert detalle["es_pieza"] is True
        assert detalle["es_conjunto"] is False
    ficha = client.get(f"/api/v1/producto/{comedor['id']}", headers=ADMIN_HEADERS).json()
    assert ficha["es_conjunto"] is True
    # La receta de materiales sigue siendo la de siempre (vacía aquí): la
    # composición no la toca.
    receta = client.get(f"/api/v1/producto/{comedor['id']}/receta", headers=ADMIN_HEADERS)
    assert receta.status_code == 200 and receta.json() == []


def test_reemplazo_completo_y_vaciar(client, cleaner):
    mesa = _producto(client, cleaner, costo=1000.0, precio=1400.0)
    sillas = _producto(client, cleaner, costo=100.0, precio=140.0)
    comedor = _producto(client, cleaner)

    assert _poner_piezas(client, comedor["id"], [
        {"pieza_producto_id": mesa["id"], "cantidad": 1},
        {"pieza_producto_id": sillas["id"], "cantidad": 4},
    ]).status_code == 200

    # Reemplazo: solo queda la mesa (las sillas salen de la composición).
    r = _poner_piezas(client, comedor["id"], [{"pieza_producto_id": mesa["id"], "cantidad": 1}])
    assert r.status_code == 200
    body = r.json()
    assert body["es_conjunto"] is True
    assert [p["pieza_producto_id"] for p in body["piezas"]] == [mesa["id"]]
    assert abs(body["resumen"]["costo_piezas"] - 1000.0) < 0.01

    # Vaciar deja el producto sin conjunto (vuelve a ser un mueble simple).
    r = _poner_piezas(client, comedor["id"], [])
    assert r.status_code == 200
    assert r.json()["es_conjunto"] is False
    assert r.json()["piezas"] == []


def test_validaciones_de_la_composicion(client, cleaner):
    mesa = _producto(client, cleaner)
    comedor = _producto(client, cleaner)

    # Auto-referencia.
    r = _poner_piezas(client, comedor["id"], [{"pieza_producto_id": comedor["id"], "cantidad": 1}])
    assert r.status_code == 400 and "sí mismo" in r.text

    # Pieza inexistente.
    r = _poner_piezas(client, comedor["id"], [{"pieza_producto_id": 999999999, "cantidad": 1}])
    assert r.status_code == 400 and "no existen" in r.text

    # Duplicados: los rechaza el esquema (422).
    r = _poner_piezas(client, comedor["id"], [
        {"pieza_producto_id": mesa["id"], "cantidad": 1},
        {"pieza_producto_id": mesa["id"], "cantidad": 2},
    ])
    assert r.status_code == 422

    # Cantidad inválida.
    r = _poner_piezas(client, comedor["id"], [{"pieza_producto_id": mesa["id"], "cantidad": 0}])
    assert r.status_code == 422

    # Un conjunto no puede ser pieza de otro conjunto.
    assert _poner_piezas(client, comedor["id"], [
        {"pieza_producto_id": mesa["id"], "cantidad": 1}
    ]).status_code == 200
    otro = _producto(client, cleaner)
    r = _poner_piezas(client, otro["id"], [{"pieza_producto_id": comedor["id"], "cantidad": 1}])
    assert r.status_code == 400 and "conjunto" in r.text


def test_escribir_composicion_es_solo_admin(client, cleaner):
    mesa = _producto(client, cleaner)
    comedor = _producto(client, cleaner)
    r = _poner_piezas(
        client, comedor["id"],
        [{"pieza_producto_id": mesa["id"], "cantidad": 1}],
        headers=VENTAS_HEADERS,
    )
    assert r.status_code == 403, f"VENTAS no debe escribir la composición: {r.status_code}"
    # La lectura sigue disponible para quien tenga el módulo de productos.
    lectura = client.get(f"/api/v1/producto/{comedor['id']}/piezas", headers=ADMIN_HEADERS)
    assert lectura.status_code == 200


def test_no_se_borra_un_producto_que_es_pieza(client, cleaner):
    mesa = _producto(client, cleaner)
    comedor = _producto(client, cleaner)
    assert _poner_piezas(client, comedor["id"], [
        {"pieza_producto_id": mesa["id"], "cantidad": 1}
    ]).status_code == 200

    r = client.delete(f"/api/v1/producto/{mesa['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 409 and "conjunto" in r.text

    # Quitándolo de la composición ya se puede borrar.
    assert _poner_piezas(client, comedor["id"], []).status_code == 200
    r = client.delete(f"/api/v1/producto/{mesa['id']}", headers=ADMIN_HEADERS)
    assert r.status_code == 204


def test_producto_inexistente_devuelve_404(client):
    r = client.get("/api/v1/producto/999999999/piezas", headers=ADMIN_HEADERS)
    assert r.status_code == 404


def test_composicion_entra_a_la_replica_offline(client, db, cleaner):
    """La tabla nueva debe replicar como el resto del negocio (sync offline)."""
    row = db.execute(text(
        "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_sync_cambio' "
        "AND tgrelid = to_regclass('producto_pieza') AND NOT tgisinternal"
    )).fetchone()
    assert row is not None, "producto_pieza quedó fuera de la bitácora de sync"
