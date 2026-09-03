"""quitar email de cliente

Revision ID: a3b4c5d6e7f8
Revises: f0e1d2c3b4a5
Create Date: 2026-09-01

El correo electrónico no se usa en el flujo de clientes; se elimina la
columna para simplificar el alta y la ficha del cliente.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'm1n2o3p4q5r6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('cliente', 'email')


def downgrade() -> None:
    op.add_column('cliente', sa.Column('email', sa.String(120), nullable=True))