"""venta de insumos - tipo_item y material_id en detalles

Revision ID: b5ac1f578227
Revises: f275fd88fb94
Create Date: 2026-08-28 11:47:06.072248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b5ac1f578227'
down_revision: Union[str, None] = 'f275fd88fb94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── detalle_cotizacion ──
    op.add_column('detalle_cotizacion', sa.Column('material_id', sa.BigInteger(), nullable=True))
    op.add_column('detalle_cotizacion', sa.Column('tipo_item', sa.String(length=20), server_default='FABRICADO', nullable=False))
    op.alter_column('detalle_cotizacion', 'producto_id', existing_type=sa.BIGINT(), nullable=True)
    op.create_foreign_key(None, 'detalle_cotizacion', 'material', ['material_id'], ['id'], ondelete='RESTRICT')

    # ── detalle_pedido ──
    op.add_column('detalle_pedido', sa.Column('material_id', sa.BigInteger(), nullable=True))
    op.add_column('detalle_pedido', sa.Column('tipo_item', sa.String(length=20), server_default='FABRICADO', nullable=False))
    op.alter_column('detalle_pedido', 'producto_id', existing_type=sa.BIGINT(), nullable=True)
    op.create_foreign_key(None, 'detalle_pedido', 'material', ['material_id'], ['id'], ondelete='RESTRICT')

    # ── detalle_venta ──
    op.add_column('detalle_venta', sa.Column('material_id', sa.BigInteger(), nullable=True))
    op.add_column('detalle_venta', sa.Column('tipo_item', sa.String(length=20), server_default='FABRICADO', nullable=False))
    op.alter_column('detalle_venta', 'producto_id', existing_type=sa.BIGINT(), nullable=True)
    op.create_foreign_key(None, 'detalle_venta', 'material', ['material_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    op.drop_constraint(None, 'detalle_venta', type_='foreignkey')
    op.alter_column('detalle_venta', 'producto_id', existing_type=sa.BIGINT(), nullable=False)
    op.drop_column('detalle_venta', 'tipo_item')
    op.drop_column('detalle_venta', 'material_id')

    op.drop_constraint(None, 'detalle_pedido', type_='foreignkey')
    op.alter_column('detalle_pedido', 'producto_id', existing_type=sa.BIGINT(), nullable=False)
    op.drop_column('detalle_pedido', 'tipo_item')
    op.drop_column('detalle_pedido', 'material_id')

    op.drop_constraint(None, 'detalle_cotizacion', type_='foreignkey')
    op.alter_column('detalle_cotizacion', 'producto_id', existing_type=sa.BIGINT(), nullable=False)
    op.drop_column('detalle_cotizacion', 'tipo_item')
    op.drop_column('detalle_cotizacion', 'material_id')
