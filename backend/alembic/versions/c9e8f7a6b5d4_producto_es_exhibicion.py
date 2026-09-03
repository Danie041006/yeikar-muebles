"""producto.es_exhibicion: flag de pieza de exhibición

Revision ID: c9e8f7a6b5d4
Revises: b3c7d9e1f5a2
Create Date: 2026-08-31

Marca las piezas de exhibición: se fabrican una vez, viven en el stock del
showroom y su venta descuenta stock al facturar (como reventa), sin entrar a
producción desde un pedido.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e8f7a6b5d4"
down_revision: Union[str, None] = "c4d8e0f2a6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("producto", sa.Column("es_exhibicion", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_producto_es_exhibicion", "producto", ["es_exhibicion"])


def downgrade() -> None:
    op.drop_index("ix_producto_es_exhibicion", table_name="producto")
    op.drop_column("producto", "es_exhibicion")
