"""tipo en orden_produccion: PEDIDO | EXHIBICION | STOCK

Revision ID: f7b8c9d0e1a2
Revises: a3b4c5d6e7f8
Create Date: 2026-09-03

Hace explícito el DESTINO de lo fabricado (antes lo implícito era el booleano
`es_stock`, que mezclaba stock genérico con piezas de exhibición):
- PEDIDO: línea de pedido → envío al cliente.
- EXHIBICION: pieza de showroom (producto es_exhibicion) → ENTRADA a la
  ubicación EXHIBICIÓN con el costo real.
- STOCK: fabricación sin pedido de un producto del catálogo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b8c9d0e1a2'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECK_TIPO = 'ck_orden_produccion_tipo'


def upgrade() -> None:
    op.add_column(
        'orden_produccion',
        sa.Column('tipo', sa.String(length=20), server_default='PEDIDO', nullable=False),
    )
    # Backfill: EXHIBICION si la orden sin pedido fabrica un producto de
    # exhibición; STOCK el resto de órdenes sin pedido; PEDIDO el resto.
    op.execute(
        "UPDATE orden_produccion o SET tipo = 'EXHIBICION' "
        "FROM producto p "
        "WHERE o.producto_id = p.id AND o.es_stock AND p.es_exhibicion"
    )
    op.execute("UPDATE orden_produccion SET tipo = 'STOCK' WHERE es_stock")
    op.create_check_constraint(
        CHECK_TIPO,
        'orden_produccion',
        "tipo IN ('PEDIDO', 'EXHIBICION', 'STOCK')",
    )


def downgrade() -> None:
    op.drop_constraint(CHECK_TIPO, 'orden_produccion', type_='check')
    op.drop_column('orden_produccion', 'tipo')
