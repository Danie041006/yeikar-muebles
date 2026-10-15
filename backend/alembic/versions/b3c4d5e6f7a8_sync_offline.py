"""sync offline: bitácora de cambios + operaciones idempotentes

Crea `sync_cambio` (bitácora con cursor monótono) y `sync_operacion`
(idempotencia del push) y adjunta un trigger AFTER INSERT/UPDATE/DELETE a
todas las tablas de negocio. Los triggers son la única fuente confiable de
tombstones: capturan cascadas de FK y borrados masivos que los eventos ORM
no ven. Tablas internas/de seguridad quedan excluidas.

Revision ID: b3c4d5e6f7a8
Revises: y2z3a4b5c6d7
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'y2z3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tablas que NO se replican a los dispositivos: internas, de seguridad o la
# propia infraestructura de sincronización.
TABLAS_EXCLUIDAS = {
    "alembic_version",
    "sync_cambio",
    "sync_operacion",
    "audit_event",
    "refresh_token",
    "login_intento",
    "sesion",
    "credencial_webauthn",
}

FUNCION_TRIGGER = """
CREATE OR REPLACE FUNCTION sync_registrar_cambio() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO sync_cambio (tabla, pk, op) VALUES (TG_TABLE_NAME, OLD.id::text, 'D');
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN
        RETURN NEW;
    END IF;
    INSERT INTO sync_cambio (tabla, pk, op)
    VALUES (TG_TABLE_NAME, NEW.id::text, CASE TG_OP WHEN 'INSERT' THEN 'I' ELSE 'U' END);
    RETURN NEW;
END;
$$;
"""


def _tablas_con_trigger(bind) -> list[str]:
    filas = bind.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )).fetchall()
    return sorted(t for (t,) in filas if t not in TABLAS_EXCLUIDAS)


def upgrade() -> None:
    op.create_table(
        'sync_cambio',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True, index=True),
        sa.Column('tabla', sa.String(80), nullable=False),
        sa.Column('pk', sa.String(64), nullable=False),
        sa.Column('op', sa.String(1), nullable=False),
        sa.Column('ocurrido_en', sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_index('ix_sync_cambio_tabla_pk', 'sync_cambio', ['tabla', 'pk'])
    op.create_table(
        'sync_operacion',
        sa.Column('operacion_id', sa.String(36), primary_key=True),
        sa.Column('usuario_id', sa.BigInteger(), sa.ForeignKey('usuario.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('tipo', sa.String(120), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False, server_default='EN_PROCESO'),
        sa.Column('resultado', sa.JSON(), nullable=True),
        sa.Column('ocurrida_en', sa.DateTime(), nullable=True),
        sa.Column('aplicada_en', sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
    )

    bind = op.get_bind()
    bind.execute(text(FUNCION_TRIGGER))
    for tabla in _tablas_con_trigger(bind):
        bind.execute(text(
            f'CREATE TRIGGER trg_sync_cambio AFTER INSERT OR UPDATE OR DELETE '
            f'ON "{tabla}" FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio()'
        ))


def downgrade() -> None:
    bind = op.get_bind()
    for tabla in _tablas_con_trigger(bind):
        bind.execute(text(f'DROP TRIGGER IF EXISTS trg_sync_cambio ON "{tabla}"'))
    bind.execute(text('DROP FUNCTION IF EXISTS sync_registrar_cambio()'))
    op.drop_table('sync_cambio')
    op.drop_table('sync_operacion')
