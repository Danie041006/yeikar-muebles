"""Pruebas del registro de facturas de inventario con pagos divididos."""
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.core.hora_ve import hoy_ve
from app.modules.inventory.schemas import CompraInventarioMultipleLinea
from conftest import ADMIN_HEADERS, VENTAS_HEADERS, _uniq, crear_material, crear_proveedor


@pytest.fixture
def compra_multiple_instalada(db):
    tabla = db.execute(text("SELECT to_regclass('compra_inventario_multiple')")).scalar()
    if tabla is None:
        pytest.skip("La migración de compra múltiple aún no está aplicada en esta BD.")


def _cuenta_cop(db) -> int:
    cuenta_id = db.execute(text(
        "SELECT mc.id FROM metodo_caja mc "
        "JOIN moneda m ON m.id = mc.moneda_id "
        "WHERE mc.activo = true AND m.codigo = 'COP' ORDER BY mc.id LIMIT 1"
    )).scalar()
    if cuenta_id is None:
        pytest.skip("No hay una cuenta activa en COP para probar la compra.")
    return int(cuenta_id)


def _crear_segunda_cuenta_cop(db, cleaner) -> int:
    moneda_id = db.execute(text("SELECT id FROM moneda WHERE codigo = 'COP' LIMIT 1")).scalar()
    if moneda_id is None:
        pytest.skip("No existe la moneda COP en la BD de pruebas.")
    cuenta_id = db.execute(text(
        "INSERT INTO metodo_caja (nombre, codigo, activo, orden, moneda_id) "
        "VALUES (:nombre, :codigo, true, 999, :moneda_id) RETURNING id"
    ), {
        "nombre": _uniq("cuenta_compra"),
        "codigo": _uniq("CTA_COMPRA"),
        "moneda_id": int(moneda_id),
    }).scalar()
    db.commit()
    cleaner.registrar("metodo_caja", cuenta_id)
    return int(cuenta_id)


def _catalogos_para_compra(db):
    nombres_tipo = ("COMPRA DE INSUMOS", "PAPELERIA DE OFICINA", "COMPRA INVENTARIO REVENTA")
    anteriores = set(db.execute(
        text("SELECT nombre FROM tipo_gasto WHERE nombre = ANY(:nombres)"),
        {"nombres": list(nombres_tipo)},
    ).scalars())
    return anteriores


def _registrar_catalogos_nuevos(db, cleaner, anteriores):
    filas = db.execute(
        text("SELECT id, nombre FROM tipo_gasto WHERE nombre = ANY(:nombres)"),
        {"nombres": ["COMPRA DE INSUMOS", "PAPELERIA DE OFICINA", "COMPRA INVENTARIO REVENTA"]},
    ).fetchall()
    for tipo_id, nombre in filas:
        if nombre not in anteriores:
            cleaner.registrar("tipo_gasto", tipo_id)


def _ids_gastos_compra(db, compra_id: int, cxp_id: int | None = None) -> list[int]:
    """El enlace interno identifica los gastos del test sin buscar por texto."""
    return list(db.execute(text(
        "SELECT id FROM gasto WHERE entrada_inventario_id = :id"
    ), {"id": compra_id}).scalars())


def _registrar_dependencias_compra(db, cleaner, compra_id: int, cxp_id: int | None):
    cleaner.registrar("compra_inventario_multiple", compra_id)
    if cxp_id:
        cleaner.registrar("cuenta_por_pagar", cxp_id)

    movimientos_material = db.execute(text(
        "SELECT id, material_id FROM movimiento_inventario "
        "WHERE referencia_tipo = 'COMPRA_INVENTARIO_MULTIPLE' AND referencia_id = :compra_id"
    ), {"compra_id": compra_id}).fetchall()
    for movimiento_id, material_id in movimientos_material:
        cleaner.registrar("movimiento_inventario", movimiento_id)
        cleaner.registrar("material", material_id)
        inventarios = db.execute(
            text("SELECT id FROM inventario WHERE material_id = :material_id"),
            {"material_id": material_id},
        ).scalars()
        cleaner.registrar_muchos("inventario", inventarios)

    movimientos_producto = db.execute(text(
        "SELECT id, producto_id FROM movimiento_producto_inventario "
        "WHERE referencia_tipo = 'COMPRA_INVENTARIO_MULTIPLE' AND referencia_id = :compra_id"
    ), {"compra_id": compra_id}).fetchall()
    for movimiento_id, producto_id in movimientos_producto:
        cleaner.registrar("movimiento_producto_inventario", movimiento_id)
        cleaner.registrar("producto", producto_id)
        inventarios = db.execute(
            text("SELECT id FROM producto_inventario WHERE producto_id = :producto_id"),
            {"producto_id": producto_id},
        ).scalars()
        cleaner.registrar_muchos("producto_inventario", inventarios)

    gastos = _ids_gastos_compra(db, compra_id, cxp_id)
    for gasto_id in gastos:
        cleaner.registrar("gasto", gasto_id)
        caja_ids = db.execute(text(
            "SELECT id FROM movimiento_caja WHERE referencia = :referencia"
        ), {"referencia": f"Gasto #{gasto_id}"}).scalars()
        cleaner.registrar_muchos("movimiento_caja", caja_ids)


