"""add BINANCE payment method (USD) + update CHECK constraint

Revision ID: d4e5f6a7b8c9
Revises: 8b6c7d8e9f01, e5f6a7b8c9d0, c3f4a5b6c7d8, h2i3j4k5l6m7
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = ("8b6c7d8e9f01", "e5f6a7b8c9d0", "c3f4a5b6c7d8", "h2i3j4k5l6m7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT 1 FROM metodo_caja WHERE codigo = 'BINANCE'")
    ).fetchone()
    if not exists:
        op.bulk_insert(
            sa.table(
                "metodo_caja",
                sa.column("id", sa.BigInteger()),
                sa.column("nombre", sa.String(100)),
                sa.column("codigo", sa.String(50)),
                sa.column("activo", sa.Boolean()),
                sa.column("orden", sa.Integer()),
            ),
            [
                {"id": 9, "nombre": "Binance", "codigo": "BINANCE", "activo": True, "orden": 7},
            ],
        )

    has_binance = conn.execute(
        sa.text("SELECT 1 FROM pg_constraint WHERE conrelid = 'pago'::regclass AND contype = 'c' AND pg_get_constraintdef(oid) LIKE '%BINANCE%'")
    ).fetchone()
    if not has_binance:
        op.execute("ALTER TABLE pago DROP CONSTRAINT pago_metodo_pago_check")
        op.execute(
            "ALTER TABLE pago ADD CONSTRAINT pago_metodo_pago_check CHECK "
            "(metodo_pago IN ('EFECTIVO_COP','EFECTIVO_USD','EFECTIVO_VES',"
            "'BANCOLOMBIA','BANCARIBE','ZELLE','BINANCE'))"
        )


def downgrade() -> None:
    op.execute("ALTER TABLE pago DROP CONSTRAINT pago_metodo_pago_check")
    op.execute(
        "ALTER TABLE pago ADD CONSTRAINT pago_metodo_pago_check CHECK "
        "(metodo_pago IN ('EFECTIVO_COP','EFECTIVO_USD','EFECTIVO_VES',"
        "'BANCOLOMBIA','BANCARIBE','ZELLE'))"
    )
    op.execute("DELETE FROM metodo_caja WHERE codigo = 'BINANCE'")
