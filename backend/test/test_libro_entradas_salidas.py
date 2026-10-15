"""
test_libro_entradas_salidas.py — Libro de Entradas y Salidas (inventario).

Verifica el endpoint GET /api/v1/inventario/libro: separación entradas
(ENTRADA + DEVOLUCION) vs salidas (SALIDA + DAÑO), zona del taller por
movimiento, costos, resumen por zona y filtros.

Ejecutar:
    cd backend && venv/bin/python -m pytest test/test_libro_entradas_salidas.py -v
"""
from sqlalchemy import text

import pytest

from conftest import (
    ADMIN_HEADERS,
    _uniq,
    crear_material,
    crear_producto,
    registrar_inventario_de_material,
)

from app.core.hora_ve import hoy_ve


def _movimiento(client, cleaner, material_id, tipo, cantidad, **extra):
    payload = {
        "material_id": material_id,
        "ubicacion_id": extra.pop("ubicacion_id", 1),
        "tipo": tipo,
        "cantidad": cantidad,
        **extra,
    }
    r = client.post("/api/v1/inventario/movimiento", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"movimiento {tipo} → {r.status_code}: {r.text}"
    body = r.json()
    cleaner.registrar("movimiento_inventario", body["id"])
    return body


def _libro(client, lado, **params):
    hoy = str(hoy_ve())
    r = client.get(
        "/api/v1/inventario/libro",
        params={"desde": hoy, "hasta": hoy, "lado": lado, **params},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, f"libro {lado} → {r.status_code}: {r.text}"
    return r.json()


def test_libro_separa_entradas_salidas_y_zonas(client, db, cleaner):
    """Entrada con zona (PINTURA) y costo + salida + devolución + daño: cada
    lado muestra lo suyo y el resumen divide los totales por zona."""
    material = crear_material(client, cleaner, costo_base=1000.0)
    _movimiento(client, cleaner, material["id"], "ENTRADA", 4,
                costo_unitario=250.0, departamento="PINTURA", llevada=50.0,
                descuento_porcentaje=10.0)
    _movimiento(client, cleaner, material["id"], "SALIDA", 2)
    _movimiento(client, cleaner, material["id"], "DEVOLUCION", 1)
    _movimiento(client, cleaner, material["id"], "DAÑO", 1)
    registrar_inventario_de_material(db, cleaner, material["id"])

    entradas = _libro(client, "ENTRADAS", buscar=material["nombre"])
    tipos = {f["tipo"] for f in entradas["filas"]}
    assert tipos == {"ENTRADA", "DEVOLUCION"}, f"Entradas no cuadra: {tipos}"
    assert entradas["resumen"]["lado"] == "ENTRADAS"
    assert entradas["resumen"]["movimientos"] == 2
    assert entradas["resumen"]["costo_total"] == 1000.0, "4 × 250 = 1000"

    # Los mismos campos del formulario de entrada viajan en la fila del libro.
    entrada_fila = next(f for f in entradas["filas"] if f["tipo"] == "ENTRADA")
    assert entrada_fila["llevada"] == 50.0
    assert entrada_fila["descuento"] == 10.0
    assert entrada_fila["pagado_desde"] is None, "Sin cuenta indicada no hay pago de contado"
    assert entrada_fila["fiado"] is False
    assert entrada_fila["categoria"] is None, "El insumo del test no tiene categoría"

    zona_pintura = next(z for z in entradas["resumen"]["por_zona"] if z["zona"] == "PINTURA")
    assert zona_pintura["movimientos"] == 1 and zona_pintura["costo"] == 1000.0
    # La devolución no tiene zona: cae en General y queda contada como sin costo.
    zona_general = next(z for z in entradas["resumen"]["por_zona"] if z["zona"] == "GENERAL")
    assert zona_general["movimientos"] == 1 and zona_general["sin_costo"] == 1

    salidas = _libro(client, "SALIDAS", buscar=material["nombre"])
    tipos = {f["tipo"] for f in salidas["filas"]}
    assert tipos == {"SALIDA", "DANO"}, f"Salidas no cuadra: {tipos}"
    assert salidas["resumen"]["movimientos"] == 2

    # Filtro por zona (clave canónica) y por nombre inexistente.
    solo_pintura = _libro(client, "ENTRADAS", buscar=material["nombre"], zona="PINTURA")
    assert [f["tipo"] for f in solo_pintura["filas"]] == ["ENTRADA"]
    sin_resultados = _libro(client, "ENTRADAS", buscar="zzz_no_existe_9999")
    assert sin_resultados["filas"] == []


def test_libro_incluye_productos(client, db, cleaner):
    """Las entradas de productos terminados/reventa entran al mismo libro con
    su costo y su origen."""
    producto = crear_producto(client, cleaner)
    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": producto["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 3,
        "costo_unitario": 500.0,
        "descuento_porcentaje": 15,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"movimiento producto → {r.status_code}: {r.text}"
    mov = r.json()
    cleaner.registrar("movimiento_producto_inventario", mov["id"])
    fila = db.execute(
        text("SELECT id FROM producto_inventario WHERE producto_id = :p"),
        {"p": producto["id"]},
    ).fetchone()
    if fila:
        cleaner.registrar("producto_inventario", fila[0])

    libro = _libro(client, "ENTRADAS", buscar=producto["nombre"])
    assert [f["item_tipo"] for f in libro["filas"]] == ["PRODUCTO"]
    fila_libro = libro["filas"][0]
    assert fila_libro["origen"] == "Manual"
    assert fila_libro["zona"] == "GENERAL"
    assert fila_libro["costo_total"] == 1500.0, "3 × 500 = 1500"
    assert fila_libro["descuento"] == 15.0, "El % del formulario de productos viaja al libro"


def test_libro_filtra_productos_por_categoria_y_tipo(client, db, cleaner):
    """Los grupos de productos del libro: por categoría (plásticos) y por tipo
    (reventa) — el producto del test se separa por ambos ejes."""
    import unicodedata

    from app.modules.catalogos.model import CategoriaInventario, TipoProducto

    def normalizar(texto: str) -> str:
        sin_tildes = unicodedata.normalize("NFD", str(texto).upper())
        return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")

    categorias = db.query(CategoriaInventario).filter(
        CategoriaInventario.tipo == "PRODUCTO"
    ).all()
    categoria = next((c for c in categorias if "PLASTIC" in normalizar(c.nombre)), None)
    tipo_revendido = db.query(TipoProducto).filter(TipoProducto.nombre.ilike("%Revendido%")).first()
    tipo_fabricado = db.query(TipoProducto).filter(TipoProducto.nombre.ilike("%Fabricado%")).first()
    assert categoria and tipo_revendido and tipo_fabricado, "Catálogos base de la BD dev"

    r = client.post("/api/v1/producto/", json={
        "nombre": _uniq("prod_plast"),
        "tipo_producto_id": tipo_revendido.id,
        "categoria_inventario_id": categoria.id,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"crear producto con categoría → {r.status_code}: {r.text}"
    producto = r.json()
    cleaner.registrar("producto", producto["id"])

    r = client.post("/api/v1/inventario/producto/movimiento", json={
        "producto_id": producto["id"],
        "ubicacion_id": 1,
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 100.0,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"movimiento producto → {r.status_code}: {r.text}"
    cleaner.registrar("movimiento_producto_inventario", r.json()["id"])
    fila = db.execute(
        text("SELECT id FROM producto_inventario WHERE producto_id = :p"),
        {"p": producto["id"]},
    ).fetchone()
    if fila:
        cleaner.registrar("producto_inventario", fila[0])

    # Por categoría (plásticos): aparece con su categoría visible.
    libro = _libro(client, "ENTRADAS", buscar=producto["nombre"],
                   tipo_item="PRODUCTO", categoria_id=categoria.id)
    assert [f["item_tipo"] for f in libro["filas"]] == ["PRODUCTO"]
    assert libro["filas"][0]["categoria"] == categoria.nombre

    # Por tipo: entra en Revendido y se excluye con Fabricado.
    por_revendido = _libro(client, "ENTRADAS", buscar=producto["nombre"],
                           tipo_item="PRODUCTO", tipo_producto_id=tipo_revendido.id)
    assert len(por_revendido["filas"]) == 1
    por_fabricado = _libro(client, "ENTRADAS", buscar=producto["nombre"],
                           tipo_item="PRODUCTO", tipo_producto_id=tipo_fabricado.id)
    assert por_fabricado["filas"] == []


def test_movimiento_sin_ubicacion_usa_deposito_predeterminado(client, db, cleaner):
    """El formulario de insumos ya no pide almacén: sin ubicación en el payload,
    el movimiento cae en el depósito principal y suma stock ahí."""
    material = crear_material(client, cleaner)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "ENTRADA",
        "cantidad": 3,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"movimiento sin ubicación → {r.status_code}: {r.text}"
    mov = r.json()
    cleaner.registrar("movimiento_inventario", mov["id"])
    registrar_inventario_de_material(db, cleaner, material["id"])

    deposito = db.execute(text(
        "SELECT id FROM ubicacion WHERE activo AND nombre LIKE '%Principal%' ORDER BY id LIMIT 1"
    )).fetchone()
    assert deposito, "La BD dev debe tener el depósito principal"
    assert mov["ubicacion_id"] == deposito[0]

    fila = db.execute(text(
        "SELECT cantidad FROM inventario WHERE material_id = :m AND ubicacion_id = :u"
    ), {"m": material["id"], "u": deposito[0]}).fetchone()
    assert fila and float(fila[0]) == 3.0


def test_libro_muestra_cuenta_de_pago_y_descuento(client, db, cleaner):
    """La entrada pagada de contado expone la cuenta usada y el % de descuento:
    los campos "¿Desde qué cuenta pagaste?" y "% Descuento" del formulario."""
    cuenta = db.execute(text("SELECT id, nombre FROM metodo_caja ORDER BY id LIMIT 1")).fetchone()
    if cuenta is None:
        pytest.skip("No hay cuentas de caja en la BD de pruebas")

    material = crear_material(client, cleaner, costo_base=100.0)
    r = client.post("/api/v1/inventario/movimiento", json={
        "material_id": material["id"],
        "tipo": "ENTRADA",
        "cantidad": 2,
        "costo_unitario": 100.0,
        "pagado_desde_metodo_caja_id": cuenta.id,
        "descuento_porcentaje": 10,
    }, headers=ADMIN_HEADERS)
    assert r.status_code == 201, f"entrada de contado → {r.status_code}: {r.text}"
    mov = r.json()
    cleaner.registrar("movimiento_inventario", mov["id"])
    registrar_inventario_de_material(db, cleaner, material["id"])
    # El pago de contado genera el gasto de compra + su salida de caja espejo
    # ("Gasto #N"): se registran para el teardown.
    gastos = db.execute(text(
        "SELECT id FROM gasto WHERE descripcion LIKE :pat"
    ), {"pat": f"Compra {material['nombre']}%"}).fetchall()
    assert gastos, "El pago de contado debe generar el gasto de compra"
    for (gasto_id,) in gastos:
        cleaner.registrar("gasto", gasto_id)
        cleaner.registrar_caja_ref(f"Gasto #{gasto_id}")

    libro = _libro(client, "ENTRADAS", buscar=material["nombre"])
    fila = libro["filas"][0]
    assert fila["pagado_desde"] == cuenta.nombre
    assert fila["descuento"] == 10.0
    assert fila["fiado"] is False


def test_libro_muestra_entrada_fiada(client, db, cleaner):
    """Una entrada fiada expone la deuda en el libro: proveedor y estado
    (el campo "Fiar" del formulario)."""
    material = crear_material(client, cleaner, costo_base=100.0)
    nombre_proveedor = _uniq("prov_fiar")
    mov = _movimiento(client, cleaner, material["id"], "ENTRADA", 2,
                      costo_unitario=100.0, proveedor_nombre=nombre_proveedor, fiar=True)
    registrar_inventario_de_material(db, cleaner, material["id"])

    # La deuda nace enlazada al movimiento (origen_id) + su gasto sin caja.
    deuda = db.execute(text(
        "SELECT c.id, c.gasto_id FROM cuenta_por_pagar c "
        "WHERE c.origen_tipo = 'ENTRADA_INVENTARIO' AND c.origen_id = :m"
    ), {"m": mov["id"]}).fetchone()
    assert deuda, "Fiar debe crear la cuenta por pagar"
    cleaner.registrar("cuenta_por_pagar", deuda.id)
    if deuda.gasto_id:
        cleaner.registrar("gasto", deuda.gasto_id)
    proveedor = db.execute(text(
        "SELECT id FROM proveedor WHERE nombre = :n"
    ), {"n": nombre_proveedor}).fetchone()
    if proveedor:
        cleaner.registrar("proveedor", proveedor.id)

    libro = _libro(client, "ENTRADAS", buscar=material["nombre"])
    fila = libro["filas"][0]
    assert fila["fiado"] is True
    assert fila["fiado_a"] == nombre_proveedor
    assert fila["fiado_estado"] == "PENDIENTE"
    assert fila["pagado_desde"] is None


def test_libro_valida_parametros(client):
    """Lado inválido o rango invertido devuelven 400."""
    hoy = str(hoy_ve())
    r = client.get(
        "/api/v1/inventario/libro",
        params={"desde": hoy, "hasta": hoy, "lado": "AJUSTES"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, r.text
    r = client.get(
        "/api/v1/inventario/libro",
        params={"desde": "2026-10-02", "hasta": "2026-10-01", "lado": "ENTRADAS"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 400, r.text
