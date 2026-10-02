"""merge reparacion/servicio/flete con cuentas por persona

Revision ID: a14719da2be6
Revises: c3d4e5f6a7b8, d5e6f7a8b9c0
Create Date: 2026-10-02 11:07:11.056118

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a14719da2be6'
down_revision: Union[str, None] = ('c3d4e5f6a7b8', 'd5e6f7a8b9c0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
