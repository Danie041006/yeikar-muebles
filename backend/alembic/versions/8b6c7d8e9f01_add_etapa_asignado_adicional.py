"""add etapa production additional assignees

Revision ID: 8b6c7d8e9f01
Revises: f346bfe982db
Create Date: 2026-07-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b6c7d8e9f01"
down_revision: Union[str, None] = "f346bfe982db"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "etapa_asignado_adicional",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("etapa_produccion_id", sa.BigInteger(), nullable=False),
        sa.Column("empleado_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["empleado_id"], ["empleado.id"]),
        sa.ForeignKeyConstraint(
            ["etapa_produccion_id"],
            ["etapa_produccion.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "etapa_produccion_id",
            "empleado_id",
            name="uq_etapa_asignado_adicional",
        ),
    )
    op.create_index(
        op.f("ix_etapa_asignado_adicional_id"),
        "etapa_asignado_adicional",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_etapa_asignado_adicional_etapa_produccion_id"),
        "etapa_asignado_adicional",
        ["etapa_produccion_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_etapa_asignado_adicional_etapa_produccion_id"),
        table_name="etapa_asignado_adicional",
    )
    op.drop_index(
        op.f("ix_etapa_asignado_adicional_id"),
        table_name="etapa_asignado_adicional",
    )
    op.drop_table("etapa_asignado_adicional")
