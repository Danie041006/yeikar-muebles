"""detalle_cuenta_por_pagar: renglones de cada deuda (qué se compró y para quién)

Revision ID: o1p2q3r4s5t6
Revises: m1n2o3p4q5r6
Create Date: 2026-09-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'o1p2q3r4s5t6'
down_revision = 'm1n2o3p4q5r6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'detalle_cuenta_por_pagar',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('cuenta_por_pagar_id', sa.BigInteger(), sa.ForeignKey('cuenta_por_pagar.id', ondelete='CASCADE'), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('descripcion', sa.String(250), nullable=True),
        sa.Column('material_id', sa.BigInteger(), sa.ForeignKey('material.id', ondelete='SET NULL'), nullable=True),
        sa.Column('cantidad', sa.Numeric(12, 2), nullable=False, server_default='1'),
        sa.Column('precio_unitario', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('cliente_nombre', sa.String(150), nullable=True),
        sa.Column('cliente_id', sa.BigInteger(), sa.ForeignKey('cliente.id', ondelete='SET NULL'), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
    )
    op.create_index('ix_detalle_cuenta_por_pagar_cuenta_por_pagar_id', 'detalle_cuenta_por_pagar', ['cuenta_por_pagar_id'])
    op.create_index('ix_detalle_cuenta_por_pagar_material_id', 'detalle_cuenta_por_pagar', ['material_id'])


def downgrade():
    op.drop_index('ix_detalle_cuenta_por_pagar_material_id', table_name='detalle_cuenta_por_pagar')
    op.drop_index('ix_detalle_cuenta_por_pagar_cuenta_por_pagar_id', table_name='detalle_cuenta_por_pagar')
    op.drop_table('detalle_cuenta_por_pagar')