"""Distinguir pagos totales de entradas cuyo flete se cobró aparte.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
"""
from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for tabla in ("movimiento_inventario", "movimiento_producto_inventario"):
        op.add_column(tabla, sa.Column(
            "pagos_incluyen_llevada", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ))


def downgrade() -> None:
    for tabla in ("movimiento_producto_inventario", "movimiento_inventario"):
        op.drop_column(tabla, "pagos_incluyen_llevada")
