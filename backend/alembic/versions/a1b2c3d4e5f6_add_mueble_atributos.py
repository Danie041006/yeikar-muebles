"""
a1b2c3d4e5f6_add_mueble_atributos.py
=====================================
Migración: Tabla genérica mueble_atributos

Propósito:
  Añade la tabla `mueble_atributos` que reemplaza a `cama_historica_atributos`
  para soportar CUALQUIER tipo de mueble que fabrica YEIKAR.
  
  La tabla legacy `cama_historica_atributos` se mantiene para los 63 registros
  históricos de camas ya importados.

Revisión: a1b2c3d4e5f6
Revisión anterior: 530ad3bcdb72
"""

from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '530ad3bcdb72'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'mueble_atributos',
        sa.Column('id', sa.BigInteger(), primary_key=True, index=True),
        sa.Column('producto_id', sa.BigInteger(),
                  sa.ForeignKey('producto.id', ondelete='CASCADE'),
                  unique=True, nullable=False),
        sa.Column('tipo_mueble', sa.String(50), nullable=False, index=True),
        sa.Column('familia_probable', sa.String(50), nullable=True),
        sa.Column('estilo_general', sa.String(50), nullable=True),
        sa.Column('tipo_patas', sa.String(50), nullable=True),
        sa.Column('tiene_tapiceria', sa.Boolean(), nullable=False, default=False),
        sa.Column('tiene_luces', sa.Boolean(), nullable=False, default=False),
        sa.Column('atributos_extra', sa.JSON(), nullable=True),
        sa.Column('vector_similitud', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('mueble_atributos')
