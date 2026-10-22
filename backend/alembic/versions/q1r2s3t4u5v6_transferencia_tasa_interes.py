"""transferencias: tasa de conversión editable e interés opcional

Una transferencia entre cuentas de distinta moneda necesita la tasa REAL de la
operación (1 USD = 4.000 COP, no “200.000 dólares por 2.000.000 de pesos”).
Se guarda en la pata de salida como `tasa_conversion` (unidades de moneda
destino por 1 unidad de moneda origen).

También se agrega `interes` (en moneda destino, positivo suma y negativo
resta) para reflejar el interés de un tercero en la pata de entrada.

Revision ID: q1r2s3t4u5v6
Revises: p9q0r1s2t3u4
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "q1r2s3t4u5v6"
down_revision = "p9q0r1s2t3u4"
branch_labels = None
depends_on = None


def _existe_columna(conn, tabla: str, columna: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ),
            {"t": tabla, "c": columna},
        ).first()
    )


def upgrade() -> None:
    conn = op.get_bind()

    if not _existe_columna(conn, "movimiento_caja", "tasa_conversion"):
        op.add_column(
            "movimiento_caja",
            sa.Column("tasa_conversion", sa.Numeric(18, 6), nullable=True),
        )

    if not _existe_columna(conn, "movimiento_caja", "interes"):
        op.add_column(
            "movimiento_caja",
            sa.Column("interes", sa.Numeric(15, 2), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()

    if _existe_columna(conn, "movimiento_caja", "interes"):
        op.drop_column("movimiento_caja", "interes")

    if _existe_columna(conn, "movimiento_caja", "tasa_conversion"):
        op.drop_column("movimiento_caja", "tasa_conversion")
