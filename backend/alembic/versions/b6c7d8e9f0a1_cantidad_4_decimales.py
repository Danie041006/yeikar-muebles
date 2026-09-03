"""cantidad de consumos/inventario con 4 decimales (madera por pieza)

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-09-01

La fórmula de la casa (L×A×E) × piezas ÷ 10000 da volúmenes pequeños
(20×4×2×1 = 0.016 m³). Con NUMERIC(12,2) se redondeaba a 0.02 y se perdía
~25% del stock. Se amplía a 4 decimales en las tablas que cargan la
cantidad consumida/descontada:

  - inventario.cantidad (stock actual)
  - movimiento_inventario.cantidad (kardex)
  - consumo_material.cantidad (consumos de producción)
  - produccion_crudo_consumo.cantidad (consumos de crudo)

Los CHECKs existentes (cantidad >= 0 / > 0) se conservan.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLAS = (
    "inventario",
    "movimiento_inventario",
    "consumo_material",
    "produccion_crudo_consumo",
)


def upgrade() -> None:
    for tabla in TABLAS:
        op.alter_column(tabla, "cantidad", type_=sa.Numeric(12, 4))


def downgrade() -> None:
    for tabla in TABLAS:
        op.alter_column(
            tabla,
            "cantidad",
            type_=sa.Numeric(12, 2),
            postgresql_using="cantidad::numeric(12,2)",
        )