"""gastos: clasificación del egreso (G D/C/P/F/I).

El libro de caja del negocio marca cada gasto con un código de dos letras:
  G D = Gasto Deducible    G C = Gasto de Casa
  G P = Gasto Personal     G F = Gasto Familiar
  G I = Gasto de Inversión

Es una dimensión distinta de `tipo_gasto.categoria` (OPERATIVO/PASIVO/
PRODUCCION): el tipo dice QUÉ se pagó y la clasificación dice A QUÉ DESTINO
iba el dinero. Se guarda por fila para poder sumar/filtrar el mes. Es
OPCIONAL: los gastos que no vengan del libro pueden quedar sin clasificar.

Revision ID: k3l4m5n6o7p8
Revises: f3a1b2c4d5e6
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "k3l4m5n6o7p8"
down_revision = "f3a1b2c4d5e6"
branch_labels = None
depends_on = None


def _existe_columna(conn, tabla: str, columna: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ),
            {"t": tabla, "c": columna},
        ).first()
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _existe_columna(conn, "gasto", "clasificacion"):
        op.add_column(
            "gasto",
            sa.Column("clasificacion", sa.String(length=30), nullable=True),
        )
        op.create_index(
            "ix_gasto_clasificacion", "gasto", ["clasificacion"], unique=False
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _existe_columna(conn, "gasto", "clasificacion"):
        op.drop_index("ix_gasto_clasificacion", table_name="gasto")
        op.drop_column("gasto", "clasificacion")
