"""optimizacion_indices

Índices de rendimiento (Fase 1):
  - FKs de tablas hijas (hoy full-scan en cada detalle/agregación)
  - encabezados por cliente/proveedor (expediente)
  - filtros por estado (tabs de la UI, igualdad exacta)
  - compuestos (fecha, id) para el ORDER BY fecha DESC, id DESC de las listas

Revision ID: b518384162af
Revises: f1a2b3c4d5e6
Create Date: 2026-08-25 10:36:04.471947

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b518384162af'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabla, nombre del índice, [columnas])
INDICES = [
    # ── FKs de tablas hijas ──────────────────────────────────────────────
    ("detalle_pedido", "ix_detalle_pedido_pedido_id", ["pedido_id"]),
    ("detalle_cotizacion", "ix_detalle_cotizacion_cotizacion_id", ["cotizacion_id"]),
    ("detalle_venta", "ix_detalle_venta_venta_id", ["venta_id"]),
    ("detalle_factura", "ix_detalle_factura_factura_id", ["factura_id"]),
    ("pago", "ix_pago_venta_id", ["venta_id"]),
    ("etapa_produccion", "ix_etapa_produccion_orden_id", ["orden_produccion_id"]),
    ("etapa_produccion", "ix_etapa_produccion_area_id", ["area_id"]),
    ("consumo_material", "ix_consumo_material_etapa_id", ["etapa_produccion_id"]),
    ("consumo_material", "ix_consumo_material_material_id", ["material_id"]),
    ("mano_obra", "ix_mano_obra_etapa_id", ["etapa_produccion_id"]),
    ("movimiento_inventario", "ix_movimiento_inventario_material_id", ["material_id"]),
    ("movimiento_inventario", "ix_movimiento_inventario_ubicacion_id", ["ubicacion_id"]),
    ("gasto", "ix_gasto_tipo_gasto_id", ["tipo_gasto_id"]),
    ("movimiento_caja", "ix_movimiento_caja_metodo_caja_id", ["metodo_caja_id"]),
    ("detalle_compra", "ix_detalle_compra_compra_id", ["compra_id"]),
    ("detalle_compra", "ix_detalle_compra_material_id", ["material_id"]),
    # ── Encabezados por cliente/proveedor (expediente) ───────────────────
    ("pedido", "ix_pedido_cliente_id", ["cliente_id"]),
    ("cotizacion", "ix_cotizacion_cliente_id", ["cliente_id"]),
    ("venta", "ix_venta_cliente_id", ["cliente_id"]),
    ("factura", "ix_factura_cliente_id", ["cliente_id"]),
    ("compra", "ix_compra_proveedor_id", ["proveedor_id"]),
    # ── Filtros por estado (tabs por igualdad exacta) ────────────────────
    ("envio", "ix_envio_estado", ["estado"]),
    ("envio", "ix_envio_empleado_id", ["empleado_id"]),
    ("orden_produccion", "ix_orden_produccion_estado", ["estado"]),
    ("venta", "ix_venta_estado", ["estado"]),
    ("factura", "ix_factura_estado", ["estado"]),
    ("factura", "ix_factura_pedido_id", ["pedido_id"]),
    ("compra", "ix_compra_estado", ["estado"]),
    # ── Compuestos (fecha, id) para ORDER BY fecha DESC, id DESC ─────────
    ("pedido", "ix_pedido_fecha_id", ["fecha", "id"]),
    ("cotizacion", "ix_cotizacion_fecha_id", ["fecha", "id"]),
    ("venta", "ix_venta_fecha_id", ["fecha", "id"]),
    ("gasto", "ix_gasto_fecha", ["fecha"]),
    ("movimiento_caja", "ix_movimiento_caja_fecha", ["fecha"]),
    ("compra", "ix_compra_fecha_id", ["fecha", "id"]),
]


def upgrade() -> None:
    for tabla, nombre, columnas in INDICES:
        op.create_index(nombre, tabla, columnas, unique=False)


def downgrade() -> None:
    for tabla, nombre, columnas in reversed(INDICES):
        op.drop_index(nombre, table_name=tabla)
