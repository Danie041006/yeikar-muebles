"""tipos de producto para mueblería (fabricados específicos)

Revision ID: e1f2a3b4c5d6
Revises: a5b6c7d8e9f0
Create Date: 2026-09-01

Amplía el catálogo de tipos de los FABRICADOS: hasta ahora todo lo que no es
Cama caía en "Fabricado" genérico. Se agregan los 7 tipos principales de una
mueblería. Son solo datos: el cotizador, IQE y Productos los cargan del
catálogo y aparecen automáticamente.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NUEVOS_TIPOS = [
    "Nochero / Gavetero",
    "Comedor",
    "Closet / Armario",
    "Modular / Barra",
    "Peinador / Espejo",
    "Mesa",
    "Mueble TV / Escritorio",
]


def _existe_tipo(conn, nombre: str):
    return conn.execute(text("SELECT id FROM tipo_producto WHERE nombre = :n"), {"n": nombre}).first()


def upgrade() -> None:
    conn = op.get_bind()
    for nombre in NUEVOS_TIPOS:
        if not _existe_tipo(conn, nombre):
            conn.execute(text("INSERT INTO tipo_producto (nombre) VALUES (:n)"), {"n": nombre})


def downgrade() -> None:
    conn = op.get_bind()
    for nombre in NUEVOS_TIPOS:
        fila = _existe_tipo(conn, nombre)
        if fila:
            en_uso = conn.execute(
                text("SELECT 1 FROM producto WHERE tipo_producto_id = :i LIMIT 1"), {"i": fila[0]}
            ).first()
            if not en_uso:
                conn.execute(text("DELETE FROM tipo_producto WHERE id = :i"), {"i": fila[0]})
