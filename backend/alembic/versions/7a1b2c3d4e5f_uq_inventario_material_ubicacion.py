"""uq_inventario_material_ubicacion

Revision ID: 7a1b2c3d4e5f
Revises: e5f6a7b8c9d0
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a1b2c3d4e5f'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Eliminar filas duplicadas previas (conservar la de mayor id) para que el
    # constraint único pueda crearse sin fallar sobre datos históricos.
    op.execute("""
        DELETE FROM inventario a
        USING inventario b
        WHERE a.material_id = b.material_id
          AND a.ubicacion_id = b.ubicacion_id
          AND a.id < b.id
    """)
    op.create_unique_constraint(
        'uq_inventario_material_ubicacion',
        'inventario',
        ['material_id', 'ubicacion_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_inventario_material_ubicacion', 'inventario', type_='unique')
