"""nomina detalle sueldo_snapshot

Revision ID: f1a2b3c4d5e6
Revises: e5eba926361b
Create Date: 2026-08-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e5eba926361b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('nomina_detalle', sa.Column('sueldo_snapshot', sa.Numeric(15, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('nomina_detalle', 'sueldo_snapshot')