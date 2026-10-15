"""registro_entrada_producto

Igual que en movimiento_inventario (migración d1e2f3a4b5c6), guarda en el
propio movimiento de producto los datos del registro de la compra: cuenta
desde la que se pagó (contado), % de descuento aplicado y bandera de fiar.
Así el Libro de Entradas y Salidas muestra, también para reventa/plásticos,
los mismos campos que se llenan al registrar la entrada.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-10-15 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'movimiento_producto_inventario',
        sa.Column('pagado_desde_metodo_caja_id', sa.BigInteger(), nullable=True),
    )
    op.add_column(
        'movimiento_producto_inventario',
        sa.Column('descuento_porcentaje', sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        'movimiento_producto_inventario',
        sa.Column('fiar', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.create_foreign_key(
        'fk_mov_producto_pagado_desde',
        'movimiento_producto_inventario',
        'metodo_caja',
        ['pagado_desde_metodo_caja_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_mov_producto_pagado_desde',
        'movimiento_producto_inventario',
        type_='foreignkey',
    )
    op.drop_column('movimiento_producto_inventario', 'fiar')
    op.drop_column('movimiento_producto_inventario', 'descuento_porcentaje')
    op.drop_column('movimiento_producto_inventario', 'pagado_desde_metodo_caja_id')
