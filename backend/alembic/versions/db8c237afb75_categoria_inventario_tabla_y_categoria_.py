"""categoria_inventario: tabla y categoria_inventario_id en producto/material

Revision ID: db8c237afb75
Revises: 9f47b518bfcb
Create Date: 2026-08-31 08:32:05.606824

Sincluye el feature de sobrantes de lámina (sobrante_lamina + columnas de
corte en consumo_material/produccion_crudo_consumo/producto_material/material).
Limpio a mano: solo cambios de modelos, sin el drift preexistente de índices.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db8c237afb75'
down_revision: Union[str, None] = '9f47b518bfcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Categorías de inventario (catálogo) ──────────────────────────────
    op.create_table('categoria_inventario',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_categoria_inventario_id'), 'categoria_inventario', ['id'], unique=False)

    # ── Sobrantes de lámina ──────────────────────────────────────────────
    op.create_table('sobrante_lamina',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('material_id', sa.BigInteger(), nullable=False),
        sa.Column('ubicacion_id', sa.BigInteger(), nullable=False),
        sa.Column('largo_cm', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('ancho_cm', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('consumo_origen_id', sa.BigInteger(), nullable=True),
        sa.Column('consumo_origen_tipo', sa.String(length=30), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['material_id'], ['material.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['ubicacion_id'], ['ubicacion.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sobrante_lamina_consumo_origen_id'), 'sobrante_lamina', ['consumo_origen_id'], unique=False)
    op.create_index(op.f('ix_sobrante_lamina_estado'), 'sobrante_lamina', ['estado'], unique=False)
    op.create_index(op.f('ix_sobrante_lamina_id'), 'sobrante_lamina', ['id'], unique=False)
    op.create_index(op.f('ix_sobrante_lamina_material_id'), 'sobrante_lamina', ['material_id'], unique=False)

    # ── consumo_material: cortes + origen sobrante ───────────────────────
    op.add_column('consumo_material', sa.Column('ancho_corte_cm', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('consumo_material', sa.Column('largo_corte_cm', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('consumo_material', sa.Column('origen_sobrante_id', sa.BigInteger(), nullable=True))
    op.add_column('consumo_material', sa.Column('laminas_consumidas', sa.Numeric(precision=12, scale=2), nullable=True))
    op.create_index(op.f('ix_consumo_material_origen_sobrante_id'), 'consumo_material', ['origen_sobrante_id'], unique=False)
    op.create_foreign_key(
        'fk_consumo_material_origen_sobrante_id',
        'consumo_material', 'sobrante_lamina', ['origen_sobrante_id'], ['id'], ondelete='SET NULL',
    )

    # ── material: dimensiones de lámina + categoría ──────────────────────
    op.add_column('material', sa.Column('largo_cm', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('material', sa.Column('ancho_cm', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('material', sa.Column('categoria_inventario_id', sa.BigInteger(), nullable=True))
    op.create_index(op.f('ix_material_categoria_inventario_id'), 'material', ['categoria_inventario_id'], unique=False)
    op.create_foreign_key(
        'fk_material_categoria_inventario_id',
        'material', 'categoria_inventario', ['categoria_inventario_id'], ['id'], ondelete='SET NULL',
    )

    # ── produccion_crudo_consumo: cortes + origen sobrante ───────────────
    op.add_column('produccion_crudo_consumo', sa.Column('ancho_corte_cm', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('produccion_crudo_consumo', sa.Column('largo_corte_cm', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('produccion_crudo_consumo', sa.Column('origen_sobrante_id', sa.BigInteger(), nullable=True))
    op.add_column('produccion_crudo_consumo', sa.Column('laminas_consumidas', sa.Numeric(precision=12, scale=2), nullable=True))
    op.create_index(op.f('ix_produccion_crudo_consumo_origen_sobrante_id'), 'produccion_crudo_consumo', ['origen_sobrante_id'], unique=False)
    op.create_foreign_key(
        'fk_produccion_crudo_consumo_origen_sobrante_id',
        'produccion_crudo_consumo', 'sobrante_lamina', ['origen_sobrante_id'], ['id'], ondelete='SET NULL',
    )

    # ── producto: categoría de inventario ────────────────────────────────
    op.add_column('producto', sa.Column('categoria_inventario_id', sa.BigInteger(), nullable=True))
    op.create_index(op.f('ix_producto_categoria_inventario_id'), 'producto', ['categoria_inventario_id'], unique=False)
    op.create_foreign_key(
        'fk_producto_categoria_inventario_id',
        'producto', 'categoria_inventario', ['categoria_inventario_id'], ['id'], ondelete='SET NULL',
    )

    # ── producto_material: dimensiones de corte ──────────────────────────
    op.add_column('producto_material', sa.Column('ancho_corte_cm', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('producto_material', sa.Column('largo_corte_cm', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column('producto_material', 'largo_corte_cm')
    op.drop_column('producto_material', 'ancho_corte_cm')

    op.drop_constraint('fk_producto_categoria_inventario_id', 'producto', type_='foreignkey')
    op.drop_index(op.f('ix_producto_categoria_inventario_id'), table_name='producto')
    op.drop_column('producto', 'categoria_inventario_id')

    op.drop_constraint('fk_produccion_crudo_consumo_origen_sobrante_id', 'produccion_crudo_consumo', type_='foreignkey')
    op.drop_index(op.f('ix_produccion_crudo_consumo_origen_sobrante_id'), table_name='produccion_crudo_consumo')
    op.drop_column('produccion_crudo_consumo', 'laminas_consumidas')
    op.drop_column('produccion_crudo_consumo', 'origen_sobrante_id')
    op.drop_column('produccion_crudo_consumo', 'largo_corte_cm')
    op.drop_column('produccion_crudo_consumo', 'ancho_corte_cm')

    op.drop_constraint('fk_material_categoria_inventario_id', 'material', type_='foreignkey')
    op.drop_index(op.f('ix_material_categoria_inventario_id'), table_name='material')
    op.drop_column('material', 'categoria_inventario_id')
    op.drop_column('material', 'ancho_cm')
    op.drop_column('material', 'largo_cm')

    op.drop_constraint('fk_consumo_material_origen_sobrante_id', 'consumo_material', type_='foreignkey')
    op.drop_index(op.f('ix_consumo_material_origen_sobrante_id'), table_name='consumo_material')
    op.drop_column('consumo_material', 'laminas_consumidas')
    op.drop_column('consumo_material', 'origen_sobrante_id')
    op.drop_column('consumo_material', 'largo_corte_cm')
    op.drop_column('consumo_material', 'ancho_corte_cm')

    op.drop_index(op.f('ix_sobrante_lamina_material_id'), table_name='sobrante_lamina')
    op.drop_index(op.f('ix_sobrante_lamina_id'), table_name='sobrante_lamina')
    op.drop_index(op.f('ix_sobrante_lamina_estado'), table_name='sobrante_lamina')
    op.drop_index(op.f('ix_sobrante_lamina_consumo_origen_id'), table_name='sobrante_lamina')
    op.drop_table('sobrante_lamina')

    op.drop_index(op.f('ix_categoria_inventario_id'), table_name='categoria_inventario')
    op.drop_table('categoria_inventario')
