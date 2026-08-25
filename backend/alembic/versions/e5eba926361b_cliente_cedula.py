"""cliente cedula

Revision ID: e5eba926361b
Revises: e9f8a7b6c5d4
Create Date: 2026-08-24 00:46:03.411803

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5eba926361b'
down_revision: Union[str, None] = 'e9f8a7b6c5d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cliente', sa.Column('cedula', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('cliente', 'cedula')