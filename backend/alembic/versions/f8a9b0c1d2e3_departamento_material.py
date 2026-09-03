"""departamento en material: inventario por departamentos del taller

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-08-31

Agrega `material.departamento` para organizar el inventario de insumos por
departamentos productivos (EBANISTERIA, PREPARACION, PINTURA, TAPICERIA,
VIDRIERIA, TERMINACION). Tendido no es departamento propio: sus insumos se
marcan EBANISTERIA. NULL = insumo transversal/general (a clasificar).

Seed inicial por categoría de inventario:
  - LÁMINAS MDF, MELAMINA → EBANISTERIA
  - ESPUMA → TAPICERIA
  - PINTURA → PINTURA
  - OTROS INSUMOS y sin categoría → NULL (transversal)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "ed2edcb2360c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEPARTAMENTOS = (
    "EBANISTERIA",
    "PREPARACION",
    "PINTURA",
    "TAPICERIA",
    "VIDRIERIA",
    "TERMINACION",
)


def upgrade() -> None:
    op.add_column(
        "material",
        sa.Column("departamento", sa.String(30), nullable=True),
    )
    op.create_check_constraint(
        "material_departamento_check",
        "material",
        "departamento IS NULL OR departamento IN "
        f"({', '.join(f"'{d}'" for d in DEPARTAMENTOS)})",
    )

    conn = op.get_bind()
    seeds = {
        "LÁMINAS MDF": "EBANISTERIA",
        "MELAMINA": "EBANISTERIA",
        "ESPUMA": "TAPICERIA",
        "PINTURA": "PINTURA",
    }
    for categoria, departamento in seeds.items():
        conn.execute(
            text(
                "UPDATE material SET departamento = :depto "
                "WHERE departamento IS NULL AND categoria_inventario_id IN "
                "(SELECT id FROM categoria_inventario WHERE nombre = :cat)"
            ),
            {"depto": departamento, "cat": categoria},
        )


def downgrade() -> None:
    op.drop_constraint("material_departamento_check", "material", type_="check")
    op.drop_column("material", "departamento")