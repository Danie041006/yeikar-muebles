"""captura flexible de insumos en cotización/pedido/venta (cm ↔ m³)

Revision ID: h1i2j3k4l5m6
Revises: g5c6d7e8f9a0

La madera se compra/inventaría en m³ pero se cotiza al cliente en cm (cuenta
del taller). El renglón guarda la cantidad/precio en la unidad vendida y
`cantidad_base` en la unidad del inventario para costos y stock. Se amplían
las cantidades a 4 decimales para aceptar 0,1128 m³ sin redondear a 0,11.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, None] = "g5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLAS_DETALLE = ("detalle_cotizacion", "detalle_pedido", "detalle_venta")
TABLAS_CANTIDAD_4 = TABLAS_DETALLE + ("detalle_factura",)


def upgrade() -> None:
    # 1) Unidad de captura + equivalencia en la unidad base del inventario.
    for tabla in TABLAS_DETALLE:
        op.add_column(tabla, sa.Column("unidad_captura", sa.String(length=4), nullable=True))
        op.add_column(tabla, sa.Column("cantidad_base", sa.Numeric(14, 4), nullable=True))

    # 2) Cantidades con 4 decimales: 0,1128 m³ no cabe en NUMERIC(10,2).
    for tabla in TABLAS_CANTIDAD_4:
        op.alter_column(tabla, "cantidad", type_=sa.Numeric(14, 4))

    # 3) Compatibilidad: los renglones históricos no tienen captura; su
    #    cantidad ya estaba en la unidad base, así que esa es su equivalencia.
    for tabla in TABLAS_DETALLE:
        op.execute(
            f"UPDATE {tabla} SET cantidad_base = cantidad "
            "WHERE tipo_item = 'INSUMO' AND cantidad_base IS NULL"
        )


def downgrade() -> None:
    for tabla in TABLAS_CANTIDAD_4:
        op.alter_column(
            tabla,
            "cantidad",
            type_=sa.Numeric(10, 2),
            postgresql_using="cantidad::numeric(10,2)",
        )
    for tabla in TABLAS_DETALLE:
        op.drop_column(tabla, "cantidad_base")
        op.drop_column(tabla, "unidad_captura")
