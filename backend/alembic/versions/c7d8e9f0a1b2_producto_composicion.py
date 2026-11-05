"""producto: composición de un conjunto en piezas (producto_pieza)

Un mueble puede ser un CONJUNTO de piezas (un comedor = mesa ×1 + sillas ×6) y
cada pieza es ella misma un producto del catálogo con su costo y su precio.

- producto.es_conjunto: lo mantiene el endpoint de composición.
- producto.es_pieza: marca de catálogo para las piezas (se pueden cotizar
  solas o combinar con piezas de otros conjuntos).
- producto_pieza: composición del conjunto (sin duplicar costo/precio).

No toca la receta de materiales ni el motor de costos: es el desglose
comercial y de costo del mueble. Migración 100% aditiva.

Revision ID: c7d8e9f0a1b2
Revises: u9n8i7f6g5a4
Create Date: 2026-11-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'u9n8i7f6g5a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('producto', sa.Column('es_conjunto', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('producto', sa.Column('es_pieza', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index('ix_producto_es_pieza', 'producto', ['es_pieza'])

    op.create_table(
        'producto_pieza',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True, index=True),
        sa.Column('producto_id', sa.BigInteger(), sa.ForeignKey('producto.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('pieza_producto_id', sa.BigInteger(), sa.ForeignKey('producto.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('cantidad', sa.Numeric(10, 2), nullable=False, server_default='1'),
        sa.Column('orden', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('producto_id', 'pieza_producto_id', name='uq_producto_pieza_conjunto_pieza'),
    )

    # La tabla nueva entra a la réplica offline (misma función de sync que el
    # resto de tablas de negocio). Condicionado a que la función exista.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'sync_registrar_cambio') THEN
                CREATE TRIGGER trg_sync_cambio AFTER INSERT OR UPDATE OR DELETE
                ON "producto_pieza" FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio();
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS trg_sync_cambio ON "producto_pieza"')
    op.drop_table('producto_pieza')
    op.drop_index('ix_producto_es_pieza', table_name='producto')
    op.drop_column('producto', 'es_pieza')
    op.drop_column('producto', 'es_conjunto')
