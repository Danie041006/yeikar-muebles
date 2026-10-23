"""pago_correccion: historial de correcciones del monto de un abono

Revision ID: pc1o2r3r4e5c
Revises: r3s4t5u6v7w8
Create Date: 2026-10-23

Cada vez que se corrige el monto de un cobro se guarda aquí el antes/después
(en la moneda del pago y en la moneda de la venta), quién lo corrigió y por
qué. La cotización ignora esta tabla; la trazabilidad se muestra en Ventas y
Cobros y en la auditoría del sistema.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'pc1o2r3r4e5c'
down_revision = 'r3s4t5u6v7w8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pago_correccion',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column(
            'pago_id',
            sa.BigInteger(),
            sa.ForeignKey('pago.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'usuario_id',
            sa.BigInteger(),
            sa.ForeignKey('usuario.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('monto_anterior', sa.Numeric(15, 2), nullable=False),
        sa.Column('monto_nuevo', sa.Numeric(15, 2), nullable=False),
        sa.Column('monto_base_anterior', sa.Numeric(15, 2), nullable=False),
        sa.Column('monto_base_nuevo', sa.Numeric(15, 2), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_pago_correccion_id', 'pago_correccion', ['id'])
    op.create_index('ix_pago_correccion_pago_id', 'pago_correccion', ['pago_id'])
    op.create_index('ix_pago_correccion_usuario_id', 'pago_correccion', ['usuario_id'])


def downgrade():
    op.drop_index('ix_pago_correccion_usuario_id', table_name='pago_correccion')
    op.drop_index('ix_pago_correccion_pago_id', table_name='pago_correccion')
    op.drop_index('ix_pago_correccion_id', table_name='pago_correccion')
    op.drop_table('pago_correccion')
