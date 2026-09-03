"""costo_estimado en costo_produccion (comparativa estimado vs real)

Revision ID: f9a0b1c2d3e4
Revises: f8a9b0c1d2e3
Create Date: 2026-09-01 10:00:00.000000

Agrega costo_estimado a costo_produccion: el estimado del costo de la orden
(precio_costo_base del producto × unidades del detalle) para compararlo con
el costo real al finalizar la producción.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9a0b1c2d3e4'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'costo_produccion',
        sa.Column('costo_estimado', sa.Numeric(precision=15, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('costo_produccion', 'costo_estimado')