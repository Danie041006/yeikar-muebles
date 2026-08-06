"""seguridad por registro, auditoria y tracking de envios.

Revision ID: d9e8f7a6b5c4
Revises: c3f4a5b6c7d8
Create Date: 2026-08-06

NOTA: Reparentada desde c6e5f4a3b2d1 a c3f4a5b6c7d8 (el head real aplicado
en la BD) porque la rama original nunca se aplicó y dejaba el esquema sin
las columnas de auditoría (creado_por_id / actualizado_por_id).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "d9e8f7a6b5c4"
down_revision = "c3f4a5b6c7d8"
branch_labels = None
depends_on = None


OWNED_TABLES = (
    "cliente",
    "cotizacion",
    "pedido",
    "venta",
    "gasto",
    "envio",
    "orden_produccion",
)


def _column_exists(conn, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:table AND column_name=:column"
            ),
            {"table": table, "column": column},
        ).first()
    )


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:table"
            ),
            {"table": table},
        ).first()
    )


def _add_actor_columns(conn, table: str) -> None:
    for column, constraint in (
        ("creado_por_id", f"fk_{table}_creado_por"),
        ("actualizado_por_id", f"fk_{table}_actualizado_por"),
    ):
        if not _column_exists(conn, table, column):
            op.add_column(table, sa.Column(column, sa.BigInteger(), nullable=True))
            op.create_foreign_key(
                constraint,
                table,
                "usuario",
                [column],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    conn = op.get_bind()

    for table in OWNED_TABLES:
        if _table_exists(conn, table):
            _add_actor_columns(conn, table)

    if not _table_exists(conn, "envio"):
        raise RuntimeError("La tabla envio es necesaria para habilitar el tracking seguro.")

    if not _column_exists(conn, "envio", "asignado_por_usuario_id"):
        op.add_column("envio", sa.Column("asignado_por_usuario_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(
            "fk_envio_asignado_por_usuario",
            "envio",
            "usuario",
            ["asignado_por_usuario_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_envio_asignado_por_usuario_id", "envio", ["asignado_por_usuario_id"])

    if not _table_exists(conn, "audit_event"):
        op.create_table(
            "audit_event",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.String(length=80), nullable=False),
            sa.Column("before_data", sa.JSON(), nullable=True),
            sa.Column("after_data", sa.JSON(), nullable=True),
            sa.Column("changed_fields", sa.JSON(), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["actor_user_id"], ["usuario.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_audit_event_actor_user_id", "audit_event", ["actor_user_id"])
        op.create_index("ix_audit_event_entity_type", "audit_event", ["entity_type"])
        op.create_index("ix_audit_event_entity_id", "audit_event", ["entity_id"])
        op.create_index("ix_audit_event_created_at", "audit_event", ["created_at"])
        op.create_index(
            "ix_audit_event_entity_created",
            "audit_event",
            ["entity_type", "entity_id", "created_at"],
        )

    if not _table_exists(conn, "envio_asignacion"):
        op.create_table(
            "envio_asignacion",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("envio_id", sa.BigInteger(), nullable=False),
            sa.Column("empleado_id", sa.BigInteger(), nullable=True),
            sa.Column("asignado_por_usuario_id", sa.BigInteger(), nullable=True),
            sa.Column("asignado_en", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("desasignado_en", sa.DateTime(), nullable=True),
            sa.Column("motivo", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["envio_id"], ["envio.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["empleado_id"], ["empleado.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["asignado_por_usuario_id"], ["usuario.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_envio_asignacion_envio_id", "envio_asignacion", ["envio_id"])

    if not _table_exists(conn, "envio_ubicacion"):
        op.create_table(
            "envio_ubicacion",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("envio_id", sa.BigInteger(), nullable=False),
            sa.Column("empleado_id", sa.BigInteger(), nullable=True),
            sa.Column("reportado_por_id", sa.BigInteger(), nullable=True),
            sa.Column("latitud", sa.Numeric(10, 7), nullable=False),
            sa.Column("longitud", sa.Numeric(10, 7), nullable=False),
            sa.Column("precision_m", sa.Numeric(10, 2), nullable=True),
            sa.Column("velocidad", sa.Numeric(10, 2), nullable=True),
            sa.Column("rumbo", sa.Numeric(6, 2), nullable=True),
            sa.Column("capturada_en", sa.DateTime(), nullable=True),
            sa.Column("recibida_en", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("fuente", sa.String(length=30), server_default="web", nullable=False),
            sa.Column("secuencia", sa.BigInteger(), nullable=True),
            sa.ForeignKeyConstraint(["envio_id"], ["envio.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["empleado_id"], ["empleado.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["reportado_por_id"], ["usuario.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("envio_id", "reportado_por_id", "secuencia", name="uq_envio_ubicacion_secuencia"),
        )
        op.create_index("ix_envio_ubicacion_envio_id", "envio_ubicacion", ["envio_id"])
        op.create_index("ix_envio_ubicacion_empleado_id", "envio_ubicacion", ["empleado_id"])
        op.create_index("ix_envio_ubicacion_reportado_por_id", "envio_ubicacion", ["reportado_por_id"])
        op.create_index("ix_envio_ubicacion_recibida_en", "envio_ubicacion", ["recibida_en"])
        op.create_index("ix_envio_ubicacion_envio_recibida", "envio_ubicacion", ["envio_id", "recibida_en"])


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "envio_ubicacion"):
        op.drop_index("ix_envio_ubicacion_envio_recibida", table_name="envio_ubicacion")
        op.drop_index("ix_envio_ubicacion_recibida_en", table_name="envio_ubicacion")
        op.drop_index("ix_envio_ubicacion_reportado_por_id", table_name="envio_ubicacion")
        op.drop_index("ix_envio_ubicacion_empleado_id", table_name="envio_ubicacion")
        op.drop_index("ix_envio_ubicacion_envio_id", table_name="envio_ubicacion")
        op.drop_table("envio_ubicacion")
    if _table_exists(conn, "envio_asignacion"):
        op.drop_index("ix_envio_asignacion_envio_id", table_name="envio_asignacion")
        op.drop_table("envio_asignacion")
    if _table_exists(conn, "audit_event"):
        op.drop_index("ix_audit_event_entity_created", table_name="audit_event")
        op.drop_index("ix_audit_event_created_at", table_name="audit_event")
        op.drop_index("ix_audit_event_entity_id", table_name="audit_event")
        op.drop_index("ix_audit_event_entity_type", table_name="audit_event")
        op.drop_index("ix_audit_event_actor_user_id", table_name="audit_event")
        op.drop_table("audit_event")

    if _column_exists(conn, "envio", "asignado_por_usuario_id"):
        op.drop_index("ix_envio_asignado_por_usuario_id", table_name="envio")
        op.drop_constraint("fk_envio_asignado_por_usuario", "envio", type_="foreignkey")
        op.drop_column("envio", "asignado_por_usuario_id")

    for table in reversed(OWNED_TABLES):
        for column, constraint in (
            ("actualizado_por_id", f"fk_{table}_actualizado_por"),
            ("creado_por_id", f"fk_{table}_creado_por"),
        ):
            if _column_exists(conn, table, column):
                op.drop_index(f"ix_{table}_{column}", table_name=table)
                op.drop_constraint(constraint, table, type_="foreignkey")
                op.drop_column(table, column)
