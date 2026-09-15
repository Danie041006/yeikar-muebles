"""pedido de material: cantidad_pedida en consumo_material (pidieron vs usaron)

Revision ID: q3r4s5t6u7v8
Revises: p2q3r4s5t6u7
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'q3r4s5t6u7v8'
down_revision = 'p2q3r4s5t6u7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('consumo_material', sa.Column('cantidad_pedida', sa.Numeric(12, 2), nullable=True))


def downgrade():
    op.drop_column('consumo_material', 'cantidad_pedida')
