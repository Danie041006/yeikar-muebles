"""add moneda_id to metodo_caja + set Binance to USD

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    has_col = conn.execute(
        sa.text("SELECT 1 FROM information_schema.columns WHERE table_name = 'metodo_caja' AND column_name = 'moneda_id'")
    ).fetchone()

    if not has_col:
        op.add_column(
            "metodo_caja",
            sa.Column("moneda_id", sa.BigInteger(), sa.ForeignKey("moneda.id", ondelete="SET NULL"), nullable=True),
        )

    conn.execute(sa.text("UPDATE metodo_caja SET moneda_id = 1 WHERE codigo IN ('EFECTIVO_COP', 'BANCOLOMBIA', 'NEQUI', 'BANCO SOFITASA', 'BANESCO') AND (moneda_id IS NULL OR moneda_id != 1)"))
    conn.execute(sa.text("UPDATE metodo_caja SET moneda_id = 2 WHERE codigo IN ('EFECTIVO_USD', 'ZELLE', 'BINANCE') AND (moneda_id IS NULL OR moneda_id != 2)"))
    conn.execute(sa.text("UPDATE metodo_caja SET moneda_id = 3 WHERE codigo IN ('EFECTIVO_VES', 'BANCARIBE') AND (moneda_id IS NULL OR moneda_id != 3)"))

    conn.execute(sa.text("""
        UPDATE movimiento_caja mc
        SET
            moneda_id = 2,
            monto = ROUND(mc.monto / 4200.0, 2),
            monto_en_moneda_base = ROUND(mc.monto / 4200.0, 2),
            tasa_cambio = 4200.0
        FROM metodo_caja mcj
        WHERE mc.metodo_caja_id = mcj.id
          AND mcj.codigo = 'BINANCE'
          AND mc.moneda_id = 1
    """))


def downgrade() -> None:
    op.execute("""
        UPDATE movimiento_caja mc
        SET
            moneda_id = 1,
            monto = ROUND(mc.monto * 4200.0, 2),
            monto_en_moneda_base = ROUND(mc.monto * 4200.0, 2),
            tasa_cambio = 1.0
        FROM metodo_caja mcj
        WHERE mc.metodo_caja_id = mcj.id
          AND mcj.codigo = 'BINANCE'
          AND mc.moneda_id = 2
    """)
    op.drop_column("metodo_caja", "moneda_id")
