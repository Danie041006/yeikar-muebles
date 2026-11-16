"""Enlaces e historial de correcciones de entradas de inventario.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
"""
from alembic import op
import sqlalchemy as sa

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for columna in (
        sa.Column("datos_json", sa.JSON(), nullable=True),
        sa.Column("original_json", sa.JSON(), nullable=True),
        sa.Column("pagos_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("actualizado_por_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ):
        op.add_column("compra_inventario_multiple", columna)
    op.create_foreign_key("fk_entrada_actualizador", "compra_inventario_multiple", "usuario", ["actualizado_por_id"], ["id"], ondelete="SET NULL")
    op.add_column("gasto", sa.Column("entrada_inventario_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_gasto_entrada_inventario", "gasto", "compra_inventario_multiple", ["entrada_inventario_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_gasto_entrada_inventario_id", "gasto", ["entrada_inventario_id"])
    op.create_table(
        "correccion_entrada_inventario",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("compra_id", sa.BigInteger(), sa.ForeignKey("compra_inventario_multiple.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operacion_id", sa.String(36), nullable=False, unique=True),
        sa.Column("solicitud_json", sa.JSON(), nullable=False),
        sa.Column("respuesta_json", sa.JSON(), nullable=False),
        sa.Column("motivo", sa.String(500), nullable=False),
        sa.Column("antes_json", sa.JSON(), nullable=False),
        sa.Column("despues_json", sa.JSON(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), sa.ForeignKey("usuario.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_correccion_entrada_inventario_compra_id", "correccion_entrada_inventario", ["compra_id"])
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'sync_registrar_cambio') THEN
                CREATE TRIGGER trg_sync_cambio AFTER INSERT OR UPDATE OR DELETE
                ON correccion_entrada_inventario FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio();
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("correccion_entrada_inventario")
    op.drop_index("ix_gasto_entrada_inventario_id", table_name="gasto")
    op.drop_constraint("fk_gasto_entrada_inventario", "gasto", type_="foreignkey")
    op.drop_column("gasto", "entrada_inventario_id")
    op.drop_constraint("fk_entrada_actualizador", "compra_inventario_multiple", type_="foreignkey")
    for nombre in ("updated_at", "actualizado_por_id", "version", "pagos_json", "original_json", "datos_json"):
        op.drop_column("compra_inventario_multiple", nombre)
