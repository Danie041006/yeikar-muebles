"""Tests para el cálculo de costos y precios de productos de reventa (colchones, etc.)
y verificación de descuento / ganancia porcentual."""
from decimal import Decimal
from app.modules.productos.model import Producto
from app.modules.productos.cost_service import calcular_costo_producto
from app.modules.inventory.service import registrar_movimiento_producto
from app.modules.inventory.schemas import MovimientoProductoCreate


def test_costeo_producto_reventa_usd(db, cleaner):
    """Un producto de reventa en USD con precio_costo_base calcula su precio de venta
    usando ganancia% e impuestos sin redondear a millares COP (mantiene 2 decimales)."""
    prod = Producto(
        nombre="COLCHON ORTOPEDICO QUEEN",
        tipo_producto_id=2,
        es_reventa=True,
        moneda_id=2,  # USD
        precio_costo_base=Decimal("90.00"),  # Costo neto con descuento
        precio_venta_base=None,
        activo=True,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    cleaner.registrar("producto", prod.id)

    # Costeo con 7% impuestos y 40% ganancia
    resultado = calcular_costo_producto(
        db=db,
        producto_id=prod.id,
        nuevo_ancho=Decimal("1.0"),
        nuevo_largo=Decimal("1.0"),
        ganancia_porcentaje=Decimal("40.0"),
        impuesto_porcentaje=Decimal("7.0"),
    )

    resumen = resultado["resumen_costos"]
    assert resumen["costo_produccion"] == 90.0
    assert resumen["costo_total"] == 90.0
    # 90 * 0.07 = 6.30
    assert resumen["impuestos"] == 6.30
    # Base con impuestos = 96.30
    assert resumen["base_con_impuestos"] == 96.30
    # 96.30 * 1.40 = 134.82 USD
    assert resumen["precio_sin_iva"] == 134.82
    assert resumen["precio_venta"] == 134.82


def test_costeo_producto_reventa_cop(db, cleaner):
    """Un producto de reventa en COP redondea al millar hacia arriba."""
    prod = Producto(
        nombre="ALMOHADA MEMORY FOAM",
        tipo_producto_id=2,
        es_reventa=True,
        moneda_id=1,  # COP
        precio_costo_base=Decimal("50000.00"),
        activo=True,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    cleaner.registrar("producto", prod.id)

    resultado = calcular_costo_producto(
        db=db,
        producto_id=prod.id,
        nuevo_ancho=Decimal("1.0"),
        nuevo_largo=Decimal("1.0"),
        ganancia_porcentaje=Decimal("40.0"),
        impuesto_porcentaje=Decimal("7.0"),
    )

    resumen = resultado["resumen_costos"]
    assert resumen["costo_total"] == 50000.0
    # 50000 * 1.07 = 53500; 53500 * 1.40 = 74900 -> redondeo millar COP = 75000
    assert resumen["precio_venta"] == 75000.0
    assert int(resumen["precio_venta"]) % 1000 == 0


def test_entrada_inventario_actualiza_precio_costo_base(db, cleaner):
    """Al registrar una entrada de inventario de producto con costo_unitario,
    se actualiza el costo promedio y el precio_costo_base del producto."""
    prod = Producto(
        nombre="COLCHON MATRIMONIAL",
        tipo_producto_id=2,
        es_reventa=True,
        moneda_id=2,  # USD
        precio_costo_base=Decimal("100.00"),
        activo=True,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    cleaner.registrar("producto", prod.id)

    # Entrada de inventario con costo neto de 85.00 (después de descuento)
    mov = MovimientoProductoCreate(
        producto_id=prod.id,
        ubicacion_id=1,
        tipo="ENTRADA",
        cantidad=Decimal("5.0"),
        costo_unitario=Decimal("85.00"),
        observaciones="Entrada con 15% de descuento por compra al mayor",
    )
    db_mov = registrar_movimiento_producto(db, mov)
    db.commit()
    db.refresh(prod)

    assert prod.precio_costo_base == Decimal("85.00")
