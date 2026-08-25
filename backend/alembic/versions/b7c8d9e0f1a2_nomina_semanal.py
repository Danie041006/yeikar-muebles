"""nómina semanal: tablas de nómina, config de áreas, columnas de empleado

Revision ID: b7c8d9e0f1a2
Revises: f5c6d7e8f9a0
Create Date: 2026-08-14

Crea las tablas de nómina semanal (nomina, nomina_detalle, nomina_linea,
nomina_concepto_vario, nomina_area_config), extiende `empleado` con los
campos de nómina, siembra los % de aguinaldo por área (Ebanistería 8%,
resto 5%), el tipo de gasto "NÓMINA SEMANAL" y otorga el módulo `nomina`
a Dueño, Administrador y Producción.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "f5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------
    # Empleado: campos de nómina
    # ------------------------------------------------------------
    op.add_column("empleado", sa.Column("en_nomina", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("empleado", sa.Column("tipo_pago", sa.String(20), nullable=True))  # DESTAJO | FIJO
    op.add_column("empleado", sa.Column("sueldo_semanal", sa.Numeric(15, 2), nullable=True))
    op.add_column("empleado", sa.Column("saldo_aguinaldo", sa.Numeric(15, 2), nullable=False, server_default="0"))
    op.add_column("empleado", sa.Column("porcentaje_aguinaldo", sa.Numeric(5, 2), nullable=True))

    # ------------------------------------------------------------
    # Tablas de nómina
    # ------------------------------------------------------------
    op.create_table(
        "nomina",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("periodo_desde", sa.Date(), nullable=False),
        sa.Column("periodo_hasta", sa.Date(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="BORRADOR"),  # BORRADOR | PAGADA | ANULADA
        sa.Column("descripcion", sa.String(200), nullable=True),
        sa.Column("total_nomina", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("creado_por_id", sa.BigInteger(), sa.ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.func.now()),
    )

    op.create_table(
        "nomina_detalle",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("nomina_id", sa.BigInteger(), sa.ForeignKey("nomina.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("empleado_id", sa.BigInteger(), sa.ForeignKey("empleado.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tipo_pago", sa.String(20), nullable=False),  # DESTAJO | FIJO
        sa.Column("total_produccion", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("bono_aguinaldo", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("monto_a_pagar", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("metodo_caja_id", sa.BigInteger(), sa.ForeignKey("metodo_caja.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("gasto_id", sa.BigInteger(), sa.ForeignKey("gasto.id", ondelete="SET NULL"), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.func.now()),
    )
    op.create_index("ix_nomina_detalle_nomina_empleado", "nomina_detalle", ["nomina_id", "empleado_id"])

    op.create_table(
        "nomina_linea",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("detalle_id", sa.BigInteger(), sa.ForeignKey("nomina_detalle.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("origen", sa.String(20), nullable=False, server_default="MANUAL"),  # ETAPA | MANUAL
        sa.Column("etapa_id", sa.BigInteger(), nullable=True),
        sa.Column("descripcion", sa.String(250), nullable=False),
        sa.Column("area_id", sa.BigInteger(), sa.ForeignKey("area.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cliente_nombre", sa.String(150), nullable=True),
        sa.Column("cantidad", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("precio_unitario", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "nomina_concepto_vario",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("nomina_id", sa.BigInteger(), sa.ForeignKey("nomina.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "nomina_area_config",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("area_id", sa.BigInteger(), sa.ForeignKey("area.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("porcentaje_aguinaldo", sa.Numeric(5, 2), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------
    # Seeds: % de aguinaldo por área (Ebanistería 8%, resto 5%)
    # ------------------------------------------------------------
    for area_nombre, pct in (("Ebanistería", 8), ("Preparación", 5), ("Pintura", 5), ("Tapicería", 5)):
        area = conn.execute(text("SELECT id FROM area WHERE nombre = :n"), {"n": area_nombre}).first()
        if area:
            conn.execute(
                text(
                    "INSERT INTO nomina_area_config (area_id, porcentaje_aguinaldo) VALUES (:a, :p) "
                    "ON CONFLICT (area_id) DO UPDATE SET porcentaje_aguinaldo = :p"
                ),
                {"a": area[0], "p": pct},
            )

    # Tipo de gasto para los egresos automáticos de nómina
    conn.execute(
        text(
            "INSERT INTO tipo_gasto (nombre, categoria) VALUES ('NÓMINA SEMANAL', 'OPERATIVO') "
            "ON CONFLICT (nombre) DO NOTHING"
        )
    )

    # ------------------------------------------------------------
    # Permiso del módulo: Dueño, Administrador y Producción
    # ------------------------------------------------------------
    for rol_nombre in ("Dueño", "Administrador", "Producción"):
        rol = conn.execute(text("SELECT id FROM rol WHERE nombre = :n"), {"n": rol_nombre}).first()
        if rol:
            conn.execute(
                text(
                    "INSERT INTO rol_modulo (rol_id, modulo, gestionar) VALUES (:r, 'nomina', TRUE) "
                    "ON CONFLICT (rol_id, modulo) DO UPDATE SET gestionar = TRUE"
                ),
                {"r": rol[0]},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM rol_modulo WHERE modulo = 'nomina'"))
    conn.execute(text("DELETE FROM tipo_gasto WHERE nombre = 'NÓMINA SEMANAL'"))
    op.drop_table("nomina_area_config")
    op.drop_table("nomina_concepto_vario")
    op.drop_table("nomina_linea")
    op.drop_index("ix_nomina_detalle_nomina_empleado", table_name="nomina_detalle")
    op.drop_table("nomina_detalle")
    op.drop_table("nomina")
    op.drop_column("empleado", "porcentaje_aguinaldo")
    op.drop_column("empleado", "saldo_aguinaldo")
    op.drop_column("empleado", "sueldo_semanal")
    op.drop_column("empleado", "tipo_pago")
    op.drop_column("empleado", "en_nomina")
