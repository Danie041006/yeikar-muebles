"""mano_obra.precio_produccion_id — trazabilidad del tarifario usado en cada MO.

Revision ID: 0761b7ce4ad9
Revises: a7b8c9d0e1f2
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0761b7ce4ad9'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'mano_obra',
        sa.Column('precio_produccion_id', sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        'fk_mano_obra_precio_produccion',
        'mano_obra',
        'precio_produccion',
        ['precio_produccion_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_mano_obra_precio_produccion_id',
        'mano_obra',
        ['precio_produccion_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_mano_obra_precio_produccion_id', table_name='mano_obra')
    op.drop_constraint('fk_mano_obra_precio_produccion', 'mano_obra', type_='foreignkey')
    op.drop_column('mano_obra', 'precio_produccion_id')
