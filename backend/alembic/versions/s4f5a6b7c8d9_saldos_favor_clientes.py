"""Excedentes de cobro y aplicaciones de crédito de clientes, sin nueva caja.

Revision ID: s4f5a6b7c8d9
Revises: c0d1e2f3a4b5
"""
from alembic import op
import sqlalchemy as sa

revision = "s4f5a6b7c8d9"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pago", sa.Column("monto_aplicado", sa.Numeric(15, 2), nullable=True))
    op.add_column("pago", sa.Column("tipo", sa.String(20), nullable=False, server_default="COBRO"))
    op.add_column("pago", sa.Column("operacion_id", sa.String(36), nullable=True))
    op.create_unique_constraint("uq_pago_operacion_id", "pago", ["operacion_id"])
    # NULL equivale al importe histórico; no se reescribe ningún pago ni caja.
    op.create_table(
        "saldo_favor",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("cliente.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("moneda_id", sa.BigInteger(), sa.ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pago_origen_id", sa.BigInteger(), sa.ForeignKey("pago.id", ondelete="SET NULL"), unique=True),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False),
        sa.Column("origen", sa.String(30), nullable=False),
        sa.Column("referencia", sa.String(150), nullable=False),
        sa.Column("anulado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creado_por_id", sa.BigInteger(), sa.ForeignKey("usuario.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("monto >= 0", name="ck_saldo_favor_monto"),
    )
    op.create_index("ix_saldo_favor_cliente_id", "saldo_favor", ["cliente_id"])
    op.create_table(
        "aplicacion_saldo_favor",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("saldo_favor_id", sa.BigInteger(), sa.ForeignKey("saldo_favor.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pago_id", sa.BigInteger(), sa.ForeignKey("pago.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False),
        sa.CheckConstraint("monto > 0", name="ck_aplicacion_saldo_favor_monto"),
    )
    op.create_index("ix_aplicacion_saldo_favor_saldo_favor_id", "aplicacion_saldo_favor", ["saldo_favor_id"])
    for tabla in ("saldo_favor", "aplicacion_saldo_favor"):
        op.execute(sa.text(f"""
            CREATE TRIGGER trg_sync_cambio AFTER INSERT OR UPDATE OR DELETE ON {tabla}
            FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio()
        """))


def downgrade() -> None:
    op.drop_table("aplicacion_saldo_favor")
    op.drop_table("saldo_favor")
    op.drop_constraint("uq_pago_operacion_id", "pago", type_="unique")
    for campo in ("operacion_id", "tipo", "monto_aplicado"):
        op.drop_column("pago", campo)
