"""check constraints detalle_cotizacion

Revision ID: cee7ebd51154
Revises: f346bfe982db
Create Date: 2026-08-12

Defensa en profundidad: valida en BD las cantidades/precios/dimensiones de
detalle_cotizacion (igual que detalle_pedido). La validación Pydantic ya
existe; estos CHECKs evitan datos corruptos si algo la elude.
"""
from alembic import op

revision = 'cee7ebd51154'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        'detalle_cotizacion_cantidad_check',
        'detalle_cotizacion',
        'cantidad > 0',
    )
    op.create_check_constraint(
        'detalle_cotizacion_precio_check',
        'detalle_cotizacion',
        'precio >= 0',
    )
    op.create_check_constraint(
        'detalle_cotizacion_dimensiones_check',
        'detalle_cotizacion',
        '(ancho IS NULL OR ancho >= 0) AND (largo IS NULL OR largo >= 0) AND (alto IS NULL OR alto >= 0)',
    )
    op.create_check_constraint(
        'detalle_cotizacion_costos_check',
        'detalle_cotizacion',
        '(costo_materiales IS NULL OR costo_materiales >= 0) AND (costo_mano_obra IS NULL OR costo_mano_obra >= 0) AND (costo_gastos IS NULL OR costo_gastos >= 0) AND (costo_total IS NULL OR costo_total >= 0)',
    )


def downgrade():
    for nombre in (
        'detalle_cotizacion_cantidad_check',
        'detalle_cotizacion_precio_check',
        'detalle_cotizacion_dimensiones_check',
        'detalle_cotizacion_costos_check',
    ):
        op.drop_constraint(nombre, 'detalle_cotizacion', type_='check')
