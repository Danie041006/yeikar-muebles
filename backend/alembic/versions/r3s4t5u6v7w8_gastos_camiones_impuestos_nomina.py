"""tipos de gasto: camiones, impuestos y nómina

El dueño pidió tres motivos nuevos en el catálogo de TipoGasto para no
tener que escribirlos a mano cada vez:

  - GASTOS DE CAMIONES  → OPERATIVO
  - GASTOS DE IMPUESTOS → IMPUESTO
  - GASTOS EN NÓMINA    → OPERATIVO

Son tipos del catálogo, no categorías nuevas: así siguen entrando en los
totales del informe mensual (operativos / impuestos) sin tocar los reportes.

Revision ID: r3s4t5u6v7w8
Revises: q1r2s3t4u5v6
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa


revision = "r3s4t5u6v7w8"
down_revision = "q1r2s3t4u5v6"
branch_labels = None
depends_on = None


_TIPOS = [
    ("GASTOS DE CAMIONES", "OPERATIVO"),
    ("GASTOS DE IMPUESTOS", "IMPUESTO"),
    ("GASTOS EN NÓMINA", "OPERATIVO"),
]


def upgrade() -> None:
    for nombre, categoria in _TIPOS:
        op.execute(
            sa.text(
                "INSERT INTO tipo_gasto (nombre, categoria) "
                "VALUES (:nombre, :categoria) "
                "ON CONFLICT (nombre) DO NOTHING"
            ).bindparams(nombre=nombre, categoria=categoria)
        )


def downgrade() -> None:
    for nombre, _ in _TIPOS:
        op.execute(
            sa.text("DELETE FROM tipo_gasto WHERE nombre = :nombre").bindparams(
                nombre=nombre
            )
        )
