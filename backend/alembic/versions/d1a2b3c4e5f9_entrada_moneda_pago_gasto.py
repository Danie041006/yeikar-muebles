"""entrada de inventario: moneda/tasa de pago y gasto vinculado

Guarda en el propio movimiento de inventario la moneda y la tasa con las que
se pagó la compra (hoy viven solo en el gasto generado) y el id de ese gasto,
para poder bloquear su borrado y detectar entradas que quedaron sin pago.

- `moneda_pago_id`: moneda de la cuenta desde la que se pagó (NULL = no aplica).
- `tasa_pago`: 1 [moneda_pago] = X COP (convención del proyecto).
- `gasto_id`: gasto "COMPRA DE INSUMOS" generado automáticamente por la entrada.

Revision ID: d1a2b3c4e5f9
Revises: of1c2i3n4a5b6
Create Date: 2026-10-24
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1a2b3c4e5f9"
down_revision: Union[str, None] = "of1c2i3n4a5b6"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "movimiento_inventario",
        sa.Column("moneda_pago_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "movimiento_inventario",
        sa.Column("tasa_pago", sa.Numeric(15, 6), nullable=True),
    )
    op.add_column(
        "movimiento_inventario",
        sa.Column("gasto_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_movimiento_inventario_moneda_pago",
        "movimiento_inventario",
        "moneda",
        ["moneda_pago_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_movimiento_inventario_gasto",
        "movimiento_inventario",
        "gasto",
        ["gasto_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_movimiento_inventario_gasto_id",
        "movimiento_inventario",
        ["gasto_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_movimiento_inventario_gasto_id",
        table_name="movimiento_inventario",
    )
    op.drop_constraint(
        "fk_movimiento_inventario_gasto",
        "movimiento_inventario",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_movimiento_inventario_moneda_pago",
        "movimiento_inventario",
        type_="foreignkey",
    )
    op.drop_column("movimiento_inventario", "gasto_id")
    op.drop_column("movimiento_inventario", "tasa_pago")
    op.drop_column("movimiento_inventario", "moneda_pago_id")
