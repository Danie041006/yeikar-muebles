"""movimiento_caja: persona o entidad (contraparte) y concepto (antes observaciones).

El libro de caja siempre nombra a la otra parte del movimiento: quien entrega
el dinero (entrada) o quien lo recibe (salida). No es quien registra (eso es
`usuario_id`). Se agrega `persona_entidad` como texto libre OPCIONAL, porque
puede ser cliente, proveedor, empleado, familiar, etc.

`observaciones` pasa a llamarse `concepto`: es la razón del movimiento y es
la palabra que el taller entiende mejor.

Backfill:
  - Filas importadas del libro ("[Libro ...] TIPO · CONCEPTO") → TIPO.
  - Cobros ("Cobro de CLIENTE · Venta #N") → CLIENTE.
  - Compras ("Compra #N a PROVEEDOR") → PROVEEDOR.
  - Abonos de cuentas por pagar ("CxP #N abono #M") → proveedor de la deuda.

Revision ID: p9q0r1s2t3u4
Revises: k3l4m5n6o7p8
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "p9q0r1s2t3u4"
down_revision = "k3l4m5n6o7p8"
branch_labels = None
depends_on = None


def _existe_columna(conn, tabla: str, columna: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ),
            {"t": tabla, "c": columna},
        ).first()
    )


def upgrade() -> None:
    conn = op.get_bind()

    if not _existe_columna(conn, "movimiento_caja", "persona_entidad"):
        op.add_column(
            "movimiento_caja",
            sa.Column("persona_entidad", sa.String(length=150), nullable=True),
        )

    if _existe_columna(conn, "movimiento_caja", "observaciones"):
        op.alter_column(
            "movimiento_caja",
            "observaciones",
            new_column_name="concepto",
            existing_type=sa.Text(),
        )

    # 1. Filas del libro importado: "[Libro X] TIPO · CONCEPTO" → TIPO.
    conn.execute(
        text(
            """
            UPDATE movimiento_caja
            SET persona_entidad = NULLIF(
                btrim(CASE WHEN s.tipo = 'Gasto' THEN '' ELSE s.tipo END), ''
            )
            FROM (
                SELECT id,
                       split_part(
                           substring(concepto FROM '^\\[Libro [^\\]]+\\] *(.*)$'),
                           ' ·', 1
                       ) AS tipo
                FROM movimiento_caja
                WHERE concepto LIKE '[Libro %'
            ) s
            WHERE movimiento_caja.id = s.id
              AND movimiento_caja.persona_entidad IS NULL
            """
        )
    )

    # 2. Cobros: "Cobro de CLIENTE · Venta #N" → CLIENTE.
    conn.execute(
        text(
            """
            UPDATE movimiento_caja
            SET persona_entidad = NULLIF(
                btrim(split_part(substring(concepto FROM '^Cobro de (.*)$'), ' ·', 1)), ''
            )
            WHERE persona_entidad IS NULL
              AND concepto LIKE 'Cobro de %'
            """
        )
    )

    # 3. Compras: "Compra #N a PROVEEDOR" → PROVEEDOR.
    conn.execute(
        text(
            """
            UPDATE movimiento_caja
            SET persona_entidad = NULLIF(btrim(substring(concepto FROM ' a (.*)$')), '')
            WHERE persona_entidad IS NULL
              AND concepto LIKE 'Compra #% a %'
            """
        )
    )

    # 4. Abonos de cuentas por pagar: el proveedor de la deuda.
    conn.execute(
        text(
            """
            UPDATE movimiento_caja m
            SET persona_entidad = p.nombre
            FROM cuenta_por_pagar c
            JOIN proveedor p ON p.id = c.proveedor_id
            WHERE m.persona_entidad IS NULL
              AND m.referencia ~ '^CxP #[0-9]+ '
              AND c.id = (split_part(split_part(m.referencia, '#', 2), ' ', 1))::bigint
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    if _existe_columna(conn, "movimiento_caja", "concepto"):
        op.alter_column(
            "movimiento_caja",
            "concepto",
            new_column_name="observaciones",
            existing_type=sa.Text(),
        )
    if _existe_columna(conn, "movimiento_caja", "persona_entidad"):
        op.drop_column("movimiento_caja", "persona_entidad")
