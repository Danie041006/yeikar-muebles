"""merge_ramas_produccion

Revision ID: ed2edcb2360c
Revises: j5k6l7m8n9o0, e7f8a9b0c1d2
Create Date: 2026-08-31 17:24:54.042779

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed2edcb2360c'
down_revision: Union[str, None] = ('j5k6l7m8n9o0', 'e7f8a9b0c1d2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
