"""saldo inicial por defecto: 1M en todas las cuentas sin movimientos

Revision ID: e2d4c6a8b1f3
Revises: d5f2a1c9e8b7
Create Date: 2026-08-13

Cada cuenta sin movimientos abre con un APERTURA de 1.000.000 COP
(las que ya tienen movimientos no se tocan para no inflar saldos reales).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2d4c6a8b1f3"
down_revision: Union[str, None] = "d5f2a1c9e8b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO movimiento_caja "
            "(metodo_caja_id, usuario_id, pago_id, fecha, tipo, monto, moneda_id, "
            " tasa_cambio, monto_en_moneda_base, referencia, observaciones) "
            "SELECT mc.id, NULL, NULL, CURRENT_DATE, 'APERTURA', 1000000.00, 1, 1.0, "
            "       1000000.00, 'Saldo inicial por defecto', "
            "       'Apertura por defecto: 1.000.000 COP' "
            "FROM metodo_caja mc "
            "WHERE mc.activo "
            "AND NOT EXISTS (SELECT 1 FROM movimiento_caja mv WHERE mv.metodo_caja_id = mc.id)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM movimiento_caja "
            "WHERE tipo = 'APERTURA' AND referencia = 'Saldo inicial por defecto'"
        )
    )
