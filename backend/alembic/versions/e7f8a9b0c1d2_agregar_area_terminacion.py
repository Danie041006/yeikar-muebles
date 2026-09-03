"""agregar área Terminación al taller

Revision ID: e7f8a9b0c1d2
Revises: c9e8f7a6b5d4
Create Date: 2026-08-31

Faltaba el área "Terminación" en el kanban de producción. El orden del
taller es: EBANISTERÍA → PREPARACIÓN → PINTURA → TAPICERÍA → VIDRIERÍA →
TERMINACIÓN.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "c9e8f7a6b5d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existe = conn.execute(text("SELECT 1 FROM area WHERE nombre = 'Terminación'")).first()
    if not existe:
        conn.execute(text("INSERT INTO area (nombre) VALUES ('Terminación')"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM area WHERE nombre = 'Terminación'"))