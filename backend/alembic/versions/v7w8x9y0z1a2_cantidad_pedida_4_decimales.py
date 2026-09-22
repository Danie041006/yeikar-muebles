"""cantidad_pedida de consumo_material con 4 decimales (pedido abierto)

Revision ID: v7w8x9y0z1a2
Revises: u6v7w8x9y0z1

`cantidad_pedida` guarda lo que el taller pidió antes de confirmar el uso.
Con la captura flexible (pieza L×A×E ÷ 10000, cm ÷ 10000) la cantidad pedida
puede ser tan pequeña como 0.016 m³; con NUMERIC(12,2) se redondeaba y no
cuadraba con lo usado. Se amplía a 4 decimales para alinearla con `cantidad`
(migración b6c7d8e9f0a1).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "v7w8x9y0z1a2"
down_revision: Union[str, None] = "u6v7w8x9y0z1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("consumo_material", "cantidad_pedida", type_=sa.Numeric(12, 4))


def downgrade() -> None:
    op.alter_column(
        "consumo_material",
        "cantidad_pedida",
        type_=sa.Numeric(12, 2),
        postgresql_using="cantidad_pedida::numeric(12,2)",
    )
