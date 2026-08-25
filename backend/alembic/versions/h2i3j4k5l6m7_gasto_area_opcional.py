"""gasto: área/departamento opcional del egreso

Revision ID: h2i3j4k5l6m7
Revises: g1a2b3c4d5e6
Create Date: 2026-08-15

Agrega `area_id` (opcional) a `gasto` para etiquetar de qué departamento/
área es el egreso (p. ej. reparación de una máquina compartida entre dos
áreas: se indica cuál fue).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, None] = "g1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gasto",
        sa.Column("area_id", sa.BigInteger(), sa.ForeignKey("area.id", ondelete="SET NULL"), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("gasto", "area_id")
