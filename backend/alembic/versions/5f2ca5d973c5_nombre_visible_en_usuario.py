"""nombre_visible_en_usuario

Revision ID: 5f2ca5d973c5
Revises: n2o3p4q5r6s7
Create Date: 2026-09-03 08:47:28.464828

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f2ca5d973c5'
down_revision: Union[str, None] = 'n2o3p4q5r6s7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('usuario', sa.Column('nombre', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('usuario', 'nombre')
