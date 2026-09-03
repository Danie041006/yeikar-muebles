"""componente y consumo extra en consumos (estructura de costes desde producción)

Campos para alimentar la estructura de costes generada al finalizar la orden:
  - componente: pieza del mueble (CAMA, NOCHERO, CABECERA...) → secciones
    "SECCIÓN (COMPONENTE)" en la estructura.
  - es_excedente + motivo_exceso: material usado de más (daño/desperdicio) que
    cuenta en el costo real de la orden pero se excluye de la estructura.

Revision ID: j5k6l7m8n9o0
Revises: i3j4k5l6m7n8
Create Date: 2026-08-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j5k6l7m8n9o0'
down_revision = 'i3j4k5l6m7n8'
branch_labels = None
depends_on = None


def _add_columns(tabla: str) -> None:
    op.add_column(tabla, sa.Column('componente', sa.String(length=50), nullable=True))
    op.add_column(tabla, sa.Column('es_excedente', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column(tabla, sa.Column('motivo_exceso', sa.String(length=100), nullable=True))


def _drop_columns(tabla: str) -> None:
    op.drop_column(tabla, 'motivo_exceso')
    op.drop_column(tabla, 'es_excedente')
    op.drop_column(tabla, 'componente')


def upgrade():
    _add_columns('consumo_material')
    _add_columns('produccion_crudo_consumo')


def downgrade():
    _drop_columns('produccion_crudo_consumo')
    _drop_columns('consumo_material')