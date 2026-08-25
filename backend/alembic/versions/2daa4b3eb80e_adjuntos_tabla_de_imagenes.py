"""adjuntos tabla de imagenes

Revision ID: 2daa4b3eb80e
Revises: h2i3j4k5l6m7
Create Date: 2026-08-21 13:21:55.852934

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2daa4b3eb80e'
down_revision: Union[str, None] = 'h2i3j4k5l6m7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'adjunto',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('entidad_tipo', sa.String(length=30), nullable=False),
        sa.Column('entidad_id', sa.BigInteger(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('nombre_original', sa.String(length=255), nullable=True),
        sa.Column('mime', sa.String(length=100), nullable=False),
        sa.Column('tamano', sa.BigInteger(), nullable=False),
        sa.Column('archivo', sa.LargeBinary(), nullable=False),
        sa.Column('creado_por_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuario.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('uuid'),
    )
    op.create_index('ix_adjunto_entidad', 'adjunto', ['entidad_tipo', 'entidad_id'], unique=False)
    op.create_index(op.f('ix_adjunto_creado_por_id'), 'adjunto', ['creado_por_id'], unique=False)
    op.create_index(op.f('ix_adjunto_id'), 'adjunto', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_adjunto_id'), table_name='adjunto')
    op.drop_index(op.f('ix_adjunto_creado_por_id'), table_name='adjunto')
    op.drop_index('ix_adjunto_entidad', table_name='adjunto')
    op.drop_table('adjunto')
