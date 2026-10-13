"""zona y quién trajo en entradas de insumos

Agrega a `movimiento_inventario`:
  - `departamento`: zona del taller a la que va la compra
    (EBANISTERIA, PREPARACION, PINTURA, TAPICERIA, VIDRIERIA, TERMINACION).
    NULL = general/sin zona. Solo informativo: no cambia el departamento
    del material.
  - `recibido_por`: quién trajo/entregó la compra (texto libre).

Revision ID: x1y2z3a4b5c6
Revises: pz1e2z3a4b5c
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'x1y2z3a4b5c6'
down_revision: Union[str, None] = 'pz1e2z3a4b5c'
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
        "movimiento_inventario",
        sa.Column("departamento", sa.String(30), nullable=True),
    )
    op.add_column(
        "movimiento_inventario",
        sa.Column("recibido_por", sa.String(150), nullable=True),
    )
    deptos_sql = ", ".join(f"'{d}'" for d in DEPARTAMENTOS)
    op.create_check_constraint(
        "movimiento_inventario_departamento_check",
        "movimiento_inventario",
        f"departamento IS NULL OR departamento IN ({deptos_sql})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "movimiento_inventario_departamento_check",
        "movimiento_inventario",
        type_="check",
    )
    op.drop_column("movimiento_inventario", "recibido_por")
    op.drop_column("movimiento_inventario", "departamento")
