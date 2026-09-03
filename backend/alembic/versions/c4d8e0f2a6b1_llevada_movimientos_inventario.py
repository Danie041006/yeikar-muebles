"""llevada: flete/aduana en movimientos de inventario

Revision ID: c4d8e0f2a6b1
Revises: b3c7d9e1f5a2
Create Date: 2026-08-31

"La llevada": cuando compran insumos/productos en el exterior, además del
dinero de la compra pagan el flete/aduana para que pasen. Se registra como
columna opcional en los movimientos (para el kardex) y el gasto aparte se
genera en el servicio al registrar la entrada desde una cuenta de caja.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d8e0f2a6b1'
down_revision: Union[str, None] = 'b3c7d9e1f5a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('movimiento_inventario', sa.Column('llevada', sa.Numeric(15, 2), nullable=True))
    op.add_column('movimiento_producto_inventario', sa.Column('llevada', sa.Numeric(15, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('movimiento_producto_inventario', 'llevada')
    op.drop_column('movimiento_inventario', 'llevada')