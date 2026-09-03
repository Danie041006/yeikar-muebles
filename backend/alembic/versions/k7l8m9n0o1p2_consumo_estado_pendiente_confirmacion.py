"""consumo_material.estado (PENDIENTE/CONFIRMADO) — confirmación de uso de láminas

Revision ID: k7l8m9n0o1p2
Revises: b6c7d8e9f0a1
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'k7l8m9n0o1p2'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade():
    # Default CONFIRMADO: los consumos históricos (y los no laminares) quedan
    # como estaban. Solo el modo "lámina completa" crea PENDIENTE.
    op.add_column(
        'consumo_material',
        sa.Column('estado', sa.String(20), nullable=False, server_default='CONFIRMADO'),
    )
    op.create_index(
        'ix_consumo_material_estado',
        'consumo_material',
        ['estado'],
    )


def downgrade():
    op.drop_index('ix_consumo_material_estado', table_name='consumo_material')
    op.drop_column('consumo_material', 'estado')