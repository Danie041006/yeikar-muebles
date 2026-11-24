"""Cargos múltiples por empleado y cargos de asesora/exhibidora.

Revision ID: e7a8b9c0d1e2
Revises: s4f5a6b7c8d9
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a8b9c0d1e2"
down_revision = "s4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "empleado_cargo",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "empleado_id", sa.BigInteger(),
            sa.ForeignKey("empleado.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "cargo_id", sa.BigInteger(),
            sa.ForeignKey("cargo.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("empleado_id", "cargo_id", name="uq_empleado_cargo"),
    )
    op.create_index("ix_empleado_cargo_empleado_id", "empleado_cargo", ["empleado_id"])
    op.create_index("ix_empleado_cargo_cargo_id", "empleado_cargo", ["cargo_id"])

    # Todo empleado existente conserva su cargo principal como primera asignación.
    op.execute("""
        INSERT INTO empleado_cargo (empleado_id, cargo_id, orden)
        SELECT e.id, e.cargo_id, 0
        FROM empleado e
        WHERE NOT EXISTS (
            SELECT 1 FROM empleado_cargo ec WHERE ec.empleado_id = e.id
        )
    """)

    # Cargos solicitados desde el formulario de empleado. Idempotente por nombre.
    op.execute("""
        INSERT INTO cargo (nombre)
        SELECT v.nombre
        FROM (VALUES ('ASESORA'), ('EXHIBIDORA DE VENTAS')) AS v(nombre)
        WHERE NOT EXISTS (
            SELECT 1 FROM cargo c WHERE lower(c.nombre) = lower(v.nombre)
        )
    """)

    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'sync_registrar_cambio') THEN
                CREATE TRIGGER trg_sync_cambio
                AFTER INSERT OR UPDATE OR DELETE ON empleado_cargo
                FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio();
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("empleado_cargo")
    op.execute("""
        DELETE FROM cargo
        WHERE nombre IN ('ASESORA', 'EXHIBIDORA DE VENTAS')
          AND NOT EXISTS (SELECT 1 FROM empleado WHERE cargo_id = cargo.id)
    """)
