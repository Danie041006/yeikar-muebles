"""Préstamos por cobrar: prestamo + pago_prestamo

El "Préstamo" que antes era solo una clasificación de gasto pasa a tener
entidad propia para poder registrar a quién se le prestó y cuánto debe:

  * `prestamo`: nace de una salida de caja clasificada PRESTAMO.
  * `pago_prestamo`: cada cobro (parcial o total) atado a su entrada de caja.

Revision ID: q7r8s9t0u1v2
Revises: p1e2z3a4s5f6
Create Date: 2026-10-31
"""
from alembic import op
import sqlalchemy as sa


revision = "q7r8s9t0u1v2"
down_revision = "p1e2z3a4s5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prestamo",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("persona_nombre", sa.String(length=150), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("moneda_id", sa.BigInteger(), nullable=False),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False),
        sa.Column("tasa_cambio", sa.Numeric(15, 6), nullable=False, server_default="1.0"),
        sa.Column("monto_en_moneda_base", sa.Numeric(15, 2), nullable=False, server_default="0.0"),
        sa.Column("monto_abonado", sa.Numeric(15, 2), nullable=False, server_default="0.0"),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="PENDIENTE"),
        sa.Column("metodo_caja_id", sa.BigInteger(), nullable=True),
        sa.Column("movimiento_caja_id", sa.BigInteger(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["moneda_id"], ["moneda.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["metodo_caja_id"], ["metodo_caja.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["movimiento_caja_id"], ["movimiento_caja.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuario.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_prestamo_id", "prestamo", ["id"])
    op.create_index("ix_prestamo_persona_nombre", "prestamo", ["persona_nombre"])
    op.create_index("ix_prestamo_fecha", "prestamo", ["fecha"])
    op.create_index("ix_prestamo_estado", "prestamo", ["estado"])
    op.create_index("ix_prestamo_movimiento_caja_id", "prestamo", ["movimiento_caja_id"])
    op.create_index("ix_prestamo_creado_por_id", "prestamo", ["creado_por_id"])

    op.create_table(
        "pago_prestamo",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("prestamo_id", sa.BigInteger(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False),
        sa.Column("metodo_caja_id", sa.BigInteger(), nullable=False),
        sa.Column("moneda_cuenta_id", sa.BigInteger(), nullable=False),
        sa.Column("tasa_conversion", sa.Numeric(15, 6), nullable=False, server_default="1.0"),
        sa.Column("monto_en_moneda_cuenta", sa.Numeric(15, 2), nullable=False, server_default="0.0"),
        sa.Column("monto_en_moneda_base", sa.Numeric(15, 2), nullable=False, server_default="0.0"),
        sa.Column("movimiento_caja_id", sa.BigInteger(), nullable=True),
        sa.Column("creado_por_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["prestamo_id"], ["prestamo.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["metodo_caja_id"], ["metodo_caja.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["moneda_cuenta_id"], ["moneda.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["movimiento_caja_id"], ["movimiento_caja.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuario.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_pago_prestamo_id", "pago_prestamo", ["id"])
    op.create_index("ix_pago_prestamo_prestamo_id", "pago_prestamo", ["prestamo_id"])
    op.create_index("ix_pago_prestamo_movimiento_caja_id", "pago_prestamo", ["movimiento_caja_id"])
    op.create_index("ix_pago_prestamo_creado_por_id", "pago_prestamo", ["creado_por_id"])

    # Bitácora de sync offline (mismo trigger que el resto de tablas de
    # negocio). Si la función aún no existe (BD sin la migración de sync),
    # se omite: el script adjuntar_triggers_sync.py la crea después.
    op.execute("""
        DO $$
        DECLARE
            tabla text;
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'sync_registrar_cambio') THEN
                FOREACH tabla IN ARRAY ARRAY['prestamo', 'pago_prestamo'] LOOP
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'trg_sync_cambio'
                          AND tgrelid = to_regclass(tabla)
                          AND NOT tgisinternal
                    ) THEN
                        EXECUTE format(
                            'CREATE TRIGGER trg_sync_cambio AFTER INSERT OR UPDATE OR DELETE '
                            'ON %I FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio()',
                            tabla
                        );
                    END IF;
                END LOOP;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("pago_prestamo")
    op.drop_table("prestamo")