def _post_compra(client, payload, headers=ADMIN_HEADERS):
    return client.post("/api/v1/inventario/compra-multiple", json=payload, headers=headers)


def test_schema_requiere_un_articulo_correcto():
    with pytest.raises(ValidationError):
        CompraInventarioMultipleLinea(
            tipo_item="MATERIAL",
            material_id=5,
            producto_id=7,
            cantidad=1,
            precio_unitario=100,
        )

    with pytest.raises(ValidationError):
        CompraInventarioMultipleLinea(
            tipo_item="PRODUCTO",
            producto_id=5,
            cantidad=Decimal("0.001"),
            precio_unitario=100,
        )

    with pytest.raises(ValidationError):
        CompraInventarioMultipleLinea(
            tipo_item="MATERIAL",
            material_id=0,
            cantidad=1,
            precio_unitario=100,
        )

    material_fraccionario = CompraInventarioMultipleLinea(
        tipo_item="MATERIAL",
        material_id=5,
        cantidad=Decimal("0.0001"),
        precio_unitario=100,
    )
    assert material_fraccionario.cantidad == Decimal("0.0001")

    with pytest.raises(ValidationError):
        CompraInventarioMultipleLinea(
            tipo_item="MATERIAL",
            material_id=5,
            cantidad=Decimal("1000000000000"),
            precio_unitario=100,
        )


def test_compra_multiple_exige_permiso_de_inventario(client):
    payload = {
        "operacion_id": str(uuid.uuid4()),
        "fecha": str(hoy_ve()),
        "lineas": [{
            "tipo_item": "MATERIAL",
            "material_id": 1,
            "cantidad": 1,
            "precio_unitario": 100,
        }],
    }
    respuesta = _post_compra(client, payload, headers=VENTAS_HEADERS)
    assert respuesta.status_code == 403, respuesta.text

    with pytest.raises(ValidationError):
        CompraInventarioMultipleLinea(
            tipo_item="MATERIAL",
            nuevo_material={"nombre": "   ", "unidad_medida_id": 2},
            cantidad=1,
            precio_unitario=100,
        )


def test_compra_multiple_explica_si_falta_la_migracion(client, db):
    tabla_compra = db.execute(
        text("SELECT to_regclass('public.compra_inventario_multiple')")
    ).scalar()
    if tabla_compra is not None:
        pytest.skip("La tabla de compra múltiple ya existe en esta BD.")

    respuesta = _post_compra(client, {
        "operacion_id": str(uuid.uuid4()),
        "fecha": str(hoy_ve()),
        "lineas": [{
            "tipo_item": "MATERIAL",
            "material_id": 1,
            "cantidad": 1,
            "precio_unitario": 100,
        }],
    })

    assert respuesta.status_code == 503, respuesta.text
    assert "migración de compras múltiples" in respuesta.json()["detail"]


