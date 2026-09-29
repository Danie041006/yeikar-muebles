"""costo del crudo en el pedido: snapshot en produccion_crudo_uso + costo_crudo

Revision ID: c1d2e3f4a5b6
Revises: w9x0y1z2a3b4c
Create Date: 2026-09-28

El crudo asignado a un detalle de pedido ahora traslada su costo real al mueble:
- `produccion_crudo_uso.costo_unitario` / `costo_total`: costo CONGELADO al
  asignar (materiales + mano de obra del crudo), para que el costo del pedido
  y la estructura del producto lo incluyan una sola vez.
- `produccion_crudo_uso.seccion`: sección (del área del crudo) a la que se
  imputa el costo.
- `costo_produccion.costo_crudo`: columna propia del costo del crudo en la
  orden (no se mezcla con `costo_material`).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'w9x0y1z2a3b4c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'produccion_crudo_uso',
        sa.Column('costo_unitario', sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        'produccion_crudo_uso',
        sa.Column('costo_total', sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        'produccion_crudo_uso',
        sa.Column('seccion', sa.String(length=50), nullable=True),
    )
    op.add_column(
        'costo_produccion',
        sa.Column('costo_crudo', sa.Numeric(15, 2), nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_column('costo_produccion', 'costo_crudo')
    op.drop_column('produccion_crudo_uso', 'seccion')
    op.drop_column('produccion_crudo_uso', 'costo_total')
    op.drop_column('produccion_crudo_uso', 'costo_unitario')
