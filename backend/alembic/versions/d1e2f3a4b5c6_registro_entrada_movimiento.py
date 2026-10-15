"""registro_entrada_movimiento

Guarda en el propio movimiento de inventario los datos del registro de la
compra que antes solo vivían en el gasto o embebidos como texto: cuenta desde
la que se pagó (contado), % de descuento aplicado y bandera de fiar. Así el
Libro de Entradas y Salidas muestra los mismos campos que se llenan al
registrar la entrada.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-10-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'movimiento_inventario',
        sa.Column('pagado_desde_metodo_caja_id', sa.BigInteger(), nullable=True),
    )
    op.add_column(
        'movimiento_inventario',
        sa.Column('descuento_porcentaje', sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        'movimiento_inventario',
        sa.Column('fiar', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.create_foreign_key(
        'fk_movimiento_inventario_pagado_desde',
        'movimiento_inventario',
        'metodo_caja',
        ['pagado_desde_metodo_caja_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_movimiento_inventario_pagado_desde',
        'movimiento_inventario',
        type_='foreignkey',
    )
    op.drop_column('movimiento_inventario', 'fiar')
    op.drop_column('movimiento_inventario', 'descuento_porcentaje')
    op.drop_column('movimiento_inventario', 'pagado_desde_metodo_caja_id')
