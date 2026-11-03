"""producto.es_colchon: marca para la pregunta del plástico de regalo

Agrega el flag `es_colchon` a producto y hace backfill de los colchones que
ya existían en la promo vieja (`promocion_obsequio.colchon_id`) más los que
tienen "COLCHÓN" en el nombre. La promo automática deja de usarse: ahora el
plástico es un regalo manual, máximo 1 por colchón.

Revision ID: b2c3d4e5f6a7
Revises: q7r8s9t0u1v2
Create Date: 2026-11-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "producto",
        sa.Column(
            "es_colchon",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_producto_es_colchon", "producto", ["es_colchon"])

    # Backfill: los 8 colchones mapeados en la promo vieja + los 8 que tienen
    # "COLCHÓN" en el nombre (hoy son 16 en total; el UNION evita duplicados).
    op.execute(
        """
        UPDATE producto
        SET es_colchon = true
        WHERE id IN (
            SELECT colchon_id FROM promocion_obsequio
            UNION
            SELECT id FROM producto
            WHERE nombre ILIKE '%COLCHON%' OR nombre ILIKE '%COLCHÓN%'
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_producto_es_colchon", table_name="producto")
    op.drop_column("producto", "es_colchon")
