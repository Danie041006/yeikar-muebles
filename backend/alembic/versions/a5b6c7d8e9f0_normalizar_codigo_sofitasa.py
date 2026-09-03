"""normalizar codigo de la cuenta Sofitasa + ampliar CHECK de metodo_pago

Revision ID: a5b6c7d8e9f0
Revises: f9a0b1c2d3e4
Create Date: 2026-09-01

El código de la cuenta Sofitasa era "BANCO SOFITASA" (con espacio),
inconsistente con los demás códigos (BANESCO, NEQUI, BINANCE...). Se usa
como `value` de los selectores de método de pago (pagos de venta mapean
metodo_pago → MetodoCaja.codigo), así que se normaliza a "SOFITASA".
Seguro: ningún pago histórico lo referencia (solo hay pagos EFECTIVO_COP);
las FKs a metodo_caja son por id.

Además, el CHECK pago_metodo_pago_check solo permitía 7 códigos: faltaban
NEQUI, SOFITASA y BANESCO (cuentas existentes que nunca se agregaron al
CHECK). Se amplía para que los selectores muestren las 10 cuentas reales.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

METODOS_VALIDOS = (
    "'EFECTIVO_COP','EFECTIVO_USD','EFECTIVO_VES','BANCOLOMBIA',"
    "'BANCARIBE','ZELLE','BINANCE','NEQUI','SOFITASA','BANESCO'"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text("UPDATE metodo_caja SET codigo = 'SOFITASA' WHERE codigo = 'BANCO SOFITASA'")
    )
    conn.execute(text("ALTER TABLE pago DROP CONSTRAINT pago_metodo_pago_check"))
    conn.execute(
        text(
            "ALTER TABLE pago ADD CONSTRAINT pago_metodo_pago_check CHECK "
            f"(metodo_pago IN ({METODOS_VALIDOS}))"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text("UPDATE metodo_caja SET codigo = 'BANCO SOFITASA' WHERE codigo = 'SOFITASA'")
    )
    conn.execute(text("ALTER TABLE pago DROP CONSTRAINT pago_metodo_pago_check"))
    conn.execute(
        text(
            "ALTER TABLE pago ADD CONSTRAINT pago_metodo_pago_check CHECK "
            "(metodo_pago IN ('EFECTIVO_COP','EFECTIVO_USD','EFECTIVO_VES',"
            "'BANCOLOMBIA','BANCARIBE','ZELLE','BINANCE'))"
        )
    )