"""merge heads: moneda metodo_caja

Revision ID: cb2ae187397c
Revises: 0761b7ce4ad9, e6f7a8b9c0d1
Create Date: 2026-08-26 19:15:09.479178

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb2ae187397c'
down_revision: Union[str, None] = ('0761b7ce4ad9', 'e6f7a8b9c0d1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