def test_compra_multiple_registra_pagos_de_dos_cuentas_y_saldo(
    client, cleaner, db, compra_multiple_instalada,
):
    cuenta_uno = _cuenta_cop(db)
    cuenta_dos = _crear_segunda_cuenta_cop(db, cleaner)
    proveedor = crear_proveedor(client, cleaner)
    material_uno = crear_material(client, cleaner, costo_base=1000)
    material_dos = crear_material(client, cleaner, costo_base=1000)
    tipos_antes = _catalogos_para_compra(db)
    operacion_id = str(uuid.uuid4())
    payload = {
        "operacion_id": operacion_id,
        "fecha": str(hoy_ve()),
        "proveedor_id": proveedor["id"],
        "lineas": [
            {
                "tipo_item": "MATERIAL",
                "material_id": material_uno["id"],
                "cantidad": 2,
                "precio_unitario": 1000,
                "moneda_precio_id": 1,
                "descuento_porcentaje": 10,
                "llevada_unitaria": 25,
            },
            {
                "tipo_item": "MATERIAL",
                "material_id": material_dos["id"],
                "cantidad": 3,
                "precio_unitario": 1000,
                "moneda_precio_id": 1,
                "llevada_unitaria": 100,
            },
        ],
        "pagos": [
            {"metodo_caja_id": cuenta_uno, "monto": 1000},
            {"metodo_caja_id": cuenta_dos, "monto": 500},
        ],
    }

    respuesta = _post_compra(client, payload)
    assert respuesta.status_code == 201, respuesta.text
    compra = respuesta.json()
    assert Decimal(str(compra["total_en_moneda_base"])) == Decimal("5150.00")
    assert Decimal(str(compra["pagado_en_moneda_base"])) == Decimal("1500.00")
    assert Decimal(str(compra["saldo_en_moneda_base"])) == Decimal("3650.00")
    assert compra["cuenta_por_pagar_id"]
    assert len(compra["lineas"]) == 2

    compra_id = compra["compra_id"]
    _registrar_dependencias_compra(db, cleaner, compra_id, compra["cuenta_por_pagar_id"])
    _registrar_catalogos_nuevos(db, cleaner, tipos_antes)

    segundo_intento = _post_compra(client, payload)
    assert segundo_intento.status_code == 201, segundo_intento.text
    assert segundo_intento.json() == compra

    cantidad_movimientos = db.execute(text(
        "SELECT count(*) FROM movimiento_inventario "
        "WHERE referencia_tipo = 'COMPRA_INVENTARIO_MULTIPLE' AND referencia_id = :id"
    ), {"id": compra_id}).scalar_one()
    assert cantidad_movimientos == 2

    gastos = db.execute(text(
        "SELECT count(*), sum(monto_en_moneda_base) FROM gasto WHERE id = ANY(:ids)"
    ), {"ids": _ids_gastos_compra(db, compra_id, compra["cuenta_por_pagar_id"])}).one()
    assert gastos[0] == 3
    assert Decimal(str(gastos[1])) == Decimal("5150.00")

    movimientos_caja = db.execute(text(
        "SELECT count(*) FROM movimiento_caja mc "
        "JOIN gasto g ON mc.referencia = 'Gasto #' || g.id::text "
        "WHERE g.id = ANY(:ids)"
    ), {"ids": _ids_gastos_compra(db, compra_id, compra["cuenta_por_pagar_id"])}).scalar_one()
    assert movimientos_caja == 2


