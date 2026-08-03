"""seguridad login: tabla login_intento + rotación de refresh tokens.

Revision ID: b1a2c3d4e5f6
Revises: c6e5f4a3b2d1
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "b1a2c3d4e5f6"
down_revision = "c6e5f4a3b2d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_intento",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("exito", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_login_intento_id", "login_intento", ["id"])
    op.create_index("ix_login_intento_ip", "login_intento", ["ip"])
    op.create_index("ix_login_intento_username", "login_intento", ["username"])
    op.create_index("ix_login_intento_username_created_at", "login_intento", ["username", "created_at"])

    op.create_table(
        "refresh_token",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("usuario_id", sa.BigInteger(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revocado", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_refresh_token_id", "refresh_token", ["id"])
    op.create_index("ix_refresh_token_usuario_id", "refresh_token", ["usuario_id"])
    op.create_index("ix_refresh_token_token_hash", "refresh_token", ["token_hash"], unique=True)
    op.create_foreign_key(
        "fk_refresh_token_usuario",
        "refresh_token",
        "usuario",
        ["usuario_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_refresh_token_usuario", "refresh_token", type_="foreignkey")
    op.drop_index("ix_refresh_token_token_hash", table_name="refresh_token")
    op.drop_index("ix_refresh_token_usuario_id", table_name="refresh_token")
    op.drop_index("ix_refresh_token_id", table_name="refresh_token")
    op.drop_table("refresh_token")

    op.drop_index("ix_login_intento_username_created_at", table_name="login_intento")
    op.drop_index("ix_login_intento_username", table_name="login_intento")
    op.drop_index("ix_login_intento_ip", table_name="login_intento")
    op.drop_index("ix_login_intento_id", table_name="login_intento")
    op.drop_table("login_intento")
