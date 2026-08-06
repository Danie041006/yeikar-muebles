"""habilita lectura compartida de catálogos operativos.

Revision ID: e0f1a2b3c4d5
Revises: d9e8f7a6b5c4
Create Date: 2026-08-06
"""

from alembic import op
from sqlalchemy import text


revision = "e0f1a2b3c4d5"
down_revision = "d9e8f7a6b5c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # La fila presente en rol_modulo hace que el frontend pueda distinguir
    # lectura de gestión sin esconder catálogos que el trabajo necesita.
    conn.execute(
        text(
            "INSERT INTO rol_modulo (rol_id, modulo, gestionar) "
            "SELECT r.id, catalogo.modulo, FALSE "
            "FROM rol r "
            "CROSS JOIN (VALUES ('clientes'), ('productos'), ('materiales'), ('tasas'), ('catalogos')) AS catalogo(modulo) "
            "WHERE r.nombre NOT IN ('Dueño', 'Administrador') "
            "ON CONFLICT (rol_id, modulo) DO NOTHING"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            "DELETE FROM rol_modulo "
            "WHERE modulo IN ('clientes', 'productos', 'materiales', 'tasas', 'catalogos') "
            "AND rol_id IN (SELECT id FROM rol WHERE nombre NOT IN ('Dueño', 'Administrador'))"
        )
    )
