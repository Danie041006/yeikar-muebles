"""proveedor y cliente opcional en movimientos de inventario

Revision ID: f0e1d2c3b4a5
Revises: k7l8m9n0o1p2
Create Date: 2026-09-01

Al registrar una entrada de inventario ahora se puede indicar (opcional) el
proveedor = lugar donde se compró el insumo/producto, y el cliente = si el
material se compró para un cliente específico. Ambos quedan en el movimiento
para el kardex, sin obligar a ningún flujo de compras formal.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f0e1d2c3b4a5'
down_revision: Union[str, None] = 'k7l8m9n0o1p2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'movimiento_inventario',
        sa.Column('proveedor_id', sa.BigInteger(), sa.ForeignKey('proveedor.id', ondelete='RESTRICT'), nullable=True),
    )
    op.add_column(
        'movimiento_inventario',
        sa.Column('cliente_id', sa.Integer(), sa.ForeignKey('cliente.id', ondelete='RESTRICT'), nullable=True),
    )
    op.add_column(
        'movimiento_producto_inventario',
        sa.Column('proveedor_id', sa.BigInteger(), sa.ForeignKey('proveedor.id', ondelete='RESTRICT'), nullable=True),
    )
    op.add_column(
        'movimiento_producto_inventario',
        sa.Column('cliente_id', sa.Integer(), sa.ForeignKey('cliente.id', ondelete='RESTRICT'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('movimiento_producto_inventario', 'cliente_id')
    op.drop_column('movimiento_producto_inventario', 'proveedor_id')
    op.drop_column('movimiento_inventario', 'cliente_id')
    op.drop_column('movimiento_inventario', 'proveedor_id')
