"""indices_fecha_libros

Índices por `fecha` en los tres kardex (movimiento_inventario,
movimiento_producto_inventario y movimiento_crudo) para el Libro de Entradas
y Salidas: las consultas por rango de fechas caían en Seq Scan completo y
crecen con la operación. Aditivo y reversible.

Revision ID: c9d0e1f2a3b4
Revises: b3c4d5e6f7a8
Create Date: 2026-10-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_movimiento_inventario_fecha', 'movimiento_inventario', ['fecha'])
    op.create_index(
        'ix_movimiento_producto_inventario_fecha',
        'movimiento_producto_inventario',
        ['fecha'],
    )
    op.create_index('ix_movimiento_crudo_fecha', 'movimiento_crudo', ['fecha'])


def downgrade() -> None:
    op.drop_index('ix_movimiento_crudo_fecha', table_name='movimiento_crudo')
    op.drop_index(
        'ix_movimiento_producto_inventario_fecha',
        table_name='movimiento_producto_inventario',
    )
    op.drop_index('ix_movimiento_inventario_fecha', table_name='movimiento_inventario')
