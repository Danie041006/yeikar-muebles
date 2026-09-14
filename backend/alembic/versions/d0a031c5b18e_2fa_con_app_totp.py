"""2FA con app (TOTP) para los usuarios

Revision ID: d0a031c5b18e
Revises: 3b0b6642a702
Create Date: 2026-09-10

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd0a031c5b18e'
down_revision = '3b0b6642a702'
branch_labels = None
depends_on = None


def upgrade():
    # Secreto pendiente hasta activar; códigos de respaldo como hashes en JSON.
    op.execute("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)")
    op.execute("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS totp_habilitado BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS totp_respaldo_hash TEXT")


def downgrade():
    op.execute("ALTER TABLE usuario DROP COLUMN IF EXISTS totp_respaldo_hash")
    op.execute("ALTER TABLE usuario DROP COLUMN IF EXISTS totp_habilitado")
    op.execute("ALTER TABLE usuario DROP COLUMN IF EXISTS totp_secret")
