"""produccion: transparencia y retrabajo

Revision ID: e9f8a7b6c5d4
Revises: 2daa4b3eb80e
Create Date: 2026-08-24

Campos nuevos del módulo de producción:
  - etapa_produccion.es_retrabajo   : retrabajo no paga destajo en nómina
  - consumo_material.creado_por_id  : quién registró el consumo (rendición de cuentas)
  - consumo_material.seccion        : sección de la receta (agrupar por sección)
  - mano_obra.creado_por_id         : quién registró la mano de obra
"""
from alembic import op
import sqlalchemy as sa


revision = "e9f8a7b6c5d4"
down_revision = "2daa4b3eb80e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "etapa_produccion",
        sa.Column("es_retrabajo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("consumo_material", sa.Column("seccion", sa.String(50), nullable=True))
    op.add_column("consumo_material", sa.Column("creado_por_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_consumo_material_creador", "consumo_material", "usuario",
        ["creado_por_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_consumo_material_creado_por", "consumo_material", ["creado_por_id"])
    op.add_column("mano_obra", sa.Column("creado_por_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_mano_obra_creador", "mano_obra", "usuario",
        ["creado_por_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_mano_obra_creado_por", "mano_obra", ["creado_por_id"])


def downgrade() -> None:
    op.drop_index("ix_mano_obra_creado_por", table_name="mano_obra")
    op.drop_constraint("fk_mano_obra_creador", "mano_obra", type_="foreignkey")
    op.drop_column("mano_obra", "creado_por_id")
    op.drop_index("ix_consumo_material_creado_por", table_name="consumo_material")
    op.drop_constraint("fk_consumo_material_creador", "consumo_material", type_="foreignkey")
    op.drop_column("consumo_material", "creado_por_id")
    op.drop_column("consumo_material", "seccion")
    op.drop_column("etapa_produccion", "es_retrabajo")