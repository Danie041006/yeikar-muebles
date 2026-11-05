"""abonos a Por Pagar con descuento del proveedor

Permite pagar una deuda con un descuento porcentual (ej. 5% por ser
mayorista). El abono se aplica completo a la deuda, pero de la caja solo
sale el neto:

    deuda 1.000, descuento 5% (50)  →  caja 950, deuda 0

`pago_cuenta_por_pagar.monto` sigue siendo el dinero que sale de caja y
`descuento` guarda lo condonado. `cuenta_por_pagar.monto_descontado`
acumula esos descuentos para que el saldo cierre sin alterar `monto` ni
el gasto original (el costo del ítem no cambia).

Revision ID: p6a7b8c9d0e1
Revises: f2a3b4c5d6e7
Create Date: 2026-11-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p6a7b8c9d0e1"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pago_cuenta_por_pagar",
        sa.Column("descuento", sa.Numeric(15, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "pago_cuenta_por_pagar",
        sa.Column("descuento_porcentaje", sa.Numeric(7, 4), nullable=True),
    )
    op.add_column(
        "cuenta_por_pagar",
        sa.Column("monto_descontado", sa.Numeric(15, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("cuenta_por_pagar", "monto_descontado")
    op.drop_column("pago_cuenta_por_pagar", "descuento_porcentaje")
    op.drop_column("pago_cuenta_por_pagar", "descuento")
