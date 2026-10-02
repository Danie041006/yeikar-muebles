"""cuentas por persona (Banesco Jackson, Bancolombia Andrea/Karolay) + quitar CHECK de metodo_pago

Revision ID: d5e6f7a8b9c0
Revises: d68c00cfa34e
Create Date: 2026-10-02

1) Se siembran 3 cuentas reales del negocio:
   - BANESCO_JACKSON (VES)
   - BANCOLOMBIA_ANDREA (COP)
   - BANCOLOMBIA_KAROLAY (COP)
   Idempotente: si el código ya existe no se toca. No se inventa saldo:
   cada cuenta arranca en 0 y su saldo real se carga con movimientos.

2) Se elimina el CHECK fijo `pago_metodo_pago_check`: el catálogo
   `metodo_caja` pasa a ser la fuente de verdad. El backend valida que el
   método exista, esté activo y que su moneda propia coincida con la del
   pago (sales/service.py), así que cualquier cuenta del catálogo sirve
   para cobrar sin migrar el CHECK cada vez que se crea una cuenta nueva.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "d68c00cfa34e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CUENTAS = [
    ("Banesco Jackson", "BANESCO_JACKSON", "VES", 20),
    ("Bancolombia Andrea", "BANCOLOMBIA_ANDREA", "COP", 21),
    ("Bancolombia Karolay", "BANCOLOMBIA_KAROLAY", "COP", 22),
]

METODOS_LEGACY = (
    "'EFECTIVO_COP','EFECTIVO_USD','EFECTIVO_VES','BANCOLOMBIA',"
    "'BANCARIBE','ZELLE','BINANCE','NEQUI','SOFITASA','BANESCO'"
)


def _moneda_id(conn, codigo: str) -> int:
    row = conn.execute(
        text("SELECT id FROM moneda WHERE codigo = :c"), {"c": codigo}
    ).first()
    if not row:
        raise RuntimeError(f"No existe la moneda {codigo} en el catálogo")
    return row[0]


def upgrade() -> None:
    conn = op.get_bind()

    for nombre, codigo, moneda_codigo, orden in CUENTAS:
        existe = conn.execute(
            text("SELECT 1 FROM metodo_caja WHERE codigo = :c"), {"c": codigo}
        ).first()
        if existe:
            continue
        conn.execute(
            text(
                "INSERT INTO metodo_caja (nombre, codigo, activo, orden, moneda_id) "
                "VALUES (:n, :c, true, :o, :m)"
            ),
            {
                "n": nombre,
                "c": codigo,
                "o": orden,
                "m": _moneda_id(conn, moneda_codigo),
            },
        )

    tiene_check = conn.execute(
        text(
            "SELECT 1 FROM pg_constraint "
            "WHERE conrelid = 'pago'::regclass AND conname = 'pago_metodo_pago_check'"
        )
    ).first()
    if tiene_check:
        op.execute("ALTER TABLE pago DROP CONSTRAINT pago_metodo_pago_check")


def downgrade() -> None:
    conn = op.get_bind()

    # El CHECK solo se puede restaurar si ningún pago usa un código fuera
    # de la lista histórica (las cuentas nuevas quedan sin restricción).
    fuera = conn.execute(
        text(f"SELECT 1 FROM pago WHERE metodo_pago NOT IN ({METODOS_LEGACY}) LIMIT 1")
    ).first()
    if not fuera:
        existe_check = conn.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conrelid = 'pago'::regclass AND conname = 'pago_metodo_pago_check'"
            )
        ).first()
        if not existe_check:
            op.execute(
                "ALTER TABLE pago ADD CONSTRAINT pago_metodo_pago_check CHECK "
                f"(metodo_pago IN ({METODOS_LEGACY}))"
            )

    for _nombre, codigo, _moneda_codigo, _orden in CUENTAS:
        conn.execute(
            text(
                "DELETE FROM metodo_caja "
                "WHERE codigo = :c AND NOT EXISTS ("
                "  SELECT 1 FROM movimiento_caja m WHERE m.metodo_caja_id = metodo_caja.id"
                ")"
            ),
            {"c": codigo},
        )
