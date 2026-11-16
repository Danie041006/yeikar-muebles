"""Compra múltiple de inventario con pagos divididos.

Revision ID: a8b9c0d1e2f3
Revises: p6a7b8c9d0e1
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa


revision = "a8b9c0d1e2f3"
down_revision = "p6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compra_inventario_multiple",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("operacion_id", sa.String(length=36), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("proveedor_id", sa.BigInteger(), nullable=True),
        sa.Column("proveedor_nombre", sa.String(length=150), nullable=True),
        sa.Column("recibido_por", sa.String(length=150), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("total_en_moneda_base", sa.Numeric(15, 2), nullable=False),
        sa.Column("pagado_en_moneda_base", sa.Numeric(15, 2), nullable=False),
        sa.Column("saldo_en_moneda_base", sa.Numeric(15, 2), nullable=False),
        sa.Column("lineas_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("cuenta_por_pagar_id", sa.BigInteger(), nullable=True),
        sa.Column("creado_por_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["proveedor_id"], ["proveedor.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cuenta_por_pagar_id"], ["cuenta_por_pagar.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuario.id"], ondelete="SET NULL"),
    )
    op.create_unique_constraint(
        "uq_compra_inventario_multiple_operacion_id",
        "compra_inventario_multiple",
        ["operacion_id"],
    )
    op.create_index(
        "ix_compra_inventario_multiple_cuenta_por_pagar_id",
        "compra_inventario_multiple",
        ["cuenta_por_pagar_id"],
    )

    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'sync_registrar_cambio')
               AND NOT EXISTS (
                    SELECT 1 FROM pg_trigger
                    WHERE tgname = 'trg_sync_cambio'
                      AND tgrelid = to_regclass('compra_inventario_multiple')
                      AND NOT tgisinternal
               ) THEN
                CREATE TRIGGER trg_sync_cambio
                AFTER INSERT OR UPDATE OR DELETE ON compra_inventario_multiple
                FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio();
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sync_cambio ON compra_inventario_multiple")
    op.drop_index("ix_compra_inventario_multiple_cuenta_por_pagar_id", table_name="compra_inventario_multiple")
    op.drop_constraint("uq_compra_inventario_multiple_operacion_id", "compra_inventario_multiple", type_="unique")
    op.drop_table("compra_inventario_multiple")
