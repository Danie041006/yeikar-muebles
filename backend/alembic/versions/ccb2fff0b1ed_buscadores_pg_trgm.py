"""buscadores_pg_trgm

Índices GIN con pg_trgm para que las búsquedas ILIKE %termino% (buscadores de
cliente, producto, material y despachos) usen el índice en vez de escanear la
tabla. Sin esto, un btree NO puede acelerar un patrón con comodín a ambos lados.

Revision ID: ccb2fff0b1ed
Revises: b518384162af
Create Date: 2026-08-25 10:36:59.550222

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'ccb2fff0b1ed'
down_revision: Union[str, None] = 'b518384162af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabla, nombre del índice, columna)
GIN_INDICES = [
    ("cliente", "ix_cliente_nombre_trgm", "nombre"),
    ("producto", "ix_producto_nombre_trgm", "nombre"),
    ("material", "ix_material_nombre_trgm", "nombre"),
    ("material_sinonimo", "ix_material_sinonimo_sinonimo_trgm", "sinonimo"),
    ("envio", "ix_envio_guia_despacho_trgm", "guia_despacho"),
    ("envio", "ix_envio_direccion_entrega_trgm", "direccion_entrega"),
]


def upgrade() -> None:
    op.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    for tabla, nombre, columna in GIN_INDICES:
        op.execute(
            text(
                f"CREATE INDEX {nombre} ON {tabla} "
                f"USING gin ({columna} gin_trgm_ops)"
            )
        )


def downgrade() -> None:
    for tabla, nombre, columna in reversed(GIN_INDICES):
        op.execute(text(f"DROP INDEX IF EXISTS {nombre}"))