def test_compra_multiple_paga_completo_con_dos_pagos_de_la_misma_cuenta(
    client, cleaner, db, compra_multiple_instalada,
):
    cuenta = _cuenta_cop(db)
    material_uno = crear_material(client, cleaner, costo_base=10000)
    material_dos = crear_material(client, cleaner, costo_base=10000)
    nombre_proveedor = _uniq("proveedor_contado")
    tipos_antes = _catalogos_para_compra(db)
    payload = {
        "operacion_id": str(uuid.uuid4()),
        "fecha": str(hoy_ve()),
        "proveedor_nombre": nombre_proveedor,
        "lineas": [
            {
                "tipo_item": "MATERIAL",
                "material_id": material_uno["id"],
                "cantidad": 10,
                "precio_unitario": 10000,
                "moneda_precio_id": 1,
                "llevada_unitaria": 1000,
                "departamento": "TAPICERIA",
            },
            {
                "tipo_item": "MATERIAL",
                "material_id": material_dos["id"],
                "cantidad": 20,
                "precio_unitario": 10000,
                "moneda_precio_id": 1,
                "llevada_unitaria": 1000,
                "departamento": "TAPICERIA",
            },
        ],
        "pagos": [
            {"metodo_caja_id": cuenta, "monto": 300000, "observacion": "Factura 0012"},
            {"metodo_caja_id": cuenta, "monto": 30000},
        ],
    }

    respuesta = _post_compra(client, payload)
    assert respuesta.status_code == 201, respuesta.text
    compra = respuesta.json()
    assert Decimal(str(compra["total_en_moneda_base"])) == Decimal("330000.00")
    assert Decimal(str(compra["pagado_en_moneda_base"])) == Decimal("330000.00")
    assert Decimal(str(compra["saldo_en_moneda_base"])) == Decimal("0.00")
    assert not compra["cuenta_por_pagar_id"]

    compra_id = compra["compra_id"]
    _registrar_dependencias_compra(db, cleaner, compra_id, None)
    _registrar_catalogos_nuevos(db, cleaner, tipos_antes)
    proveedor_id = db.execute(text(
        "SELECT id FROM proveedor WHERE lower(nombre) = lower(:nombre)"
    ), {"nombre": nombre_proveedor}).scalar()
    if proveedor_id:
        cleaner.registrar("proveedor", proveedor_id)

    gastos_ids = _ids_gastos_compra(db, compra_id)
    total_gastos = db.execute(text(
        "SELECT count(*), sum(monto_en_moneda_base) FROM gasto WHERE id = ANY(:ids)"
    ), {"ids": gastos_ids}).one()
    assert total_gastos[0] == 2
    assert Decimal(str(total_gastos[1])) == Decimal("330000.00")

    conceptos = db.execute(text(
        "SELECT concepto FROM movimiento_caja WHERE referencia = ANY(:referencias) ORDER BY id"
    ), {"referencias": [f"Gasto #{gasto_id}" for gasto_id in gastos_ids]}).scalars().all()
    assert len(conceptos) == 2
    assert any(concepto.startswith("Factura 0012 · Entrada de inventario: ") for concepto in conceptos)
    assert any(
        concepto.startswith("Entrada de inventario: ") and "Factura 0012" not in concepto
        for concepto in conceptos
    )
    assert all("Entrada de inventario: 10 " in concepto for concepto in conceptos)
    assert all(material_uno["nombre"] in concepto for concepto in conceptos)
    assert all(material_dos["nombre"] in concepto for concepto in conceptos)
    assert all("Pago 1/2" not in concepto and "Pago 2/2" not in concepto for concepto in conceptos)
    assert all("Compra múltiple" not in concepto for concepto in conceptos)
    assert all(f"#{compra_id}" not in concepto for concepto in conceptos)


def test_compra_multiple_crea_material_producto_y_deuda_en_una_transaccion(
    client, cleaner, db, compra_multiple_instalada,
):
    proveedor = crear_proveedor(client, cleaner)
    unidad_id = db.execute(text("SELECT id FROM unidad_medida ORDER BY id LIMIT 1")).scalar()
    tipo_producto_id = db.execute(text("SELECT id FROM tipo_producto ORDER BY id LIMIT 1")).scalar()
    ubicacion_id = db.execute(text(
        "SELECT id FROM ubicacion WHERE activo = true ORDER BY id LIMIT 1"
    )).scalar()
    if not unidad_id or not tipo_producto_id or not ubicacion_id:
        pytest.skip("Faltan unidad, tipo de producto o ubicación en la BD de pruebas.")

    tipos_antes = _catalogos_para_compra(db)
    payload = {
        "operacion_id": str(uuid.uuid4()),
        "fecha": str(hoy_ve()),
        "proveedor_id": proveedor["id"],
        "lineas": [
            {
                "tipo_item": "MATERIAL",
                "nuevo_material": {
                    "nombre": _uniq("material_compra"),
                    "unidad_medida_id": int(unidad_id),
                    "departamento": "EBANISTERIA",
                },
                "cantidad": 2,
                "precio_unitario": 500,
                "moneda_precio_id": 1,
            },
            {
                "tipo_item": "PRODUCTO",
                "nuevo_producto": {
                    "nombre": _uniq("reventa_compra"),
                    "tipo_producto_id": int(tipo_producto_id),
                    "moneda_id": 1,
                },
                "cantidad": 1,
                "precio_unitario": 1000,
                "moneda_precio_id": 1,
                "ubicacion_id": int(ubicacion_id),
            },
        ],
        "pagos": [],
    }

    respuesta = _post_compra(client, payload)
    assert respuesta.status_code == 201, respuesta.text
    compra = respuesta.json()
    assert Decimal(str(compra["total_en_moneda_base"])) == Decimal("2000.00")
    assert Decimal(str(compra["saldo_en_moneda_base"])) == Decimal("2000.00")
    assert compra["cuenta_por_pagar_id"]

    compra_id = compra["compra_id"]
    _registrar_dependencias_compra(db, cleaner, compra_id, compra["cuenta_por_pagar_id"])
    _registrar_catalogos_nuevos(db, cleaner, tipos_antes)

    items = db.execute(text(
        "SELECT tipo_item, item_id, cantidad, total_en_moneda_base "
        "FROM jsonb_to_recordset((SELECT lineas_json::jsonb FROM compra_inventario_multiple WHERE id = :id)) "
        "AS x(tipo_item text, item_id bigint, cantidad numeric, total_en_moneda_base numeric)"
    ), {"id": compra_id}).fetchall()
    assert len(items) == 2
    material_id = next(row[1] for row in items if row[0] == "MATERIAL")
    producto_id = next(row[1] for row in items if row[0] == "PRODUCTO")

    material = db.execute(text(
        "SELECT departamento FROM material WHERE id = :id"
    ), {"id": material_id}).scalar_one()
    producto = db.execute(text(
        "SELECT es_reventa, precio_costo_base FROM producto WHERE id = :id"
    ), {"id": producto_id}).one()
    assert material == "EBANISTERIA"
    assert producto[0] is True
    assert Decimal(str(producto[1])) == Decimal("1000.00")

    deuda = db.execute(text(
        "SELECT monto, monto_pagado, monto_descontado FROM cuenta_por_pagar WHERE id = :id"
    ), {"id": compra["cuenta_por_pagar_id"]}).one()
    assert Decimal(str(deuda[0])) == Decimal("2000.00")
    assert Decimal(str(deuda[0] - deuda[1] - deuda[2])) == Decimal("2000.00")


