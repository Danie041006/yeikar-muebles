"""fase1_base_financiera

Revision ID: 614939ee4000
Revises: 8d0e6ee658f6
Create Date: 2026-07-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '614939ee4000'
down_revision: Union[str, None] = '8d0e6ee658f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Agregar costo_unitario a consumo_material
    op.add_column('consumo_material', sa.Column('costo_unitario', sa.Numeric(precision=15, scale=2), nullable=True))
    
    # 2. Agregar pagado a mano_obra
    op.add_column('mano_obra', sa.Column('pagado', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('mano_obra', 'pagado')
    op.drop_column('consumo_material', 'costo_unitario')
