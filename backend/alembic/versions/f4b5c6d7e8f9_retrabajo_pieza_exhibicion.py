"""retrabajo de piezas de exhibición (orden tipo RETRABAJO)

Una pieza de exhibición ya fabricada y en stock se puede retrabajar (recolor,
retapizado, ajustes): la orden tipo RETRABAJO la saca del showroom al crearse
y al finalizar la devuelve al stock con su costo X + el costo real del retoque.

- orden_produccion.producto_inventario_id: la fila de producto_inventario que
  salió y a la que la pieza vuelve.
- orden_produccion.observaciones: motivo/contexto libre (qué se cambia y para
  quién). Los demás tipos de orden la dejan NULL.

Revision ID: f4b5c6d7e8f9
Revises: e2f3a4b5c6d7
Create Date: 2026-10-15 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4b5c6d7e8f9'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'orden_produccion',
        sa.Column('producto_inventario_id', sa.BigInteger(), nullable=True),
    )
    op.add_column(
        'orden_produccion',
        sa.Column('observaciones', sa.Text(), nullable=True),
    )
    op.create_index(
        'ix_orden_produccion_producto_inventario_id',
        'orden_produccion',
        ['producto_inventario_id'],
    )
    op.create_foreign_key(
        'fk_orden_produccion_producto_inventario',
        'orden_produccion',
        'producto_inventario',
        ['producto_inventario_id'],
        ['id'],
        ondelete='SET NULL',
    )
    # El CHECK del tipo se amplía con RETRABAJO (antes: PEDIDO/EXHIBICION/STOCK).
    op.drop_constraint('ck_orden_produccion_tipo', 'orden_produccion', type_='check')
    op.create_check_constraint(
        'ck_orden_produccion_tipo',
        'orden_produccion',
        "tipo IN ('PEDIDO', 'EXHIBICION', 'STOCK', 'RETRABAJO')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_orden_produccion_tipo', 'orden_produccion', type_='check')
    op.create_check_constraint(
        'ck_orden_produccion_tipo',
        'orden_produccion',
        "tipo IN ('PEDIDO', 'EXHIBICION', 'STOCK')",
    )
    op.drop_constraint(
        'fk_orden_produccion_producto_inventario',
        'orden_produccion',
        type_='foreignkey',
    )
    op.drop_index('ix_orden_produccion_producto_inventario_id', table_name='orden_produccion')
    op.drop_column('orden_produccion', 'observaciones')
    op.drop_column('orden_produccion', 'producto_inventario_id')
