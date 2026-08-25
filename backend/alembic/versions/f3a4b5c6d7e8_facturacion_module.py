"""facturacion: tabla factura, detalle_factura, tasa_impuesto y módulo de permisos.

Revision ID: f3a4b5c6d7e8
Revises: b0b00c037df5
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, None] = 'b0b00c037df5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'factura',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('pedido_id', sa.BigInteger(), sa.ForeignKey('pedido.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('cliente_id', sa.BigInteger(), sa.ForeignKey('cliente.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha_emision', sa.Date(), nullable=False),
        sa.Column('total_usd', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('tasa_usd_ves', sa.Numeric(15, 6), nullable=False, server_default='1'),
        sa.Column('base_imponible_bs', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('iva_bs', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('igtf_bs', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('total_bs', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('estado', sa.String(50), nullable=False, server_default='EMITIDA'),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('creado_por_id', sa.BigInteger(), sa.ForeignKey('usuario.id', ondelete='SET NULL'), nullable=True),
        sa.Column('actualizado_por_id', sa.BigInteger(), sa.ForeignKey('usuario.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.UniqueConstraint('pedido_id', name='uq_factura_pedido_id'),
    )
    op.create_index('ix_factura_id', 'factura', ['id'], unique=False)
    op.create_index('ix_factura_creado_por_id', 'factura', ['creado_por_id'], unique=False)
    op.create_index('ix_factura_actualizado_por_id', 'factura', ['actualizado_por_id'], unique=False)

    op.create_table(
        'detalle_factura',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('factura_id', sa.BigInteger(), sa.ForeignKey('factura.id', ondelete='CASCADE'), nullable=False),
        sa.Column('producto_id', sa.BigInteger(), sa.ForeignKey('producto.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('descripcion', sa.String(250), nullable=True),
        sa.Column('cantidad', sa.Numeric(10, 2), nullable=False),
        sa.Column('precio_usd', sa.Numeric(15, 2), nullable=False),
        sa.Column('subtotal_usd', sa.Numeric(15, 2), nullable=False),
        sa.Column('subtotal_bs', sa.Numeric(15, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    )
    op.create_index('ix_detalle_factura_id', 'detalle_factura', ['id'], unique=False)
    op.create_index('ix_detalle_factura_factura_id', 'detalle_factura', ['factura_id'], unique=False)

    op.create_table(
        'tasa_impuesto',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('clave', sa.String(20), nullable=False, unique=True),
        sa.Column('nombre', sa.String(100), nullable=False),
        sa.Column('tasa', sa.Numeric(6, 4), nullable=False),
        sa.Column('vigente', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    )
    op.create_index('ix_tasa_impuesto_id', 'tasa_impuesto', ['id'], unique=False)

    conn = op.get_bind()
    # Seed de tasas fiscales por defecto (16% IVA, 3% IGTF).
    conn.execute(
        text("INSERT INTO tasa_impuesto (clave, nombre, tasa, vigente) "
             "VALUES ('IVA', 'Impuesto al Valor Agregado', 16.0, TRUE) "
             "ON CONFLICT (clave) DO NOTHING")
    )
    conn.execute(
        text("INSERT INTO tasa_impuesto (clave, nombre, tasa, vigente) "
             "VALUES ('IGTF', 'Impuesto a las Grandes Transacciones Financieras', 3.0, TRUE) "
             "ON CONFLICT (clave) DO NOTHING")
    )
    # El módulo 'facturacion' lo heredan los roles que ya gestionan 'ventas'.
    conn.execute(
        text("INSERT INTO rol_modulo (rol_id, modulo, gestionar) "
             "SELECT DISTINCT rm.rol_id, 'facturacion', rm.gestionar "
             "FROM rol_modulo rm WHERE rm.modulo = 'ventas' "
             "ON CONFLICT (rol_id, modulo) DO NOTHING")
    )


def downgrade() -> None:
    op.drop_index('ix_tasa_impuesto_id', table_name='tasa_impuesto')
    op.drop_table('tasa_impuesto')
    op.drop_index('ix_detalle_factura_factura_id', table_name='detalle_factura')
    op.drop_index('ix_detalle_factura_id', table_name='detalle_factura')
    op.drop_table('detalle_factura')
    op.drop_index('ix_factura_creado_por_id', table_name='factura')
    op.drop_index('ix_factura_actualizado_por_id', table_name='factura')
    op.drop_index('ix_factura_id', table_name='factura')
    op.drop_constraint('uq_factura_pedido_id', 'factura', type_='unique')
    op.drop_table('factura')
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM rol_modulo WHERE modulo = 'facturacion'")
    )
