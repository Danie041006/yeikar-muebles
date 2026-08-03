"""informe mensual: costos venta, tasas, catalagos flexibles

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-08-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------
    # 1. Columnas nuevas en modelos existentes
    # ------------------------------------------------------------
    # Venta: tasa + total en moneda base
    op.add_column("venta", sa.Column("tasa_cambio", sa.Numeric(15, 6), nullable=False, server_default="1.0"))
    op.add_column("venta", sa.Column("total_en_moneda_base", sa.Numeric(15, 2), nullable=True))

    # DetalleVenta: snapshots de costos
    op.add_column("detalle_venta", sa.Column("costo_unitario", sa.Numeric(15, 2), nullable=True))
    op.add_column("detalle_venta", sa.Column("porcentaje_ganancia", sa.Numeric(5, 2), nullable=True))
    op.add_column("detalle_venta", sa.Column("utilidad", sa.Numeric(15, 2), nullable=True))
    op.add_column("detalle_venta", sa.Column("descuento", sa.Numeric(15, 2), nullable=True, server_default="0"))

    # DetallePedido: snapshots de costos
    op.add_column("detalle_pedido", sa.Column("costo_unitario", sa.Numeric(15, 2), nullable=True))
    op.add_column("detalle_pedido", sa.Column("porcentaje_ganancia", sa.Numeric(5, 2), nullable=True))

    # Compra: tasa + total base + tipo de pago
    op.add_column("compra", sa.Column("tipo_pago", sa.String(50), nullable=False, server_default="CREDITO"))
    op.add_column("compra", sa.Column("tasa_cambio", sa.Numeric(15, 6), nullable=False, server_default="1.0"))
    op.add_column("compra", sa.Column("total_en_moneda_base", sa.Numeric(15, 2), nullable=True))

    # ------------------------------------------------------------
    # 2. Tablas nuevas
    # ------------------------------------------------------------
    op.create_table(
        "concepto_reporte",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("seccion", sa.String(50), nullable=False, server_default="INVENTARIO"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.func.now()),
    )

    op.create_table(
        "valor_concepto_mensual",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("mes", sa.String(7), nullable=False, index=True),
        sa.Column("concepto_id", sa.BigInteger(), sa.ForeignKey("concepto_reporte.id", ondelete="CASCADE"), nullable=False),
        sa.Column("valor_inicial", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("valor_final", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("moneda_id", sa.BigInteger(), sa.ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False, server_default="1"),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.func.now()),
    )

    op.create_table(
        "metodo_caja",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("codigo", sa.String(50), nullable=False, unique=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.func.now()),
    )

    op.create_table(
        "movimiento_caja",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("metodo_caja_id", sa.BigInteger(), sa.ForeignKey("metodo_caja.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False),
        sa.Column("moneda_id", sa.BigInteger(), sa.ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False, server_default="1"),
        sa.Column("tasa_cambio", sa.Numeric(15, 6), nullable=False, server_default="1.0"),
        sa.Column("monto_en_moneda_base", sa.Numeric(15, 2), nullable=True),
        sa.Column("referencia", sa.String(150), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.func.now()),
    )

    op.create_table(
        "devolucion_venta",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("venta_id", sa.BigInteger(), sa.ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("detalle_venta_id", sa.BigInteger(), sa.ForeignKey("detalle_venta.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("cantidad", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("monto_devuelto", sa.Numeric(15, 2), nullable=False),
        sa.Column("moneda_id", sa.BigInteger(), sa.ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False, server_default="1"),
        sa.Column("tasa_cambio", sa.Numeric(15, 6), nullable=False, server_default="1.0"),
        sa.Column("monto_en_moneda_base", sa.Numeric(15, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------
    # 3. Seeds: concepto_reporte (líneas de inventario del Excel)
    # ------------------------------------------------------------
    op.bulk_insert(
        sa.table(
            "concepto_reporte",
            sa.column("id", sa.BigInteger()),
            sa.column("nombre", sa.String(150)),
            sa.column("seccion", sa.String(50)),
            sa.column("orden", sa.Integer()),
            sa.column("activo", sa.Boolean()),
        ),
        [
            {"id": 1, "nombre": "Inventario del Depósito MDF e Insumos", "seccion": "INVENTARIO", "orden": 1, "activo": True},
            {"id": 2, "nombre": "Inventario Melamina", "seccion": "INVENTARIO", "orden": 2, "activo": True},
            {"id": 3, "nombre": "Inventario en Espuma", "seccion": "INVENTARIO", "orden": 3, "activo": True},
            {"id": 4, "nombre": "Inventario de Producto Terminado en Depósito", "seccion": "INVENTARIO", "orden": 4, "activo": True},
            {"id": 5, "nombre": "Inventario en Proceso en Crudo", "seccion": "INVENTARIO", "orden": 5, "activo": True},
            {"id": 6, "nombre": "Inventario de Material de Pintura", "seccion": "INVENTARIO", "orden": 6, "activo": True},
            {"id": 7, "nombre": "Inventario Departamento de Colchones", "seccion": "INVENTARIO", "orden": 7, "activo": True},
            {"id": 8, "nombre": "Inventario Departamento de Electrodomésticos", "seccion": "INVENTARIO", "orden": 8, "activo": True},
        ],
    )

    # ------------------------------------------------------------
    # 4. Seeds: método_caja
    # ------------------------------------------------------------
    op.bulk_insert(
        sa.table(
            "metodo_caja",
            sa.column("id", sa.BigInteger()),
            sa.column("nombre", sa.String(100)),
            sa.column("codigo", sa.String(50)),
            sa.column("activo", sa.Boolean()),
            sa.column("orden", sa.Integer()),
        ),
        [
            {"id": 1, "nombre": "Efectivo en Pesos", "codigo": "EFECTIVO_COP", "activo": True, "orden": 1},
            {"id": 2, "nombre": "Efectivo en Dólares", "codigo": "EFECTIVO_USD", "activo": True, "orden": 2},
            {"id": 3, "nombre": "Efectivo en Bolívares", "codigo": "EFECTIVO_VES", "activo": True, "orden": 3},
            {"id": 4, "nombre": "Bancolombia", "codigo": "BANCOLOMBIA", "activo": True, "orden": 4},
            {"id": 5, "nombre": "Bancaribe", "codigo": "BANCARIBE", "activo": True, "orden": 5},
            {"id": 6, "nombre": "Zelle", "codigo": "ZELLE", "activo": True, "orden": 6},
        ],
    )

    # ------------------------------------------------------------
    # 5. Seeds: TipoGasto con categorías ampliadas (lista del Excel)
    # ------------------------------------------------------------
    op.execute("ALTER TABLE tipo_gasto DROP CONSTRAINT IF EXISTS tipo_gasto_categoria_check")

    tipos_gasto = [
        # OPERATIVO
        ("INTERNET DE FABRICA", "OPERATIVO"),
        ("CAMARA DE COMERCIO", "OPERATIVO"),
        ("MANTENIMIENTO DE AIRES", "OPERATIVO"),
        ("ALIMENTACION DE FABRICA (COMIDAS Y ALMUERZOS)", "OPERATIVO"),
        ("MANTENIMIENTO DE MAQUINARIAS", "OPERATIVO"),
        ("INTERNET DE CASA", "OPERATIVO"),
        ("MANTENIMIENTO DE EQUIPOS", "OPERATIVO"),
        ("ELECTRICIDAD CORPOELEC", "OPERATIVO"),
        ("HIDROSUROESTE", "OPERATIVO"),
        ("SERVICIO DE AGUA CARROTANQUE", "OPERATIVO"),
        ("SERVICIO DE ASEO URBANO", "OPERATIVO"),
        ("LUZ CAMARA DE COMERCIO", "OPERATIVO"),
        ("PROPAGANDA Y PUBLICIDAD", "OPERATIVO"),
        ("INSTAGRAM", "OPERATIVO"),
        ("PUBLICIDAD SR PITER", "OPERATIVO"),
        ("DONACIONES", "OPERATIVO"),
        ("AGUA DE BOTELLON", "OPERATIVO"),
        ("FUNERARIA", "OPERATIVO"),
        ("CAMIONES (CAMBIO DE ACEITE Y VARIOS)", "OPERATIVO"),
        ("FLETES", "OPERATIVO"),
        ("GASOLINA Y COMBUSTIBLE", "OPERATIVO"),
        ("HERRAMIENTAS Y REPUESTOS", "OPERATIVO"),
        # ADMINISTRATIVO
        ("GASTOS EN CASA", "ADMINISTRATIVO"),
        ("PAPELERIA DE OFICINA", "ADMINISTRATIVO"),
        ("SUELDOS DE NOMINAS ADMINISTRATIVAS", "ADMINISTRATIVO"),
        ("HONORARIOS PROFESIONALES", "ADMINISTRATIVO"),
        ("DOTACION DE EMPLEADOS", "ADMINISTRATIVO"),
        ("ALIMENTACION DE CASA", "ADMINISTRATIVO"),
        ("OTROS GASTOS ADMINISTRATIVOS Y FESTEJOS", "ADMINISTRATIVO"),
        # FINANCIERO
        ("INTERESES COBRADOS", "FINANCIERO"),
        ("UTILIDAD POR DIFERENCIAL CAMBIARIO", "FINANCIERO"),
        ("INTERESES PAGADOS BANCOLOMBIA", "FINANCIERO"),
        ("PAGOS PRESTAMO BANCOLOMBIA", "FINANCIERO"),
        ("COMISIONES BANCARIAS", "FINANCIERO"),
        ("PERDIDA POR DIFERENCIAL CAMBIARIO", "FINANCIERO"),
        # IMPUESTO
        ("CONTADORA", "IMPUESTO"),
        ("LICENCIADA INVENTARIO", "IMPUESTO"),
        ("PARAFISCALES (BANAVI Y IVSS)", "IMPUESTO"),
        ("RETENCION DE IVA", "IMPUESTO"),
        ("IGTF", "IMPUESTO"),
        ("IVA", "IMPUESTO"),
        ("ASEO ALCALDIA", "IMPUESTO"),
        ("ISLR", "IMPUESTO"),
        ("IMPUESTO ALCALDIA 2.5%", "IMPUESTO"),
        ("IMPUESTO ALCALDIA 1%", "IMPUESTO"),
    ]
    for nombre, categoria in tipos_gasto:
        op.execute(
            sa.text(
                "INSERT INTO tipo_gasto (nombre, categoria) VALUES (:nombre, :categoria) "
                "ON CONFLICT (nombre) DO NOTHING"
            ).bindparams(nombre=nombre, categoria=categoria)
        )

    # Actualizar categoría de los tipos existentes que no la tengan clara
    op.execute(sa.text("UPDATE tipo_gasto SET categoria = 'OPERATIVO' WHERE categoria NOT IN ('OPERATIVO','ADMINISTRATIVO','FINANCIERO','IMPUESTO','PRODUCCION','PASIVO')"))


def downgrade() -> None:
    op.drop_table("devolucion_venta")
    op.drop_table("movimiento_caja")
    op.drop_table("metodo_caja")
    op.drop_table("valor_concepto_mensual")
    op.drop_table("concepto_reporte")
    op.drop_column("compra", "total_en_moneda_base")
    op.drop_column("compra", "tasa_cambio")
    op.drop_column("compra", "tipo_pago")
    op.drop_column("detalle_pedido", "porcentaje_ganancia")
    op.drop_column("detalle_pedido", "costo_unitario")
    op.drop_column("detalle_venta", "descuento")
    op.drop_column("detalle_venta", "utilidad")
    op.drop_column("detalle_venta", "porcentaje_ganancia")
    op.drop_column("detalle_venta", "costo_unitario")
    op.drop_column("venta", "total_en_moneda_base")
    op.drop_column("venta", "tasa_cambio")
