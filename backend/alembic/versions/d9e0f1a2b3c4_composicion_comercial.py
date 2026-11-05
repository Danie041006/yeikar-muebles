"""composición comercial de piezas en cotización, pedido y despacho

Segunda fase de la composición de muebles:

- Cada pieza de un renglón puede apuntar a un producto del catálogo, llevar su
  propio precio y declarar que sale de un conjunto de exhibición
  (`conjunto_origen_id`) o que necesita retrabajo.
- El pedido espeja esos datos y congela el costo real de las piezas que salen
  del showroom (`costo_unitario`).
- `detalle_pedido.piezas_apartadas` marca que el despiece ya se ejecutó
  (idempotencia).
- `envio_detalle.detalle_pieza_id` distingue varias piezas del mismo renglón
  que no tienen orden de producción (exhibición ya lista).

Migración 100% aditiva; las tablas ya tienen el trigger de sync.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Piezas de la cotización ---
    op.add_column('detalle_cotizacion_pieza', sa.Column('producto_id', sa.BigInteger(), nullable=True))
    op.add_column('detalle_cotizacion_pieza', sa.Column('precio', sa.Numeric(15, 2), nullable=True))
    op.add_column('detalle_cotizacion_pieza', sa.Column('origen', sa.String(length=20), nullable=True))
    op.add_column('detalle_cotizacion_pieza', sa.Column('conjunto_origen_id', sa.BigInteger(), nullable=True))
    op.add_column('detalle_cotizacion_pieza', sa.Column('modificacion', sa.Text(), nullable=True))
    op.add_column(
        'detalle_cotizacion_pieza',
        sa.Column('requiere_retrabajo', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column('detalle_cotizacion_pieza', sa.Column('precio_modificacion', sa.Numeric(15, 2), nullable=True))
    op.create_foreign_key(
        'fk_detalle_cotizacion_pieza_producto',
        'detalle_cotizacion_pieza', 'producto',
        ['producto_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_detalle_cotizacion_pieza_conjunto_origen',
        'detalle_cotizacion_pieza', 'producto',
        ['conjunto_origen_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        'ix_detalle_cotizacion_pieza_producto_id',
        'detalle_cotizacion_pieza', ['producto_id'],
    )

    # --- Piezas del pedido ---
    op.add_column('detalle_pedido_pieza', sa.Column('producto_id', sa.BigInteger(), nullable=True))
    op.add_column('detalle_pedido_pieza', sa.Column('precio', sa.Numeric(15, 2), nullable=True))
    op.add_column('detalle_pedido_pieza', sa.Column('origen', sa.String(length=20), nullable=True))
    op.add_column('detalle_pedido_pieza', sa.Column('conjunto_origen_id', sa.BigInteger(), nullable=True))
    op.add_column('detalle_pedido_pieza', sa.Column('modificacion', sa.Text(), nullable=True))
    op.add_column(
        'detalle_pedido_pieza',
        sa.Column('requiere_retrabajo', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column('detalle_pedido_pieza', sa.Column('precio_modificacion', sa.Numeric(15, 2), nullable=True))
    op.add_column('detalle_pedido_pieza', sa.Column('costo_unitario', sa.Numeric(15, 2), nullable=True))
    op.create_foreign_key(
        'fk_detalle_pedido_pieza_producto',
        'detalle_pedido_pieza', 'producto',
        ['producto_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_detalle_pedido_pieza_conjunto_origen',
        'detalle_pedido_pieza', 'producto',
        ['conjunto_origen_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        'ix_detalle_pedido_pieza_producto_id',
        'detalle_pedido_pieza', ['producto_id'],
    )

    # --- Renglón del pedido: despiece ya ejecutado ---
    op.add_column(
        'detalle_pedido',
        sa.Column('piezas_apartadas', sa.Boolean(), nullable=False, server_default='false'),
    )

    # --- Despacho: pieza sin orden (exhibición ya lista) ---
    op.add_column('envio_detalle', sa.Column('detalle_pieza_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'fk_envio_detalle_detalle_pieza',
        'envio_detalle', 'detalle_pedido_pieza',
        ['detalle_pieza_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        'ix_envio_detalle_detalle_pieza_id',
        'envio_detalle', ['detalle_pieza_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_envio_detalle_detalle_pieza_id', table_name='envio_detalle')
    op.drop_constraint('fk_envio_detalle_detalle_pieza', 'envio_detalle', type_='foreignkey')
    op.drop_column('envio_detalle', 'detalle_pieza_id')

    op.drop_column('detalle_pedido', 'piezas_apartadas')

    op.drop_index('ix_detalle_pedido_pieza_producto_id', table_name='detalle_pedido_pieza')
    op.drop_constraint('fk_detalle_pedido_pieza_conjunto_origen', 'detalle_pedido_pieza', type_='foreignkey')
    op.drop_constraint('fk_detalle_pedido_pieza_producto', 'detalle_pedido_pieza', type_='foreignkey')
    op.drop_column('detalle_pedido_pieza', 'costo_unitario')
    op.drop_column('detalle_pedido_pieza', 'precio_modificacion')
    op.drop_column('detalle_pedido_pieza', 'requiere_retrabajo')
    op.drop_column('detalle_pedido_pieza', 'modificacion')
    op.drop_column('detalle_pedido_pieza', 'conjunto_origen_id')
    op.drop_column('detalle_pedido_pieza', 'origen')
    op.drop_column('detalle_pedido_pieza', 'precio')
    op.drop_column('detalle_pedido_pieza', 'producto_id')

    op.drop_index('ix_detalle_cotizacion_pieza_producto_id', table_name='detalle_cotizacion_pieza')
    op.drop_constraint('fk_detalle_cotizacion_pieza_conjunto_origen', 'detalle_cotizacion_pieza', type_='foreignkey')
    op.drop_constraint('fk_detalle_cotizacion_pieza_producto', 'detalle_cotizacion_pieza', type_='foreignkey')
    op.drop_column('detalle_cotizacion_pieza', 'precio_modificacion')
    op.drop_column('detalle_cotizacion_pieza', 'requiere_retrabajo')
    op.drop_column('detalle_cotizacion_pieza', 'modificacion')
    op.drop_column('detalle_cotizacion_pieza', 'conjunto_origen_id')
    op.drop_column('detalle_cotizacion_pieza', 'origen')
    op.drop_column('detalle_cotizacion_pieza', 'precio')
    op.drop_column('detalle_cotizacion_pieza', 'producto_id')
