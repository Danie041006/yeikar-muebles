"""credenciales webauthn (huella / passkeys)

Revision ID: e6f42bb70a1d
Revises: d0a031c5b18e
Create Date: 2026-09-10

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e6f42bb70a1d'
down_revision = 'd0a031c5b18e'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS credencial_webauthn (
            id BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
            credential_id VARCHAR(300) UNIQUE,
            llave_publica TEXT NOT NULL,
            contador BIGINT DEFAULT 0,
            dispositivo VARCHAR(100),
            activa BOOLEAN DEFAULT TRUE,
            creado_en TIMESTAMP DEFAULT now(),
            ultimo_uso TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_credential_webauthn_usuario_id ON credencial_webauthn (usuario_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_credential_webauthn_activa ON credencial_webauthn (activa)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS credencial_webauthn")
