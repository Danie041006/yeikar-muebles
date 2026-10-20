"""juegos: piezas internas de un renglón con precio global

Un renglón de cotización/pedido puede declarar piezas (mesa, sillas, sillones…)
sin precio propio. Al pasar a producción se crea una orden interna por pieza,
cada una con su costo; la venta/factura sigue siendo un solo renglón.

Revision ID: f8840b56521c
Revises: i2j3k4l5m6n7
Create Date: 2026-10-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8840b56521c'
down_revision: Union[str, None] = 'i2j3k4l5m6n7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'detalle_cotizacion_pieza',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('detalle_cotizacion_id', sa.BigInteger(), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('cantidad', sa.Numeric(10, 2), nullable=False, server_default='1'),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('orden', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(
            ['detalle_cotizacion_id'], ['detalle_cotizacion.id'],
            name='detalle_cotizacion_pieza_detalle_fkey', ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_detalle_cotizacion_pieza_id', 'detalle_cotizacion_pieza', ['id']
    )
    op.create_index(
        'ix_detalle_cotizacion_pieza_detalle_id',
        'detalle_cotizacion_pieza', ['detalle_cotizacion_id'],
    )

    op.create_table(
        'detalle_pedido_pieza',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('detalle_pedido_id', sa.BigInteger(), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('cantidad', sa.Numeric(10, 2), nullable=False, server_default='1'),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('orden', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(
            ['detalle_pedido_id'], ['detalle_pedido.id'],
            name='detalle_pedido_pieza_detalle_fkey', ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_detalle_pedido_pieza_id', 'detalle_pedido_pieza', ['id']
    )
    op.create_index(
        'ix_detalle_pedido_pieza_detalle_id',
        'detalle_pedido_pieza', ['detalle_pedido_id'],
    )

    # Una línea puede tener N órdenes internas (una por pieza).
    op.drop_constraint(
        'orden_produccion_detalle_pedido_id_key',
        'orden_produccion',
        type_='unique',
    )
    op.add_column(
        'orden_produccion',
        sa.Column('detalle_pieza_id', sa.BigInteger(), nullable=True),
    )
    op.add_column(
        'orden_produccion',
        sa.Column('pieza_nombre', sa.String(length=150), nullable=True),
    )
    op.add_column(
        'orden_produccion',
        sa.Column('cantidad', sa.Numeric(14, 4), nullable=True),
    )
    op.create_index(
        'ix_orden_produccion_detalle_pieza_id',
        'orden_produccion', ['detalle_pieza_id'],
    )
    op.create_foreign_key(
        'fk_orden_produccion_detalle_pieza',
        'orden_produccion', 'detalle_pedido_pieza',
        ['detalle_pieza_id'], ['id'],
        ondelete='SET NULL',
    )

    # Las tablas nuevas entran a la réplica offline (misma función de sync).
    for tabla in ('detalle_cotizacion_pieza', 'detalle_pedido_pieza'):
        op.execute(
            f'CREATE TRIGGER trg_sync_cambio AFTER INSERT OR UPDATE OR DELETE '
            f'ON "{tabla}" FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio()'
        )


def downgrade() -> None:
    # Si hay varios pedidos con más de una orden por renglón, restaurar el
    # UNIQUE fallará: hay que resolver esos datos antes de bajar la migración.
    op.drop_constraint(
        'fk_orden_produccion_detalle_pieza', 'orden_produccion', type_='foreignkey'
    )
    op.drop_index(
        'ix_orden_produccion_detalle_pieza_id', table_name='orden_produccion'
    )
    op.drop_column('orden_produccion', 'cantidad')
    op.drop_column('orden_produccion', 'pieza_nombre')
    op.drop_column('orden_produccion', 'detalle_pieza_id')
    op.create_unique_constraint(
        'orden_produccion_detalle_pedido_id_key',
        'orden_produccion', ['detalle_pedido_id'],
    )

    op.drop_index(
        'ix_detalle_pedido_pieza_detalle_id', table_name='detalle_pedido_pieza'
    )
    op.drop_index('ix_detalle_pedido_pieza_id', table_name='detalle_pedido_pieza')
    op.drop_table('detalle_pedido_pieza')

    op.drop_index(
        'ix_detalle_cotizacion_pieza_detalle_id',
        table_name='detalle_cotizacion_pieza',
    )
    op.drop_index(
        'ix_detalle_cotizacion_pieza_id', table_name='detalle_cotizacion_pieza'
    )
    op.drop_table('detalle_cotizacion_pieza')
