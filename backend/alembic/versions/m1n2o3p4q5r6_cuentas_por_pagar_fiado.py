"""cuentas por pagar (fiado): deudas con proveedores + abonos

Revision ID: m1n2o3p4q5r6
Revises: f0e1d2c3b4a5
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'm1n2o3p4q5r6'
down_revision = 'f0e1d2c3b4a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cuenta_por_pagar',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('proveedor_id', sa.BigInteger(), sa.ForeignKey('proveedor.id'), nullable=False),
        sa.Column('gasto_id', sa.BigInteger(), sa.ForeignKey('gasto.id', ondelete='SET NULL'), nullable=True),
        sa.Column('tipo_gasto_id', sa.BigInteger(), sa.ForeignKey('tipo_gasto.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('moneda_id', sa.BigInteger(), sa.ForeignKey('moneda.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('monto', sa.Numeric(15, 2), nullable=False),
        sa.Column('tasa_cambio', sa.Numeric(15, 6), nullable=False, server_default='1.0'),
        sa.Column('monto_en_moneda_base', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('monto_pagado', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('estado', sa.String(20), nullable=False, server_default='PENDIENTE'),
        sa.Column('origen_tipo', sa.String(30), nullable=True),
        sa.Column('origen_id', sa.BigInteger(), nullable=True),
        sa.Column('creado_por_id', sa.BigInteger(), sa.ForeignKey('usuario.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
    )
    op.create_index('ix_cuenta_por_pagar_estado', 'cuenta_por_pagar', ['estado'])
    op.create_index('ix_cuenta_por_pagar_gasto_id', 'cuenta_por_pagar', ['gasto_id'])
    op.create_index('ix_cuenta_por_pagar_creado_por_id', 'cuenta_por_pagar', ['creado_por_id'])

    op.create_table(
        'pago_cuenta_por_pagar',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('cuenta_por_pagar_id', sa.BigInteger(), sa.ForeignKey('cuenta_por_pagar.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('metodo_caja_id', sa.BigInteger(), sa.ForeignKey('metodo_caja.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('monto', sa.Numeric(15, 2), nullable=False),
        sa.Column('tasa_cambio', sa.Numeric(15, 6), nullable=False, server_default='1.0'),
        sa.Column('monto_en_moneda_base', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('creado_por_id', sa.BigInteger(), sa.ForeignKey('usuario.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_pago_cuenta_por_pagar_cuenta_por_pagar_id', 'pago_cuenta_por_pagar', ['cuenta_por_pagar_id'])
    op.create_index('ix_pago_cuenta_por_pagar_creado_por_id', 'pago_cuenta_por_pagar', ['creado_por_id'])


def downgrade():
    op.drop_index('ix_pago_cuenta_por_pagar_creado_por_id', table_name='pago_cuenta_por_pagar')
    op.drop_index('ix_pago_cuenta_por_pagar_cuenta_por_pagar_id', table_name='pago_cuenta_por_pagar')
    op.drop_table('pago_cuenta_por_pagar')
    op.drop_index('ix_cuenta_por_pagar_creado_por_id', table_name='cuenta_por_pagar')
    op.drop_index('ix_cuenta_por_pagar_gasto_id', table_name='cuenta_por_pagar')
    op.drop_index('ix_cuenta_por_pagar_estado', table_name='cuenta_por_pagar')
    op.drop_table('cuenta_por_pagar')