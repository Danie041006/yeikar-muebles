"""transferencias entre cuentas de caja

Revision ID: n2o3p4q5r6s7
Revises: f7b8c9d0e1a2
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'n2o3p4q5r6s7'
down_revision = 'f7b8c9d0e1a2'
branch_labels = None
depends_on = None


def upgrade():
    # Empareja las dos patas (SALIDA en origen + ENTRADA en destino) de una
    # misma transferencia. Sin FK: el valor compartido es el id de la pata
    # de salida (se asigna tras el primer flush).
    op.add_column(
        'movimiento_caja',
        sa.Column('transferencia_id', sa.BigInteger(), nullable=True),
    )
    op.create_index(
        'ix_movimiento_caja_transferencia_id',
        'movimiento_caja',
        ['transferencia_id'],
    )


def downgrade():
    op.drop_index('ix_movimiento_caja_transferencia_id', table_name='movimiento_caja')
    op.drop_column('movimiento_caja', 'transferencia_id')
