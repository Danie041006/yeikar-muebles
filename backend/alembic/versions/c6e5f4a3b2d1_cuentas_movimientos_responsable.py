"""cuentas: responsable (usuario_id) en movimiento_caja + módulo cuentas.

Revision ID: c6e5f4a3b2d1
Revises: 9a8b7c6d5e4f
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "c6e5f4a3b2d1"
down_revision = "9a8b7c6d5e4f"
branch_labels = None
depends_on = None


def _existe_columna(conn, tabla: str, columna: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ),
            {"t": tabla, "c": columna},
        ).first()
    )


def upgrade() -> None:
    conn = op.get_bind()

    # Responsable del registro del movimiento (usuario que lo creó).
    if not _existe_columna(conn, "movimiento_caja", "usuario_id"):
        op.add_column(
            "movimiento_caja",
            sa.Column("usuario_id", sa.BigInteger(), nullable=True),
        )
        op.create_foreign_key(
            "fk_movimiento_caja_usuario",
            "movimiento_caja",
            "usuario",
            ["usuario_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_movimiento_caja_usuario_id", "movimiento_caja", ["usuario_id"])

    # Módulo de permisos "cuentas": Dueño y Administrador lo gestionan.
    # El resto de roles queda sin acceso hasta que se configure en el panel.
    conn.execute(
        text(
            "INSERT INTO rol_modulo (rol_id, modulo, gestionar) "
            "SELECT id, 'cuentas', TRUE FROM rol WHERE nombre IN ('Dueño', 'Administrador') "
            "ON CONFLICT (rol_id, modulo) DO UPDATE SET gestionar = TRUE"
        )
    )

    # La tabla metodo_caja fue sembrada con IDs explícitos (1-6) sin avanzar la
    # secuencia; reposición del autoincremento para que los INSERT no colisionen.
    conn.execute(
        text("SELECT setval(pg_get_serial_sequence('metodo_caja', 'id'), (SELECT COALESCE(MAX(id), 1) FROM metodo_caja))")
    )


def downgrade() -> None:
    conn = op.get_bind()
    if _existe_columna(conn, "movimiento_caja", "usuario_id"):
        op.drop_constraint("fk_movimiento_caja_usuario", "movimiento_caja", type_="foreignkey")
        op.drop_index("ix_movimiento_caja_usuario_id", table_name="movimiento_caja")
        op.drop_column("movimiento_caja", "usuario_id")
    conn.execute(
        text("DELETE FROM rol_modulo WHERE modulo = 'cuentas'")
    )