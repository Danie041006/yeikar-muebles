"""tipo_producto y categoria_inventario PLÁSTICOS

Revision ID: c2d3e4f5a6b7
Revises: d68c00cfa34e
Create Date: 2026-10-02

Los productos de plástico se compran y revenden (misma mecánica que REVENTA:
es_reventa=True), pero llevan pestaña, tipo de producto y categoría de
inventario propios para no mezclarse con colchones/electrodomésticos.
Solo datos: el catálogo se carga en los selectores automáticamente.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'd68c00cfa34e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOMBRE = "PLÁSTICOS"


def _tipo_id(conn):
    return conn.execute(
        text("SELECT id FROM tipo_producto WHERE nombre = :n"), {"n": NOMBRE}
    ).first()


def _categoria_id(conn):
    return conn.execute(
        text("SELECT id FROM categoria_inventario WHERE nombre = :n AND tipo = 'PRODUCTO'"),
        {"n": NOMBRE},
    ).first()


def upgrade() -> None:
    conn = op.get_bind()

    if not _tipo_id(conn):
        conn.execute(
            text("INSERT INTO tipo_producto (nombre) VALUES (:n)"), {"n": NOMBRE}
        )

    if not _categoria_id(conn):
        conn.execute(
            text(
                "INSERT INTO categoria_inventario (nombre, tipo, orden, activo) "
                "VALUES (:n, 'PRODUCTO', 20, true)"
            ),
            {"n": NOMBRE},
        )


def downgrade() -> None:
    conn = op.get_bind()

    tipo = _tipo_id(conn)
    if tipo:
        en_uso = conn.execute(
            text("SELECT 1 FROM producto WHERE tipo_producto_id = :i LIMIT 1"),
            {"i": tipo[0]},
        ).first()
        if not en_uso:
            conn.execute(text("DELETE FROM tipo_producto WHERE id = :i"), {"i": tipo[0]})

    cat = _categoria_id(conn)
    if cat:
        en_uso = conn.execute(
            text("SELECT 1 FROM producto WHERE categoria_inventario_id = :i LIMIT 1"),
            {"i": cat[0]},
        ).first()
        if not en_uso:
            conn.execute(
                text("DELETE FROM categoria_inventario WHERE id = :i"), {"i": cat[0]}
            )
