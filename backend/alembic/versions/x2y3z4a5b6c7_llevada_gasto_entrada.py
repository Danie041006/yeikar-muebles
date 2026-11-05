"""movimiento_inventario: vínculo al gasto del flete/llevada.

La entrada pagada con flete/aduana crea un Gasto aparte ("FLETE / LLEVADA DE
INSUMO") y una salida de caja adicional. Antes no se guardaba el vínculo, así
que editar o anular la entrada no podía saber cuál gasto era el flete. Esta
columna lo deja explícito (las entradas históricas con flete se resuelven por
descripción/fecha/monto o se bloquean si hay ambigüedad).

Revision ID: x2y3z4a5b6c7
Revises: w1x2y3z4a5b6
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = "x2y3z4a5b6c7"
down_revision = "w1x2y3z4a5b6"
branch_labels = None
depends_on = None

FK_NAME = "fk_movimiento_inventario_llevada_gasto"


def _tiene_columna(conn, tabla: str, columna: str) -> bool:
    fila = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
        ),
        {"t": tabla, "c": columna},
    ).first()
    return fila is not None


def _tiene_fk(conn, tabla: str, nombre: str) -> bool:
    fila = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema='public' AND table_name=:t "
            "AND constraint_name=:n AND constraint_type='FOREIGN KEY'"
        ),
        {"t": tabla, "n": nombre},
    ).first()
    return fila is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _tiene_columna(conn, "movimiento_inventario", "llevada_gasto_id"):
        op.add_column(
            "movimiento_inventario",
            sa.Column("llevada_gasto_id", sa.BigInteger(), nullable=True),
        )
    if not _tiene_fk(conn, "movimiento_inventario", FK_NAME):
        op.create_foreign_key(
            FK_NAME,
            "movimiento_inventario",
            "gasto",
            ["llevada_gasto_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _tiene_fk(conn, "movimiento_inventario", FK_NAME):
        op.drop_constraint(FK_NAME, "movimiento_inventario", type_="foreignkey")
    if _tiene_columna(conn, "movimiento_inventario", "llevada_gasto_id"):
        op.drop_column("movimiento_inventario", "llevada_gasto_id")
