"""Pedido abierto de material: permitir cantidad = 0 en consumo_material

El pedido ABIERTO (piden "madera" a secas, la cantidad solo se conoce al
confirmar el uso) registra el consumo con cantidad = 0 y sin movimiento de
inventario. El CHECK original `cantidad > 0` lo bloqueaba: se relaja a
`cantidad >= 0`. 0 solo es válido mientras el consumo está PENDIENTE (el
servicio valida > 0 al confirmar y para consumos no-pedido).

Revision ID: t5u6v7w8x9y0
Revises: s5t6u7v8w9x0
"""
from alembic import op

revision = 't5u6v7w8x9y0'
down_revision = 's5t6u7v8w9x0'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('consumo_material_cantidad_check', 'consumo_material', type_='check')
    op.create_check_constraint(
        'consumo_material_cantidad_check',
        'consumo_material',
        'cantidad >= 0',
    )


def downgrade():
    # Volver a > 0 exige que no existan pedidos abiertos (cantidad = 0).
    op.execute("DELETE FROM consumo_material WHERE cantidad = 0 AND estado = 'PENDIENTE'")
    op.drop_constraint('consumo_material_cantidad_check', 'consumo_material', type_='check')
    op.create_check_constraint(
        'consumo_material_cantidad_check',
        'consumo_material',
        'cantidad > 0',
    )
