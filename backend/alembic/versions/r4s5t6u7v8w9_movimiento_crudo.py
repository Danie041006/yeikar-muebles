"""movimiento_crudo: kardex de ítems en crudo (misma UI de movimientos)

Revision ID: r4s5t6u7v8w9
Revises: q3r4s5t6u7v8
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'r4s5t6u7v8w9'
down_revision = 'q3r4s5t6u7v8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'movimiento_crudo',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('crudo_id', sa.BigInteger(), sa.ForeignKey('producto_crudo_inventario.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('tipo', sa.String(50), nullable=False),
        sa.Column('cantidad', sa.Numeric(12, 2), nullable=False),
        sa.Column('referencia_tipo', sa.String(100), nullable=True),
        sa.Column('referencia_id', sa.BigInteger(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('creado_por_id', sa.BigInteger(), sa.ForeignKey('usuario.id', ondelete='SET NULL'), nullable=True),
        sa.Column('fecha', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_movimiento_crudo_id', 'movimiento_crudo', ['id'])
    op.create_index('ix_movimiento_crudo_crudo_id', 'movimiento_crudo', ['crudo_id'])
    op.create_index('ix_movimiento_crudo_creado_por_id', 'movimiento_crudo', ['creado_por_id'])


def downgrade():
    op.drop_index('ix_movimiento_crudo_creado_por_id', table_name='movimiento_crudo')
    op.drop_index('ix_movimiento_crudo_crudo_id', table_name='movimiento_crudo')
    op.drop_index('ix_movimiento_crudo_id', table_name='movimiento_crudo')
    op.drop_table('movimiento_crudo')
