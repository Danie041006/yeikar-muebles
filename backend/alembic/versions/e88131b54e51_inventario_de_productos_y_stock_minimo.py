"""inventario de productos (terminados/reventa) y stock minimo por material/producto.

Revision ID: e88131b54e51
Revises: e0f1a2b3c4d5
Create Date: 2026-08-06 02:01:16.000631

Nota: migración manual. El autogenerate mezclaba cambios espurios preexistentes
(tipos INTEGER->BigInteger en usuario/usuario_rol, índices huérfanos); aquí solo
se incluyen las tablas nuevas y las columnas de stock mínimo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e88131b54e51'
down_revision: Union[str, None] = 'e0f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Stock mínimo por material (alerta de reabastecimiento)
    op.add_column('material', sa.Column('stock_minimo', sa.Numeric(10, 2), server_default='8', nullable=False))

    # Stock mínimo por producto (terminados / de reventa)
    op.add_column('producto', sa.Column('stock_minimo', sa.Numeric(10, 2), server_default='8', nullable=False))

    # Marca si un producto es de REVENTA (colchón, nevera, electrodoméstico)
    # vs. fabricado por YEIKAR (muebles).
    op.add_column('producto', sa.Column('es_reventa', sa.Boolean(), server_default='false', nullable=False))

    # Stock actual de productos terminados / de reventa por ubicación
    op.create_table(
        'producto_inventario',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('producto_id', sa.BigInteger(), nullable=False),
        sa.Column('ubicacion_id', sa.BigInteger(), nullable=False),
        sa.Column('cantidad', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('costo_promedio', sa.Numeric(15, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['producto_id'], ['producto.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['ubicacion_id'], ['ubicacion.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('producto_id', 'ubicacion_id', name='uq_producto_inventario_producto_ubicacion'),
    )
    op.create_index('ix_producto_inventario_id', 'producto_inventario', ['id'])

    # Kardex de movimientos de productos
    op.create_table(
        'movimiento_producto_inventario',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('producto_id', sa.BigInteger(), nullable=False),
        sa.Column('ubicacion_id', sa.BigInteger(), nullable=False),
        sa.Column('tipo', sa.String(50), nullable=False),
        sa.Column('cantidad', sa.Numeric(12, 2), nullable=False),
        sa.Column('costo_unitario', sa.Numeric(15, 2), nullable=True),
        sa.Column('fecha', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('referencia_tipo', sa.String(100), nullable=True),
        sa.Column('referencia_id', sa.BigInteger(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['producto_id'], ['producto.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['ubicacion_id'], ['ubicacion.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_movimiento_producto_inventario_id', 'movimiento_producto_inventario', ['id'])


def downgrade() -> None:
    op.drop_index('ix_movimiento_producto_inventario_id', table_name='movimiento_producto_inventario')
    op.drop_table('movimiento_producto_inventario')
    op.drop_index('ix_producto_inventario_id', table_name='producto_inventario')
    op.drop_table('producto_inventario')
    op.drop_column('producto', 'es_reventa')
    op.drop_column('producto', 'stock_minimo')
    op.drop_column('material', 'stock_minimo')
