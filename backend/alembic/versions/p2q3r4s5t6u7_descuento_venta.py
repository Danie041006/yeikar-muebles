"""descuento_venta: rebaja otorgada al cobrar (resta del saldo sin mover caja)

Revision ID: p2q3r4s5t6u7
Revises: e8f9a0b1c2d3
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p2q3r4s5t6u7'
down_revision = 'e8f9a0b1c2d3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'descuento_venta',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('venta_id', sa.BigInteger(), sa.ForeignKey('venta.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('moneda_id', sa.BigInteger(), sa.ForeignKey('moneda.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.Column('monto', sa.Numeric(15, 2), nullable=False),
        sa.Column('tasa_cambio', sa.Numeric(15, 6), nullable=False, server_default='1.0'),
        sa.Column('monto_en_moneda_base', sa.Numeric(15, 2), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('creado_por_id', sa.BigInteger(), sa.ForeignKey('usuario.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_descuento_venta_id', 'descuento_venta', ['id'])
    op.create_index('ix_descuento_venta_creado_por_id', 'descuento_venta', ['creado_por_id'])


def downgrade():
    op.drop_index('ix_descuento_venta_creado_por_id', table_name='descuento_venta')
    op.drop_index('ix_descuento_venta_id', table_name='descuento_venta')
    op.drop_table('descuento_venta')
