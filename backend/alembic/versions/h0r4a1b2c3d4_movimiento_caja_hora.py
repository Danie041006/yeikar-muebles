"""movimiento de caja: hora del movimiento para ordenar el libro

Agrega `movimiento_caja.hora` (opcional). El libro de caja ordena por
(fecha, hora NULLS LAST, id): las filas con hora se acomodan según la hora
real del papel y las que no la tienen conservan el orden de registro.

No cambia saldos: la hora solo posiciona la fila en el saldo corrido.
`NULL` = sin hora conocida (comportamiento anterior, orden por id).

Revision ID: h0r4a1b2c3d4
Revises: d1a2b3c4e5f9
Create Date: 2026-10-27
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "h0r4a1b2c3d4"
down_revision: Union[str, None] = "d1a2b3c4e5f9"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "movimiento_caja",
        sa.Column("hora", sa.Time(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("movimiento_caja", "hora")
