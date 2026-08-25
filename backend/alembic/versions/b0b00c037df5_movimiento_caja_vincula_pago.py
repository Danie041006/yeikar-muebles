"""movimiento_caja vincula pago

Revision ID: b0b00c037df5
Revises: f2a1b3c4d5e6
Create Date: 2026-08-06 09:39:39.250266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0b00c037df5'
down_revision: Union[str, None] = 'f2a1b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('movimiento_caja', sa.Column('pago_id', sa.BigInteger(), nullable=True))
    op.create_index(op.f('ix_movimiento_caja_pago_id'), 'movimiento_caja', ['pago_id'], unique=False)
    op.create_foreign_key(
        'fk_movimiento_caja_pago_id', 'movimiento_caja', 'pago',
        ['pago_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_movimiento_caja_pago_id', 'movimiento_caja', type_='foreignkey')
    op.drop_index(op.f('ix_movimiento_caja_pago_id'), table_name='movimiento_caja')
    op.drop_column('movimiento_caja', 'pago_id')
