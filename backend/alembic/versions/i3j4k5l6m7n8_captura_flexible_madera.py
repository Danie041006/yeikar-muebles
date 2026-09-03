"""captura flexible de madera: unidad_captura + medidas de pieza, unidad m³

Nuevas columnas de trazabilidad en consumo_material y produccion_crudo_consumo:
`cantidad` pasa a guardar SIEMPRE la unidad base del material (m o m³) y estos
campos conservan cómo se digitó (cm/mts o pieza L×A×E con la fórmula de la
casa ÷1000). Además se agrega la unidad "Metro cúbico (m³)" al catálogo para
madera volumétrica.

Revision ID: i3j4k5l6m7n8
Revises: db8c237afb75
Create Date: 2026-08-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i3j4k5l6m7n8'
down_revision = 'db8c237afb75'
branch_labels = None
depends_on = None


def _add_captura_columns(tabla: str) -> None:
    op.add_column(tabla, sa.Column('unidad_captura', sa.String(length=5), nullable=True))
    op.add_column(tabla, sa.Column('pieza_largo', sa.Numeric(10, 2), nullable=True))
    op.add_column(tabla, sa.Column('pieza_ancho', sa.Numeric(10, 2), nullable=True))
    op.add_column(tabla, sa.Column('pieza_espesor', sa.Numeric(10, 2), nullable=True))


def _drop_captura_columns(tabla: str) -> None:
    op.drop_column(tabla, 'pieza_espesor')
    op.drop_column(tabla, 'pieza_ancho')
    op.drop_column(tabla, 'pieza_largo')
    op.drop_column(tabla, 'unidad_captura')


def upgrade():
    _add_captura_columns('consumo_material')
    _add_captura_columns('produccion_crudo_consumo')

    # Unidad para madera volumétrica. Idempotente: no se duplica si ya existe.
    op.execute(sa.text(
        "INSERT INTO unidad_medida (nombre, abreviatura) "
        "SELECT 'Metro cúbico', 'm³' "
        "WHERE NOT EXISTS (SELECT 1 FROM unidad_medida WHERE abreviatura = 'm³')"
    ))


def downgrade():
    # La unidad m³ se conserva en el downgrade: borrarla podría romper FKs de
    # materiales que ya la usen.
    _drop_captura_columns('produccion_crudo_consumo')
    _drop_captura_columns('consumo_material')
