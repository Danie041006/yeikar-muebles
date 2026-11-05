"""envio_detalle: varias piezas sin orden en el mismo despacho

La Fase 2 permitió entregar piezas de exhibición que no tienen orden de
producción. El índice parcial `uq_envio_detalle_sin_orden` (envio, detalle)
impedía mandar DOS piezas del mismo renglón en un despacho (mesa + sillas).

Se separa en dos reglas:
  - renglón sin orden ni pieza (reventa/insumo): una sola fila;
  - pieza sin orden: única por (envío, renglón, pieza).

Revision ID: f2a3b4c5d6e7
Revises: d9e0f1a2b3c4
Create Date: 2026-11-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'd9e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('uq_envio_detalle_sin_orden', table_name='envio_detalle')
    op.create_index(
        'uq_envio_detalle_sin_orden',
        'envio_detalle',
        ['envio_id', 'detalle_pedido_id'],
        unique=True,
        postgresql_where=sa.text(
            'orden_produccion_id IS NULL AND detalle_pieza_id IS NULL'
        ),
    )
    op.create_index(
        'uq_envio_detalle_sin_orden_pieza',
        'envio_detalle',
        ['envio_id', 'detalle_pedido_id', 'detalle_pieza_id'],
        unique=True,
        postgresql_where=sa.text(
            'orden_produccion_id IS NULL AND detalle_pieza_id IS NOT NULL'
        ),
    )


def downgrade() -> None:
    op.drop_index('uq_envio_detalle_sin_orden_pieza', table_name='envio_detalle')
    op.drop_index('uq_envio_detalle_sin_orden', table_name='envio_detalle')
    op.create_index(
        'uq_envio_detalle_sin_orden',
        'envio_detalle',
        ['envio_id', 'detalle_pedido_id'],
        unique=True,
        postgresql_where=sa.text('orden_produccion_id IS NULL'),
    )
