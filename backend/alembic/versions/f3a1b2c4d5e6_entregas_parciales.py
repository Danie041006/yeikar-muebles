"""entregas parciales: varios despachos por pedido y detalle por ítem

Un pedido puede entregarse en varias tandas: el cliente se lleva lo que ya
está terminado aunque el resto siga en producción. `envio` deja de ser único
por pedido y cada despacho lleva sus propios renglones/piezas y cantidades.

Revision ID: f3a1b2c4d5e6
Revises: f8840b56521c
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a1b2c4d5e6"
down_revision: Union[str, None] = "f8840b56521c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Varios envíos por pedido: se cae el UNIQUE y se deja un índice normal.
    op.drop_constraint("envio_pedido_id_key", "envio", type_="unique")
    op.create_index("ix_envio_pedido_id", "envio", ["pedido_id"])

    # 2. Detalle del despacho: qué renglón/pieza y cuánta cantidad va en ESTE viaje.
    op.create_table(
        "envio_detalle",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("envio_id", sa.BigInteger(), nullable=False),
        sa.Column("detalle_pedido_id", sa.BigInteger(), nullable=False),
        sa.Column("orden_produccion_id", sa.BigInteger(), nullable=True),
        sa.Column("cantidad", sa.Numeric(14, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "cantidad > 0",
            name="ck_envio_detalle_cantidad_positiva",
        ),
        sa.ForeignKeyConstraint(
            ["envio_id"],
            ["envio.id"],
            name="fk_envio_detalle_envio",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["detalle_pedido_id"],
            ["detalle_pedido.id"],
            name="fk_envio_detalle_detalle_pedido",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["orden_produccion_id"],
            ["orden_produccion.id"],
            name="fk_envio_detalle_orden",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        # Una misma pieza no se repite dentro del mismo despacho.
        sa.UniqueConstraint(
            "envio_id",
            "detalle_pedido_id",
            "orden_produccion_id",
            name="uq_envio_detalle_item",
        ),
    )
    op.create_index("ix_envio_detalle_id", "envio_detalle", ["id"])
    op.create_index("ix_envio_detalle_envio_id", "envio_detalle", ["envio_id"])
    op.create_index(
        "ix_envio_detalle_detalle_pedido_id", "envio_detalle", ["detalle_pedido_id"]
    )
    op.create_index(
        "ix_envio_detalle_orden_produccion_id",
        "envio_detalle",
        ["orden_produccion_id"],
    )
    # El UNIQUE permite varios NULL; este índice parcial garantiza UNA fila por
    # renglón cuando el despacho no va atado a una orden (reventa/insumo/legacy).
    op.create_index(
        "uq_envio_detalle_sin_orden",
        "envio_detalle",
        ["envio_id", "detalle_pedido_id"],
        unique=True,
        postgresql_where=sa.text("orden_produccion_id IS NULL"),
    )

    # 3. Backfill: los envíos históricos cubrían el pedido completo. Se crea una
    # fila por renglón con su cantidad total para que el progreso y la guía
    # sigan funcionando igual.
    op.execute(
        """
        INSERT INTO envio_detalle
            (envio_id, detalle_pedido_id, orden_produccion_id, cantidad, created_at)
        SELECT e.id, dp.id, NULL, dp.cantidad, now()
        FROM envio e
        JOIN detalle_pedido dp ON dp.pedido_id = e.pedido_id
        WHERE NOT EXISTS (
            SELECT 1 FROM envio_detalle ed WHERE ed.envio_id = e.id
        )
        """
    )

    # 4. La tabla nueva entra a la réplica offline (misma función de sync).
    op.execute(
        'CREATE TRIGGER trg_sync_cambio AFTER INSERT OR UPDATE OR DELETE '
        'ON "envio_detalle" FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio()'
    )


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS trg_sync_cambio ON "envio_detalle"')
    op.drop_index("uq_envio_detalle_sin_orden", table_name="envio_detalle")
    op.drop_index("ix_envio_detalle_orden_produccion_id", table_name="envio_detalle")
    op.drop_index("ix_envio_detalle_detalle_pedido_id", table_name="envio_detalle")
    op.drop_index("ix_envio_detalle_envio_id", table_name="envio_detalle")
    op.drop_index("ix_envio_detalle_id", table_name="envio_detalle")
    op.drop_table("envio_detalle")

    op.drop_index("ix_envio_pedido_id", table_name="envio")
    # Si ya existen varios envíos por pedido, este UNIQUE fallará: hay que
    # consolidar los despachos antes de bajar la migración (no se borran datos
    # automáticamente para no perder evidencia de entregas).
    op.create_unique_constraint("envio_pedido_id_key", "envio", ["pedido_id"])
