"""metodo_caja_id en compra

Revision ID: d5f2a1c9e8b7
Revises: cee7ebd51154
Create Date: 2026-08-12

Permite registrar de qué cuenta de caja sale el dinero al recibir una
compra CONTADO (fix: la compra recibida no descuenta caja).
"""
from alembic import op
import sqlalchemy as sa

revision = 'd5f2a1c9e8b7'
down_revision = 'cee7ebd51154'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'compra',
        sa.Column('metodo_caja_id', sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        'fk_compra_metodo_caja',
        'compra', 'metodo_caja',
        ['metodo_caja_id'], ['id'],
        ondelete='RESTRICT',
    )


def downgrade():
    op.drop_constraint('fk_compra_metodo_caja', 'compra', type_='foreignkey')
    op.drop_column('compra', 'metodo_caja_id')
