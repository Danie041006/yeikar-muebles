"""descripcion en lineas de venta (items a medida)

Revision ID: 2826f753ef1e
Revises: 5f2ca5d973c5
Create Date: 2026-09-10

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '2826f753ef1e'
down_revision = '5f2ca5d973c5'
branch_labels = None
depends_on = None


def upgrade():
    # Las ventas de items a medida (notas históricas migradas) no tienen
    # producto: la descripción vive en el pedido y se copia aquí para
    # mostrarla en cobros. IF NOT EXISTS + WHERE NULL: idempotente si la
    # columna o el backfill ya se aplicaron con SQL directo.
    op.execute(
        "ALTER TABLE detalle_venta "
        "ADD COLUMN IF NOT EXISTS descripcion_especifica TEXT"
    )
    op.execute(
        """
        UPDATE detalle_venta dv SET descripcion_especifica = src.descripcion
        FROM (
            SELECT dv2.id AS dv_id, (
                SELECT dp.descripcion_especifica
                FROM detalle_pedido dp
                JOIN venta v ON v.id = dv2.venta_id
                WHERE dp.pedido_id = v.pedido_id
                  AND dp.cantidad = dv2.cantidad
                  AND dp.precio = dv2.precio
                  AND dp.tipo_item = dv2.tipo_item
                  AND dp.descripcion_especifica IS NOT NULL
                ORDER BY dp.id LIMIT 1
            ) AS descripcion
            FROM detalle_venta dv2
            WHERE dv2.descripcion_especifica IS NULL
              AND dv2.producto_id IS NULL
        ) AS src
        WHERE dv.id = src.dv_id AND src.descripcion IS NOT NULL
        """
    )


def downgrade():
    op.execute("ALTER TABLE detalle_venta DROP COLUMN IF EXISTS descripcion_especifica")