def test_compra_multiple_revierte_catalogo_si_un_renglon_falla(
    client, cleaner, db, compra_multiple_instalada,
):
    unidad_id = db.execute(text("SELECT id FROM unidad_medida ORDER BY id LIMIT 1")).scalar()
    if not unidad_id:
        pytest.skip("No hay unidades de medida en la BD de pruebas.")
    nombre_material = _uniq("rollback_compra")
    operacion_id = str(uuid.uuid4())
    producto_inexistente_id = int(db.execute(
        text("SELECT COALESCE(MAX(id), 0) + 1 FROM producto")
    ).scalar_one())
    respuesta = _post_compra(client, {
        "operacion_id": operacion_id,
        "fecha": str(hoy_ve()),
        "lineas": [
            {
                "tipo_item": "MATERIAL",
                "nuevo_material": {"nombre": nombre_material, "unidad_medida_id": int(unidad_id)},
                "cantidad": 1,
                "precio_unitario": 100,
            },
            {
                "tipo_item": "PRODUCTO",
                "producto_id": producto_inexistente_id,
                "cantidad": 1,
                "precio_unitario": 100,
            },
        ],
    })
    assert respuesta.status_code == 400, respuesta.text

    material_id = db.execute(text(
        "SELECT id FROM material WHERE nombre = :nombre"
    ), {"nombre": nombre_material}).scalar()
    if material_id:
        cleaner.registrar("material", material_id)
        movimientos = db.execute(
            text("SELECT id FROM movimiento_inventario WHERE material_id = :id"),
            {"id": material_id},
        ).scalars()
        cleaner.registrar_muchos("movimiento_inventario", movimientos)
        inventarios = db.execute(
            text("SELECT id FROM inventario WHERE material_id = :id"),
            {"id": material_id},
        ).scalars()
        cleaner.registrar_muchos("inventario", inventarios)

    compra_id = db.execute(text(
        "SELECT id FROM compra_inventario_multiple WHERE operacion_id = :operacion_id"
    ), {"operacion_id": operacion_id}).scalar()
    if compra_id:
        _registrar_dependencias_compra(db, cleaner, int(compra_id), None)

    material_guardado = db.execute(text(
        "SELECT count(*) FROM material WHERE nombre = :nombre"
    ), {"nombre": nombre_material}).scalar_one()
    compra_guardada = db.execute(text(
        "SELECT count(*) FROM compra_inventario_multiple WHERE operacion_id = :operacion_id"
    ), {"operacion_id": operacion_id}).scalar_one()
    assert material_guardado == 0
    assert compra_guardada == 0
