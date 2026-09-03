"""add_listo_nomina_to_mano_obra

Revision ID: 62bff25b4e7c
Revises: cb2ae187397c
Create Date: 2026-08-27 11:23:12.511373

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62bff25b4e7c'
down_revision: Union[str, None] = 'cb2ae187397c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('mano_obra', sa.Column('listo_nomina', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('mano_obra', 'listo_nomina')
