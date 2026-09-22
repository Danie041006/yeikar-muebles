"""Etiqueta legible del uso de material (tablita de costos en vivo)

Cada consumo puede llevar un `detalle_uso` humano ("Pieza 2×10×5",
"1.500 cm (cuenta del taller)") que la tablita de costos muestra como
sub-etiqueta del renglón. NULL = derivarla de las columnas de captura.

Revision ID: u6v7w8x9y0z1
Revises: t5u6v7w8x9y0
"""
import sqlalchemy as sa
from alembic import op

revision = 'u6v7w8x9y0z1'
down_revision = 't5u6v7w8x9y0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'consumo_material',
        sa.Column('detalle_uso', sa.String(length=120), nullable=True),
    )


def downgrade():
    op.drop_column('consumo_material', 'detalle_uso')
