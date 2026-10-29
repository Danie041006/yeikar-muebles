"""foto opcional de las piezas del juego (cotización y pedido)

Revision ID: p1e2z3a4s5f6
Revises: h0r4a1b2c3d4
Create Date: 2026-10-29

La foto se guarda como data URL ya comprimida en el navegador. Es opcional:
las piezas que no tienen foto quedan en NULL y todo el flujo sigue igual.
"""
from alembic import op
import sqlalchemy as sa


revision = "p1e2z3a4s5f6"
down_revision = "h0r4a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "detalle_cotizacion_pieza",
        sa.Column("foto", sa.Text(), nullable=True),
    )
    op.add_column(
        "detalle_pedido_pieza",
        sa.Column("foto", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("detalle_pedido_pieza", "foto")
    op.drop_column("detalle_cotizacion_pieza", "foto")
