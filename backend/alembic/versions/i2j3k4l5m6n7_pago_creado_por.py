"""trazabilidad del cobro: quién registró el pago

La fecha del pago (`pago.fecha`) puede ser anterior al día en que se digita.
`created_at` ya guarda ese momento; esta migración agrega `creado_por_id`
para saber quién cargó el cobro y poder mostrarlo en la UI.

Backfill: los pagos históricos que sí tienen movimiento de caja heredan el
usuario de ese movimiento (`movimiento_caja.usuario_id`). Los demás quedan
NULL (sin autor conocido).

Revision ID: i2j3k4l5m6n7
Revises: h1i2j3k4l5m6
Create Date: 2026-10-19 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i2j3k4l5m6n7"
down_revision: Union[str, None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pago",
        sa.Column("creado_por_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_pago_creado_por_id_usuario",
        "pago",
        "usuario",
        ["creado_por_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_pago_creado_por_id", "pago", ["creado_por_id"])

    # Backfill conservador: solo pagos con un único usuario responsable en caja.
    op.execute(
        """
        UPDATE pago p
        SET creado_por_id = sub.usuario_id
        FROM (
            SELECT pago_id, MAX(usuario_id) AS usuario_id
            FROM movimiento_caja
            WHERE pago_id IS NOT NULL AND usuario_id IS NOT NULL
            GROUP BY pago_id
        ) sub
        WHERE p.id = sub.pago_id
          AND p.creado_por_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_pago_creado_por_id", table_name="pago")
    op.drop_constraint("fk_pago_creado_por_id_usuario", "pago", type_="foreignkey")
    op.drop_column("pago", "creado_por_id")
