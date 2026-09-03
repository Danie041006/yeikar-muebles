"""rediseno productos en crudo

Revision ID: daa909641935
Revises: 137f47efc614
Create Date: 2026-08-28 01:14:59.230999

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'daa909641935'
down_revision: Union[str, None] = '137f47efc614'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # El rediseño convierte el "producto en crudo" en un ÍTEM LIBRE (nombre que
    # elige el usuario, sin ligarse al catálogo de productos). Se dropea la tabla
    # vieja (ælizada en la migración 137f47efc614) y se recrea desde cero.
    op.drop_table('producto_crudo_inventario')

    op.create_table('producto_crudo_inventario',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('area_id', sa.BigInteger(), nullable=True),
        sa.Column('ubicacion_id', sa.BigInteger(), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['area_id'], ['area.id'], name='fk_producto_crudo_inventario_area_id'),
        sa.ForeignKeyConstraint(['ubicacion_id'], ['ubicacion.id'], ondelete='RESTRICT', name='fk_producto_crudo_inventario_ubicacion_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_producto_crudo_inventario_id'), 'producto_crudo_inventario', ['id'], unique=False)
    op.create_index(op.f('ix_producto_crudo_inventario_area_id'), 'producto_crudo_inventario', ['area_id'], unique=False)

    # Segunda producción: fabricación de un ítem en crudo.
    op.create_table('produccion_crudo',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('crudo_id', sa.BigInteger(), nullable=False),
        sa.Column('estado', sa.String(length=50), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('costo_total', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('fecha_inicio', sa.DateTime(), nullable=True),
        sa.Column('fecha_fin', sa.DateTime(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('creado_por_id', sa.BigInteger(), nullable=True),
        sa.Column('actualizado_por_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['actualizado_por_id'], ['usuario.id'], ondelete='SET NULL', name='fk_produccion_crudo_actualizado_por_id'),
        sa.ForeignKeyConstraint(['crudo_id'], ['producto_crudo_inventario.id'], ondelete='RESTRICT', name='fk_produccion_crudo_crudo_id'),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuario.id'], ondelete='SET NULL', name='fk_produccion_crudo_creado_por_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_produccion_crudo_id'), 'produccion_crudo', ['id'], unique=False)
    op.create_index(op.f('ix_produccion_crudo_crudo_id'), 'produccion_crudo', ['crudo_id'], unique=False)
    op.create_index(op.f('ix_produccion_crudo_creado_por_id'), 'produccion_crudo', ['creado_por_id'], unique=False)

    # Consumos de material en una producción de crudo (solicitante + quién registró).
    op.create_table('produccion_crudo_consumo',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('produccion_crudo_id', sa.BigInteger(), nullable=False),
        sa.Column('material_id', sa.BigInteger(), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('costo_unitario', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('seccion', sa.String(length=50), nullable=True),
        sa.Column('solicitante_empleado_id', sa.BigInteger(), nullable=True),
        sa.Column('creado_por_id', sa.BigInteger(), nullable=True),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuario.id'], ondelete='SET NULL', name='fk_produccion_crudo_consumo_creado_por_id'),
        sa.ForeignKeyConstraint(['material_id'], ['material.id'], name='fk_produccion_crudo_consumo_material_id'),
        sa.ForeignKeyConstraint(['produccion_crudo_id'], ['produccion_crudo.id'], ondelete='CASCADE', name='fk_produccion_crudo_consumo_produccion_id'),
        sa.ForeignKeyConstraint(['solicitante_empleado_id'], ['empleado.id'], name='fk_produccion_crudo_consumo_solicitante_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_produccion_crudo_consumo_id'), 'produccion_crudo_consumo', ['id'], unique=False)
    op.create_index(op.f('ix_produccion_crudo_consumo_produccion_crudo_id'), 'produccion_crudo_consumo', ['produccion_crudo_id'], unique=False)
    op.create_index(op.f('ix_produccion_crudo_consumo_solicitante_empleado_id'), 'produccion_crudo_consumo', ['solicitante_empleado_id'], unique=False)
    op.create_index(op.f('ix_produccion_crudo_consumo_creado_por_id'), 'produccion_crudo_consumo', ['creado_por_id'], unique=False)

    # Trazabilidad: pieza de crudo asignada a un detalle de pedido (descuento).
    op.create_table('produccion_crudo_uso',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('crudo_id', sa.BigInteger(), nullable=False),
        sa.Column('detalle_pedido_id', sa.BigInteger(), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('creado_por_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['crudo_id'], ['producto_crudo_inventario.id'], ondelete='RESTRICT', name='fk_produccion_crudo_uso_crudo_id'),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuario.id'], ondelete='SET NULL', name='fk_produccion_crudo_uso_creado_por_id'),
        sa.ForeignKeyConstraint(['detalle_pedido_id'], ['detalle_pedido.id'], name='fk_produccion_crudo_uso_detalle_pedido_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_produccion_crudo_uso_id'), 'produccion_crudo_uso', ['id'], unique=False)
    op.create_index(op.f('ix_produccion_crudo_uso_crudo_id'), 'produccion_crudo_uso', ['crudo_id'], unique=False)
    op.create_index(op.f('ix_produccion_crudo_uso_detalle_pedido_id'), 'produccion_crudo_uso', ['detalle_pedido_id'], unique=False)
    op.create_index(op.f('ix_produccion_crudo_uso_creado_por_id'), 'produccion_crudo_uso', ['creado_por_id'], unique=False)


def downgrade() -> None:
    op.drop_table('produccion_crudo_uso')
    op.drop_table('produccion_crudo_consumo')
    op.drop_table('produccion_crudo')

    op.drop_index(op.f('ix_producto_crudo_inventario_area_id'), table_name='producto_crudo_inventario')
    op.drop_index(op.f('ix_producto_crudo_inventario_id'), table_name='producto_crudo_inventario')
    op.drop_table('producto_crudo_inventario')

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
    op.create_index(op.f('ix_producto_crudo_inventario_producto_id'), 'producto_crudo_inventario', ['producto_id'], unique=False)
    op.create_index(op.f('ix_producto_crudo_inventario_orden_produccion_origen_id'), 'producto_crudo_inventario', ['orden_produccion_origen_id'], unique=False)
    op.create_index(op.f('ix_producto_crudo_inventario_orden_produccion_destino_id'), 'producto_crudo_inventario', ['orden_produccion_destino_id'], unique=False)
