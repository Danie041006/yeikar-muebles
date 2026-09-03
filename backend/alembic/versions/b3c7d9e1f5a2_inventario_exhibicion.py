"""productos de exhibición: ubicación EXHIBICIÓN + tipo PIEZA ÚNICA

Revision ID: b3c7d9e1f5a2
Revises: f6a7b8c9d0e3
Create Date: 2026-08-31

Fase 1 del módulo de piezas de exhibición:
- Ubicación "EXHIBICIÓN" (tipo PUNTO_VENTA): el stock de piezas de exhibición
  vive en `producto_inventario` apuntando a esta ubicación. El CHECK de la
  tabla solo permite DEPOSITO/TALLER/PUNTO_VENTA y un showroom es un punto
  de venta; las compras de material solo buscan tipo DEPOSITO
  (purchases/service.py), así que no interfiere con ningún flujo automático.
- Tipo de producto "PIEZA ÚNICA": para piezas fabricadas solo para mostrar
  que no corresponden a un producto del catálogo.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "b3c7d9e1f5a2"
down_revision: Union[str, None] = "f6a7b8c9d0e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existe_ubicacion(conn, nombre: str):
    return conn.execute(text("SELECT id FROM ubicacion WHERE nombre = :n"), {"n": nombre}).first()


def _existe_tipo(conn, nombre: str):
    return conn.execute(text("SELECT id FROM tipo_producto WHERE nombre = :n"), {"n": nombre}).first()


def upgrade() -> None:
    conn = op.get_bind()

    if not _existe_ubicacion(conn, "EXHIBICIÓN"):
        conn.execute(
            text(
                "INSERT INTO ubicacion (nombre, descripcion, tipo, activo) "
                "VALUES ('EXHIBICIÓN', 'Showroom: piezas de exhibición (no rotan como venta normal)', 'PUNTO_VENTA', TRUE)"
            )
        )

    if not _existe_tipo(conn, "PIEZA ÚNICA"):
        conn.execute(text("INSERT INTO tipo_producto (nombre) VALUES ('PIEZA ÚNICA')"))


def downgrade() -> None:
    conn = op.get_bind()

    # FK RESTRICT impide borrar si ya tienen stock/productos asociados: se
    # deja el catálogo en paz en ese caso.
    ubi = _existe_ubicacion(conn, "EXHIBICIÓN")
    if ubi:
        en_uso = conn.execute(
            text("SELECT 1 FROM producto_inventario WHERE ubicacion_id = :i LIMIT 1"), {"i": ubi[0]}
        ).first()
        if not en_uso:
            conn.execute(text("DELETE FROM ubicacion WHERE id = :i"), {"i": ubi[0]})

    tipo = _existe_tipo(conn, "PIEZA ÚNICA")
    if tipo:
        en_uso = conn.execute(
            text("SELECT 1 FROM producto WHERE tipo_producto_id = :i LIMIT 1"), {"i": tipo[0]}
        ).first()
        if not en_uso:
            conn.execute(text("DELETE FROM tipo_producto WHERE id = :i"), {"i": tipo[0]})
