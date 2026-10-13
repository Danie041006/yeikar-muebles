"""unidades de uso de materiales (cuñete/galón/pistolada/litro)

Contexto: los insumos líquidos/densos (colbón, laca, tiner…) se compran en una
unidad BASE (cuñete, galón, litro) pero el taller los consume en otras medidas
(pistolada, galón, litro). Se crea `material_unidad_uso` con el factor PRÁCTICO
de cada material (1 unidad de uso = factor_base unidades base) y se agregan
`unidad_uso_id`/`cantidad_uso` a los consumos para conservar cómo se digitó.
El stock y los costos siguen SIEMPRE en la unidad base.

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'y2z3a4b5c6d7'
down_revision: Union[str, None] = 'x1y2z3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_unidad_uso",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.String(length=50), nullable=False),
        sa.Column("factor_base", sa.Numeric(18, 10), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["material_id"], ["material.id"],
            name="material_unidad_uso_material_id_fkey", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", "nombre", name="uq_material_unidad_uso_nombre"),
    )
    op.create_index("ix_material_unidad_uso_material_id", "material_unidad_uso", ["material_id"])

    op.add_column(
        "consumo_material",
        sa.Column("unidad_uso_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "consumo_material",
        sa.Column("cantidad_uso", sa.Numeric(12, 4), nullable=True),
    )
    op.create_foreign_key(
        "consumo_material_unidad_uso_id_fkey", "consumo_material",
        "material_unidad_uso", ["unidad_uso_id"], ["id"], ondelete="SET NULL",
    )

    op.add_column(
        "produccion_crudo_consumo",
        sa.Column("unidad_uso_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "produccion_crudo_consumo",
        sa.Column("cantidad_uso", sa.Numeric(12, 4), nullable=True),
    )
    op.create_foreign_key(
        "produccion_crudo_consumo_unidad_uso_id_fkey", "produccion_crudo_consumo",
        "material_unidad_uso", ["unidad_uso_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "produccion_crudo_consumo_unidad_uso_id_fkey",
        "produccion_crudo_consumo", type_="foreignkey",
    )
    op.drop_column("produccion_crudo_consumo", "cantidad_uso")
    op.drop_column("produccion_crudo_consumo", "unidad_uso_id")

    op.drop_constraint(
        "consumo_material_unidad_uso_id_fkey",
        "consumo_material", type_="foreignkey",
    )
    op.drop_column("consumo_material", "cantidad_uso")
    op.drop_column("consumo_material", "unidad_uso_id")

    op.drop_index("ix_material_unidad_uso_material_id", table_name="material_unidad_uso")
    op.drop_table("material_unidad_uso")
