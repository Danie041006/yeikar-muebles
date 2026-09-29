"""merge heads (webauthn, detalle CxP, crudo)

Revision ID: d68c00cfa34e
Revises: e6f42bb70a1d, o1p2q3r4s5t6, c1d2e3f4a5b6
Create Date: 2026-09-29 16:23:35.712914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd68c00cfa34e'
down_revision: Union[str, None] = ('e6f42bb70a1d', 'o1p2q3r4s5t6', 'c1d2e3f4a5b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
