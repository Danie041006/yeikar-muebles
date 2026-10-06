"""orden_pieza: checklist de piezas del mueble (juego = varias piezas)

El taller marca las piezas (sofá, poltronas…) dentro de la tarjeta. Se
auto-detectan de la descripción del renglón; no tocan precio, receta ni stock.

Revision ID: pz1e2z3a4b5c
Revises: z0a1b2c3d4e5
Create Date: 2026-10-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'pz1e2z3a4b5c'
down_revision: Union[str, None] = 'z0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'orden_pieza',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('orden_produccion_id', sa.BigInteger(), nullable=False),
        sa.Column('posicion', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('cantidad', sa.Numeric(10, 2), nullable=False, server_default='1'),
        sa.Column('area_id', sa.BigInteger(), nullable=True),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('completada', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('completada_por_id', sa.BigInteger(), nullable=True),
        sa.Column('fecha_completada', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(
            ['orden_produccion_id'], ['orden_produccion.id'],
            name='orden_pieza_orden_produccion_id_fkey', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['area_id'], ['area.id'],
            name='orden_pieza_area_id_fkey', ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['completada_por_id'], ['usuario.id'],
            name='orden_pieza_completada_por_fkey', ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_orden_pieza_id', 'orden_pieza', ['id'])
    op.create_index(
        'ix_orden_pieza_orden_produccion_id', 'orden_pieza', ['orden_produccion_id']
    )


def downgrade() -> None:
    op.drop_index('ix_orden_pieza_orden_produccion_id', table_name='orden_pieza')
    op.drop_index('ix_orden_pieza_id', table_name='orden_pieza')
    op.drop_table('orden_pieza')
