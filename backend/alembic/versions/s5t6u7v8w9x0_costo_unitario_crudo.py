"""costo_unitario en crudo: importar lo ya hecho con stock + costo base del egreso

Revision ID: s5t6u7v8w9x0
Revises: r4s5t6u7v8w9
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 's5t6u7v8w9x0'
down_revision = 'r4s5t6u7v8w9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'producto_crudo_inventario',
        sa.Column('costo_unitario', sa.Numeric(15, 2), nullable=True),
    )


def downgrade():
    op.drop_column('producto_crudo_inventario', 'costo_unitario')
