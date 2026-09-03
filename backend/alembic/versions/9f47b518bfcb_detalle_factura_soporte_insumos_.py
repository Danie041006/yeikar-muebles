"""detalle_factura: soporte insumos (producto_id nullable + material_id + tipo_item)

Revision ID: 9f47b518bfcb
Revises: b5ac1f578227
Create Date: 2026-08-31 07:39:26.181274

Una línea de factura puede ser un insumo vendido suelto (tipo_item=INSUMO,
material_id NOT NULL, producto_id NULL), igual que DetallePedido/DetalleVenta.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f47b518bfcb'
down_revision: Union[str, None] = 'b5ac1f578227'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'detalle_factura',
        sa.Column('tipo_item', sa.String(length=20), nullable=False, server_default='FABRICADO'),
    )
    op.add_column(
        'detalle_factura',
        sa.Column('material_id', sa.BigInteger(), nullable=True),
    )
    op.alter_column('detalle_factura', 'producto_id', existing_type=sa.BIGINT(), nullable=True)
    op.create_foreign_key(
        'fk_detalle_factura_material_id_material',
        'detalle_factura', 'material', ['material_id'], ['id'], ondelete='RESTRICT',
    )


def downgrade() -> None:
    # Solo puede revertirse si no quedan líneas INSUMO (producto_id NULL).
    op.drop_constraint(
        'fk_detalle_factura_material_id_material', 'detalle_factura', type_='foreignkey',
    )
    op.alter_column('detalle_factura', 'producto_id', existing_type=sa.BIGINT(), nullable=False)
    op.drop_column('detalle_factura', 'material_id')
    op.drop_column('detalle_factura', 'tipo_item')
