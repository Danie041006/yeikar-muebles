"""allow EFECTIVO_VES in pago metodo_pago check constraint

Revision ID: c3f4a5b6c7d8
Revises: b1a2c3d4e5f6
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3f4a5b6c7d8"
down_revision: Union[str, None] = "b1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE pago DROP CONSTRAINT pago_metodo_pago_check")
    op.execute(
        "ALTER TABLE pago ADD CONSTRAINT pago_metodo_pago_check CHECK "
        "(metodo_pago IN ('EFECTIVO_COP','EFECTIVO_USD','EFECTIVO_VES',"
        "'BANCOLOMBIA','BANCARIBE','ZELLE'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pago DROP CONSTRAINT pago_metodo_pago_check")
    op.execute(
        "ALTER TABLE pago ADD CONSTRAINT pago_metodo_pago_check CHECK "
        "(metodo_pago IN ('EFECTIVO_COP','EFECTIVO_USD',"
        "'BANCOLOMBIA','BANCARIBE','ZELLE'))"
    )
