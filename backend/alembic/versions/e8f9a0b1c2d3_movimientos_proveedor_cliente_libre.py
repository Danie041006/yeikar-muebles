"""proveedor_nombre / cliente_nombre libres en los movimientos de inventario

Revision ID: e8f9a0b1c2d3
Revises: f7b8c9d0e1a2
Create Date: 2026-09-03

Permite escribir el proveedor/cliente de un movimiento como texto libre sin
exigir un registro del catálogo (el FK sigue siendo opcional y solo se linkea
cuando el nombre coincide con un proveedor/cliente existente).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = '5f2ca5d973c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for tabla in ('movimiento_inventario', 'movimiento_producto_inventario'):
        op.add_column(tabla, sa.Column('proveedor_nombre', sa.String(length=150), nullable=True))
        op.add_column(tabla, sa.Column('cliente_nombre', sa.String(length=150), nullable=True))


def downgrade() -> None:
    for tabla in ('movimiento_inventario', 'movimiento_producto_inventario'):
        op.drop_column(tabla, 'cliente_nombre')
        op.drop_column(tabla, 'proveedor_nombre')