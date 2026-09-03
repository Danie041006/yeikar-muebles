"""tipo_escala CORTE: ampliar el CHECK de producto_material

Revision ID: f6a7b8c9d0e3
Revises: i3j4k5l6m7n8
Create Date: 2026-08-31

El CHECK pm_tipo_escala_check (aplicado a mano en la BD temprano, sin
migración) solo admitía FIJO/LINEAL/AREA/ESPACIADO/POR_RANGO/FORMULA.
Se reemplaza por la versión que incluye CORTE (consumo por cortes de
materiales laminares con registro de sobrantes).
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f6a7b8c9d0e3'
down_revision: Union[str, None] = 'i3j4k5l6m7n8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECK_NUEVO = (
    "ALTER TABLE producto_material ADD CONSTRAINT pm_tipo_escala_check CHECK ("
    "tipo_escala::text = ANY (ARRAY['FIJO'::character varying, 'LINEAL'::character varying, "
    "'AREA'::character varying, 'ESPACIADO'::character varying, 'POR_RANGO'::character varying, "
    "'FORMULA'::character varying, 'CORTE'::character varying]::text[]))"
)


def upgrade() -> None:
    # IF EXISTS: en BDs donde el CHECK manual no exista, no debe fallar.
    op.execute("ALTER TABLE producto_material DROP CONSTRAINT IF EXISTS pm_tipo_escala_check")
    op.execute(CHECK_NUEVO)


def downgrade() -> None:
    # Solo puede revertirse si no hay filas CORTE.
    op.execute("ALTER TABLE producto_material DROP CONSTRAINT IF EXISTS pm_tipo_escala_check")
    op.execute(
        "ALTER TABLE producto_material ADD CONSTRAINT pm_tipo_escala_check CHECK ("
        "tipo_escala::text = ANY (ARRAY['FIJO'::character varying, 'LINEAL'::character varying, "
        "'AREA'::character varying, 'ESPACIADO'::character varying, 'POR_RANGO'::character varying, "
        "'FORMULA'::character varying]::text[]))"
    )
