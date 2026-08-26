"""producto: moneda de los precios de referencia

Agrega `moneda_id` a `producto` para que los precios de referencia
(precio_costo_base / precio_venta_base) declaren explícitamente en qué moneda
están. La moneda base del ERP es COP (id=1): los productos fabricados siguen
en COP por defecto; los productos de REVENTA (colchones, neveras...) se
compran en USD y ahora pueden declararlo.

La conversión a la moneda base NO se congela aquí: el precio es una referencia
y se convierte con la tasa vigente en el momento de usarse (ventas, IQE),
usando tasas_cambio.obtener_tasa_moneda_a_cop.

Revision ID: f6a7b8c9d0e1
Revises: ccb2fff0b1ed
Create Date: 2026-08-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'ccb2fff0b1ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Default 1 (COP): todos los productos existentes eran interpretados como
    # COP por el motor de costos; se conserva ese comportamiento.
    op.add_column(
        'producto',
        sa.Column('moneda_id', sa.BigInteger(), nullable=True, server_default='1'),
    )
    op.create_foreign_key(
        'fk_producto_moneda', 'producto', 'moneda', ['moneda_id'], ['id'],
        ondelete='RESTRICT',
    )


def downgrade() -> None:
    op.drop_constraint('fk_producto_moneda', 'producto', type_='foreignkey')
    op.drop_column('producto', 'moneda_id')
