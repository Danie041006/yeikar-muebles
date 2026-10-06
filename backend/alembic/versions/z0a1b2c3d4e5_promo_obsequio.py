"""promo obsequio: por colchón se regala un plástico (línea a precio 0)

Tabla promocion_obsequio (colchon -> obsequio plástico) + flag es_obsequio
en detalle_cotizacion, detalle_pedido y detalle_venta.

Revision ID: z0a1b2c3d4e5
Revises: a14719da2be6
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'z0a1b2c3d4e5'
down_revision: Union[str, None] = 'a14719da2be6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'promocion_obsequio',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True, index=True),
        sa.Column('colchon_id', sa.BigInteger(), sa.ForeignKey('producto.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('obsequio_id', sa.BigInteger(), sa.ForeignKey('producto.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default='true', index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    for tabla in ('detalle_cotizacion', 'detalle_pedido', 'detalle_venta'):
        op.add_column(tabla, sa.Column('es_obsequio', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    for tabla in ('detalle_venta', 'detalle_pedido', 'detalle_cotizacion'):
        op.drop_column(tabla, 'es_obsequio')
    op.drop_table('promocion_obsequio')
