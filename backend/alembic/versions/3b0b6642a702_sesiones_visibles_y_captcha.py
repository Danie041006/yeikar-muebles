"""sesiones visibles y captcha

Revision ID: 3b0b6642a702
Revises: 2826f753ef1e
Create Date: 2026-09-10

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '3b0b6642a702'
down_revision = '2826f753ef1e'
branch_labels = None
depends_on = None


def upgrade():
    # Un login = una sesión visible (equipo, IP, último uso). Su revocación
    # apaga el refresh token enlazado. IF NOT EXISTS: idempotente si la tabla
    # ya se creó con SQL directo.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sesion (
            id BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
            refresh_token_id BIGINT REFERENCES refresh_token(id) ON DELETE CASCADE,
            ip VARCHAR(45),
            user_agent VARCHAR(300),
            revocada BOOLEAN DEFAULT FALSE,
            creado_en TIMESTAMP DEFAULT now(),
            ultimo_uso TIMESTAMP DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_sesion_usuario_id ON sesion (usuario_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sesion_revocada ON sesion (revocada)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sesion_refresh_token_id ON sesion (refresh_token_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS sesion")
