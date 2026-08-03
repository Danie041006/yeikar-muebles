"""add_currency_to_cotizacion

Revision ID: d3e4f5a6b7c8
Revises: c510a2c6c2df
Create Date: 2026-07-30 10:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = '8b6c7d8e9f01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO moneda (codigo, nombre, simbolo, activo)
        SELECT 'EUR', 'Euro', '\u20ac', true
        WHERE NOT EXISTS (SELECT 1 FROM moneda WHERE codigo = 'EUR')
    """)

    op.add_column('cotizacion', sa.Column('moneda_id', sa.BigInteger(), nullable=False, server_default='1'))
    op.create_foreign_key('fk_cotizacion_moneda', 'cotizacion', 'moneda', ['moneda_id'], ['id'])

    op.add_column('cotizacion', sa.Column('tasa_cambio', sa.Numeric(15, 6), nullable=False, server_default='1.0'))

    op.add_column('cotizacion', sa.Column('total_en_moneda_base', sa.Numeric(15, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('cotizacion', 'total_en_moneda_base')
    op.drop_column('cotizacion', 'tasa_cambio')
    op.drop_constraint('fk_cotizacion_moneda', 'cotizacion', type_='foreignkey')
    op.drop_column('cotizacion', 'moneda_id')
