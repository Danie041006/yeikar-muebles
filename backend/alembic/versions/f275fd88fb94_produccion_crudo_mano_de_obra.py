"""produccion crudo mano de obra

Revision ID: f275fd88fb94
Revises: daa909641935
Create Date: 2026-08-28 02:04:17.302376

NOTA: esta migración toca SOLO la nueva tabla produccion_crudo_mano_obra.
El autogenerate reportaba drif actual del indizado (naming ix_* vs DB) que
NO corresponde a este cambio y NO debe aplicarse.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f275fd88fb94'
down_revision: Union[str, None] = 'daa909641935'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'produccion_crudo_mano_obra',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('produccion_crudo_id', sa.BigInteger(), nullable=False),
        sa.Column('empleado_id', sa.BigInteger(), nullable=False),
        sa.Column('monto', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('porcentaje_recargo', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('listo_nomina', sa.Boolean(), nullable=False),
        sa.Column('pagado', sa.Boolean(), nullable=False),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('creado_por_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuario.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['empleado_id'], ['empleado.id'], ),
        sa.ForeignKeyConstraint(['produccion_crudo_id'], ['produccion_crudo.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_produccion_crudo_mano_obra_creado_por_id'), 'produccion_crudo_mano_obra', ['creado_por_id'], unique=False)
    op.create_index(op.f('ix_produccion_crudo_mano_obra_produccion_crudo_id'), 'produccion_crudo_mano_obra', ['produccion_crudo_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_produccion_crudo_mano_obra_produccion_crudo_id'), table_name='produccion_crudo_mano_obra')
    op.drop_index(op.f('ix_produccion_crudo_mano_obra_creado_por_id'), table_name='produccion_crudo_mano_obra')
    op.drop_table('produccion_crudo_mano_obra')
