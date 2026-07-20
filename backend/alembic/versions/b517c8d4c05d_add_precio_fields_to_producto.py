"""add_precio_fields_to_producto

Revision ID: b517c8d4c05d
Revises: a1b2c3d4e5f6
Create Date: 2026-07-17

Agrega campos de precio fijo a la tabla producto, importados del Excel
de estructuras de costos de YEIKAR.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b517c8d4c05d'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('producto', sa.Column('precio_costo_base', sa.Numeric(15, 2), nullable=True,
                  comment='TOTAL COSTO DE PRODUCCIÓN extraído del Excel'))
    op.add_column('producto', sa.Column('precio_venta_base', sa.Numeric(15, 2), nullable=True,
                  comment='Precio de Venta sin IVA (con ganancia) del Excel'))
    op.add_column('producto', sa.Column('precio_venta_con_iva', sa.Numeric(15, 2), nullable=True,
                  comment='Total a Pagar incluyendo IVA del Excel'))
    op.add_column('producto', sa.Column('hoja_excel', sa.String(150), nullable=True,
                  comment='Nombre de la hoja fuente en el archivo Excel'))


def downgrade() -> None:
    op.drop_column('producto', 'hoja_excel')
    op.drop_column('producto', 'precio_venta_con_iva')
    op.drop_column('producto', 'precio_venta_base')
    op.drop_column('producto', 'precio_costo_base')
