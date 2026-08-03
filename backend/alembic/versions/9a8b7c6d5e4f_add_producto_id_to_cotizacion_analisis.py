"""add producto_id to cotizacion_analisis_ia for idempotencia branch producto

Revision ID: 9a8b7c6d5e4f
Revises: 7a1b2c3d4e5f
Create Date: 2026-08-03

"""
from alembic import op
import sqlalchemy as sa


revision = "9a8b7c6d5e4f"
down_revision = "aabbcc001234"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cotizacion_analisis_ia",
        sa.Column(
            "producto_id",
            sa.BigInteger(),
            sa.ForeignKey("producto.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_cotizacion_analisis_ia_producto_id"),
        "cotizacion_analisis_ia",
        ["producto_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_cotizacion_analisis_ia_producto_id"),
        table_name="cotizacion_analisis_ia",
    )
    op.drop_column("cotizacion_analisis_ia", "producto_id")