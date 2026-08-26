"""consumo_material.solicitante_empleado_id (quién pide el material)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    # Solicitante = empleado que PIDE el material (trazabilidad). Nullable en BD
    # para no romper los consumos históricos; la API lo exige obligatorio.
    op.add_column(
        'consumo_material',
        sa.Column('solicitante_empleado_id', sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        'fk_consumo_material_solicitante_empleado',
        'consumo_material',
        'empleado',
        ['solicitante_empleado_id'],
        ['id'],
    )
    op.create_index(
        'ix_consumo_material_solicitante_empleado_id',
        'consumo_material',
        ['solicitante_empleado_id'],
    )


def downgrade():
    op.drop_index('ix_consumo_material_solicitante_empleado_id', table_name='consumo_material')
    op.drop_constraint('fk_consumo_material_solicitante_empleado', 'consumo_material', type_='foreignkey')
    op.drop_column('consumo_material', 'solicitante_empleado_id')
