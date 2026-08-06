"""agrega costo_unitario al kardex de materiales.

Revision ID: f2a1b3c4d5e6
Revises: e88131b54e51
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a1b3c4d5e6'
down_revision: Union[str, None] = 'e88131b54e51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Precio unitario del material en el movimiento (registrado al hacer ENTRADA)
    op.add_column(
        'movimiento_inventario',
        sa.Column('costo_unitario', sa.Numeric(15, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('movimiento_inventario', 'costo_unitario')
