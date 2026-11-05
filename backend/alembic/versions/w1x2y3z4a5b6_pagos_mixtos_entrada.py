"""entradas de inventario: pagos mixtos de una compra (varias cuentas/monedas).

Una entrada puede pagarse de más de una manera (ej. la mitad en efectivo COP
y el resto por Zelle USD). Cada pago genera su propio Gasto + salida de caja
(la filosofía de "un Gasto espejo por cuenta" se mantiene) y queda registrado
en `entrada_compra_pago` para mostrar el desglose en el libro de entradas.

- movimiento_inventario_id: la entrada (protegida: CASCADE).
- gasto_id: el gasto de compra que este pago generó.
- metodo_caja_id: la cuenta de caja de la que salió el dinero.
- moneda_id + monto: lo pagado EN LA MONEDA de esa cuenta.
- tasa_cambio: "1 [moneda del pago] = X COP" congelada en el momento.
- monto_en_moneda_base: equivalente en COP (monto × tasa).

La primera entrada conserva su fila `movimiento_inventario.pago_*` heredada
(compatibilidad) apuntando al primer pago.

Revision ID: w1x2y3z4a5b6
Revises: u9n8i7f6g5a4
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = "w1x2y3z4a5b6"
down_revision = "u9n8i7f6g5a4"
branch_labels = None
depends_on = None


def _ya_existe(conn, tabla: str) -> bool:
    """Guard de idempotencia: la tabla puede existir ya (despliegue en dos
    ramas del repo o prueba local sin alembic)."""
    fila = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t"
        ),
        {"t": tabla},
    ).first()
    return fila is not None


def upgrade() -> None:
    conn = op.get_bind()
    if _ya_existe(conn, "entrada_compra_pago"):
        return
    op.create_table(
        "entrada_compra_pago",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "movimiento_inventario_id",
            sa.BigInteger(),
            sa.ForeignKey("movimiento_inventario.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "movimiento_producto_id",
            sa.BigInteger(),
            sa.ForeignKey("movimiento_producto_inventario.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "gasto_id",
            sa.BigInteger(),
            sa.ForeignKey("gasto.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "metodo_caja_id",
            sa.BigInteger(),
            sa.ForeignKey("metodo_caja.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "moneda_id",
            sa.BigInteger(),
            sa.ForeignKey("moneda.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False),
        sa.Column("tasa_cambio", sa.Numeric(15, 6), nullable=False, server_default="1"),
        sa.Column("monto_en_moneda_base", sa.Numeric(15, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_entrada_compra_pago_movimiento",
        "entrada_compra_pago",
        ["movimiento_inventario_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_entrada_compra_pago_movimiento", table_name="entrada_compra_pago")
    op.drop_table("entrada_compra_pago")
