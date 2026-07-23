"""add_seccion_and_regla_gasto

Revision ID: c1f2e3d4e5f7
Revises: b517c8d4c05d
Create Date: 2026-07-23

Agrega la columna 'seccion' a producto_material y crea la tabla 'regla_gasto_seccion'
para controlar los recargos porcentuales por sección del mueble (EBANISTERIA, TENDIDO, etc.).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c1f2e3d4e5f7'
down_revision: Union[str, None] = 'b517c8d4c05d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Agregar columna seccion en producto_material con default 'EBANISTERIA'
    op.add_column(
        'producto_material',
        sa.Column('seccion', sa.String(30), nullable=False, server_default='EBANISTERIA')
    )

    # 2. Crear tabla regla_gasto_seccion
    op.create_table(
        'regla_gasto_seccion',
        sa.Column('id', sa.BigInteger(), primary_key=True, index=True),
        sa.Column('seccion', sa.String(30), unique=True, nullable=False),
        sa.Column('porcentaje_gasto', sa.Numeric(5, 2), nullable=False)
    )

    # 3. Poblar datos iniciales confirmados por las 68 hojas
    regla_gasto_table = sa.table(
        'regla_gasto_seccion',
        sa.column('seccion', sa.String),
        sa.column('porcentaje_gasto', sa.Numeric)
    )
    op.bulk_insert(
        regla_gasto_table,
        [
            {'seccion': 'EBANISTERIA', 'porcentaje_gasto': 10.00},
            {'seccion': 'TENDIDO', 'porcentaje_gasto': 10.00},
            {'seccion': 'COLA_DE_PATO', 'porcentaje_gasto': 10.00},
            {'seccion': 'PINTURA', 'porcentaje_gasto': 10.00},
            {'seccion': 'NOCHEROS', 'porcentaje_gasto': 5.00},
            {'seccion': 'TAPICERIA', 'porcentaje_gasto': 0.00},
            {'seccion': 'TERMINACION', 'porcentaje_gasto': 0.00},
        ]
    )


def downgrade() -> None:
    op.drop_table('regla_gasto_seccion')
    op.drop_column('producto_material', 'seccion')
