"""indices_trgm_catalogos

Índices GIN pg_trgm para el resto de catálogos con búsqueda ILIKE %termino%
(multi-campo) que antes caían en Seq Scan completo: producto.codigo,
cliente.telefono/cedula, proveedor.nombre/email/telefono,
unidad_medida.nombre/abreviatura y tipo_gasto.nombre.

Complementa:
- ccb2fff0b1ed (cliente.nombre, producto.nombre, material.nombre,
  material_sinonimo.sinonimo, envio.*)
- w7x8y9z0a1b2c (empleado.nombre, empleado.telefono)

Revision ID: w9x0y1z2a3b4c
Revises: w7x8y9z0a1b2c
Create Date: 2026-09-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'w9x0y1z2a3b4c'
down_revision: Union[str, None] = 'w7x8y9z0a1b2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabla, nombre del índice, columna)
GIN_INDICES = [
    ("producto", "ix_producto_codigo_trgm", "codigo"),
    ("cliente", "ix_cliente_telefono_trgm", "telefono"),
    ("cliente", "ix_cliente_cedula_trgm", "cedula"),
    ("proveedor", "ix_proveedor_nombre_trgm", "nombre"),
    ("proveedor", "ix_proveedor_email_trgm", "email"),
    ("proveedor", "ix_proveedor_telefono_trgm", "telefono"),
    ("unidad_medida", "ix_unidad_medida_nombre_trgm", "nombre"),
    ("unidad_medida", "ix_unidad_medida_abreviatura_trgm", "abreviatura"),
    ("tipo_gasto", "ix_tipo_gasto_nombre_trgm", "nombre"),
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