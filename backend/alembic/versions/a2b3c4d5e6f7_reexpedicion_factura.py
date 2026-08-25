"""facturacion: permitir re-expedir una factura tras anular la anterior.

Se elimina la restricción UNIQUE de factura.pedido_id: cuando una factura se
anula, el pedido puede volver a facturarse (corrección) conservando la
anulada en el historial.

Revision ID: a2b3c4d5e6f7
Revises: f3a4b5c6d7e8
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('uq_factura_pedido_id', 'factura', type_='unique')


def downgrade() -> None:
    # OJO: si existen facturas duplicadas del mismo pedido (emitida + anulada),
    # el restore fallará. Se deja constancia: limpiar anuladas antes de revertir.
    op.create_unique_constraint('uq_factura_pedido_id', 'factura', ['pedido_id'])
