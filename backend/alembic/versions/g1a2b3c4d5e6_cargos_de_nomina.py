"""cargos de nómina: cargos por categoría (EBANISTA, TAPICERO, etc.)

Revision ID: g1a2b3c4d5e6
Revises: b7c8d9e0f1a2
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "g1a2b3c4d5e6"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    for nombre in ("EBANISTA", "TAPICERO", "PINTOR", "PREPARADOR", "VIGILANTE", "SECRETARIA", "CHOFER"):
        existe = conn.execute(
            text("SELECT 1 FROM cargo WHERE nombre = :n"), {"n": nombre}
        ).first()
        if not existe:
            conn.execute(text("INSERT INTO cargo (nombre) VALUES (:n)"), {"n": nombre})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM cargo WHERE nombre IN ('EBANISTA','TAPICERO','PINTOR','PREPARADOR','VIGILANTE','SECRETARIA','CHOFER')")
    )
