"""indices_trgm_empleados

Índices GIN pg_trgm sobre empleado.nombre y empleado.telefono para que el
autocomplete de trabajadores (búsqueda server-side ILIKE %termino% en el
selector de producción, nómina y despachos) use el índice en vez de escanear.

Revision ID: w7x8y9z0a1b2c
Revises: v7w8x9y0z1a2
Create Date: 2026-09-22 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'w7x8y9z0a1b2c'
down_revision: Union[str, None] = 'v7w8x9y0z1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    op.execute(
        text(
            "CREATE INDEX ix_empleado_nombre_trgm ON empleado "
            "USING gin (nombre gin_trgm_ops)"
        )
    )
    op.execute(
        text(
            "CREATE INDEX ix_empleado_telefono_trgm ON empleado "
            "USING gin (telefono gin_trgm_ops)"
        )
    )


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS ix_empleado_nombre_trgm"))
    op.execute(text("DROP INDEX IF EXISTS ix_empleado_telefono_trgm"))