"""detalle_cuenta_por_pagar: renglones de cada deuda (qué se compró y para quién)

Revision ID: o1p2q3r4s5t6
Revises: m1n2o3p4q5r6
Create Date: 2026-09-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'o1p2q3r4s5t6'
down_revision = 'm1n2o3p4q5r6'
branch_labels = None
depends_on = None


def upgrade():
    # IF NOT EXISTS: la tabla pudo crearse con SQL directo en producción antes
    # de registrar la revisión; el resto de migraciones de esta rama ya usan
    # este mismo patrón.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS detalle_cuenta_por_pagar (
            id BIGSERIAL PRIMARY KEY,
            cuenta_por_pagar_id BIGINT NOT NULL REFERENCES cuenta_por_pagar(id) ON DELETE CASCADE,
            orden INTEGER NOT NULL DEFAULT 0,
            descripcion VARCHAR(250),
            material_id BIGINT REFERENCES material(id) ON DELETE SET NULL,
            cantidad NUMERIC(12, 2) NOT NULL DEFAULT 1,
            precio_unitario NUMERIC(15, 2) NOT NULL DEFAULT 0,
            cliente_nombre VARCHAR(150),
            cliente_id BIGINT REFERENCES cliente(id) ON DELETE SET NULL,
            observaciones TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_detalle_cuenta_por_pagar_cuenta_por_pagar_id "
        "ON detalle_cuenta_por_pagar (cuenta_por_pagar_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_detalle_cuenta_por_pagar_material_id "
        "ON detalle_cuenta_por_pagar (material_id)"
    )


def downgrade():
    op.drop_index('ix_detalle_cuenta_por_pagar_material_id', table_name='detalle_cuenta_por_pagar')
    op.drop_index('ix_detalle_cuenta_por_pagar_cuenta_por_pagar_id', table_name='detalle_cuenta_por_pagar')
    op.drop_table('detalle_cuenta_por_pagar')