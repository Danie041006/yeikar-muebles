"""Reparación/Servicio (tipo_item) y costo de flete en envío

- detalle_cotizacion.descripcion_especifica: descripción del mueble a reparar o
  del servicio (flete/instalación) que viaja cotización → pedido → venta →
  factura. REPARACION/SERVICIO no llevan producto ni material.
- envio: costo real del flete (opcional) con su moneda/TRM y el equivalente en
  moneda base (COP) para conocer el margen real del pedido.

Revision ID: c3d4e5f6a7b8
Revises: c2d3e4f5a6b7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('detalle_cotizacion', sa.Column('descripcion_especifica', sa.Text(), nullable=True))
    op.add_column('envio', sa.Column('costo_flete', sa.Numeric(15, 2), nullable=True))
    op.add_column('envio', sa.Column('moneda_flete_id', sa.BigInteger(), nullable=True))
    op.add_column('envio', sa.Column('tasa_cambio_flete', sa.Numeric(15, 6), nullable=True))
    op.add_column('envio', sa.Column('costo_flete_en_moneda_base', sa.Numeric(15, 2), nullable=True))
    op.create_foreign_key('fk_envio_moneda_flete', 'envio', 'moneda', ['moneda_flete_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    op.drop_constraint('fk_envio_moneda_flete', 'envio', type_='foreignkey')
    op.drop_column('envio', 'costo_flete_en_moneda_base')
    op.drop_column('envio', 'tasa_cambio_flete')
    op.drop_column('envio', 'moneda_flete_id')
    op.drop_column('envio', 'costo_flete')
    op.drop_column('detalle_cotizacion', 'descripcion_especifica')