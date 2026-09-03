"""productos en crudo

Revision ID: 137f47efc614
Revises: 62bff25b4e7c
Create Date: 2026-08-28 00:31:46.420414

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '137f47efc614'
down_revision: Union[str, None] = '62bff25b4e7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tabla de inventario de "productos en crudo" (muebles semi-terminados).
    op.create_table('producto_crudo_inventario',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('producto_id', sa.BigInteger(), nullable=False),
    sa.Column('ubicacion_id', sa.BigInteger(), nullable=False),
    sa.Column('cantidad', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('ancho', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('largo', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('alto', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('etapas_completadas', sa.JSON(), nullable=False),
    sa.Column('costo_total', sa.Numeric(precision=15, scale=2), nullable=False),
    sa.Column('orden_produccion_origen_id', sa.BigInteger(), nullable=True),
    sa.Column('orden_produccion_destino_id', sa.BigInteger(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['orden_produccion_destino_id'], ['orden_produccion.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['orden_produccion_origen_id'], ['orden_produccion.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['producto_id'], ['producto.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['ubicacion_id'], ['ubicacion.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_producto_crudo_inventario_id'), 'producto_crudo_inventario', ['id'], unique=False)
    op.create_index(op.f('ix_producto_crudo_inventario_orden_produccion_destino_id'), 'producto_crudo_inventario', ['orden_produccion_destino_id'], unique=False)
    op.create_index(op.f('ix_producto_crudo_inventario_orden_produccion_origen_id'), 'producto_crudo_inventario', ['orden_produccion_origen_id'], unique=False)
    op.create_index(op.f('ix_producto_crudo_inventario_producto_id'), 'producto_crudo_inventario', ['producto_id'], unique=False)

    # Etapas pre-marcadas (asignación de crudo) no tienen empleado responsable.
    op.alter_column('etapa_produccion', 'empleado_responsable_id',
               existing_type=sa.BIGINT(),
               nullable=True)

    # Columnas nuevas + detalle_pedido_id nullable + FK a producto en órdenes.
    op.add_column('orden_produccion', sa.Column('producto_id', sa.BigInteger(), nullable=True))
    op.add_column('orden_produccion', sa.Column('ancho', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('orden_produccion', sa.Column('largo', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('orden_produccion', sa.Column('alto', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('orden_produccion', sa.Column('es_stock', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.alter_column('orden_produccion', 'detalle_pedido_id',
               existing_type=sa.BIGINT(),
               nullable=True)
    op.create_index(op.f('ix_orden_produccion_producto_id'), 'orden_produccion', ['producto_id'], unique=False)
    op.create_foreign_key(None, 'orden_produccion', 'producto', ['producto_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(None, 'orden_produccion', type_='foreignkey')
    op.drop_index(op.f('ix_orden_produccion_producto_id'), table_name='orden_produccion')
    op.alter_column('orden_produccion', 'detalle_pedido_id',
               existing_type=sa.BIGINT(),
               nullable=False)
    op.drop_column('orden_produccion', 'es_stock')
    op.drop_column('orden_produccion', 'alto')
    op.drop_column('orden_produccion', 'largo')
    op.drop_column('orden_produccion', 'ancho')
    op.drop_column('orden_produccion', 'producto_id')
    op.alter_column('etapa_produccion', 'empleado_responsable_id',
               existing_type=sa.BIGINT(),
               nullable=False)
    op.drop_index(op.f('ix_producto_crudo_inventario_producto_id'), table_name='producto_crudo_inventario')
    op.drop_index(op.f('ix_producto_crudo_inventario_orden_produccion_origen_id'), table_name='producto_crudo_inventario')
    op.drop_index(op.f('ix_producto_crudo_inventario_orden_produccion_destino_id'), table_name='producto_crudo_inventario')
    op.drop_index(op.f('ix_producto_crudo_inventario_id'), table_name='producto_crudo_inventario')
    op.drop_table('producto_crudo_inventario')
