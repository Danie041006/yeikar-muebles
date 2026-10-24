"""inventario de oficina: departamento OFICINA, categoría y consumido_por

Revision ID: of1c2i3n4a5b6
Revises: pc1o2r3r4e5c
Create Date: 2026-10-23

- Agrega `OFICINA` a los departamentos válidos de materiales (papelería,
  cafetería, aseo de oficina...). Los ítems de oficina son MATERIALES: entran
  por compra y salen por consumo. Así reutilizan kardex, alertas, costos y el
  Libro de Entradas y Salidas en vez de duplicar un inventario aparte.
- Siembra la categoría de inventario PAPELERÍA DE OFICINA (tipo MATERIAL) y
  clasifica allí los materiales que ya la usen.
- Agrega `movimiento_inventario.consumido_por`: en una SALIDA de oficina queda
  quién recibió/consumió el ítem (texto libre). En una ENTRADA se sigue usando
  `recibido_por` (quién trajo la compra).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "of1c2i3n4a5b6"
down_revision: Union[str, None] = "pc1o2r3r4e5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEPARTAMENTOS = (
    "EBANISTERIA",
    "PREPARACION",
    "PINTURA",
    "TAPICERIA",
    "VIDRIERIA",
    "TERMINACION",
    "OFICINA",
)
CATEGORIA = "PAPELERÍA DE OFICINA"


def upgrade() -> None:
    op.add_column(
        "movimiento_inventario",
        sa.Column("consumido_por", sa.String(150), nullable=True),
    )

    # El CHECK original solo permitía los 6 departamentos del taller.
    op.drop_constraint("material_departamento_check", "material", type_="check")
    deptos_sql = ", ".join(f"'{d}'" for d in DEPARTAMENTOS)
    op.create_check_constraint(
        "material_departamento_check",
        "material",
        f"departamento IS NULL OR departamento IN ({deptos_sql})",
    )

    # El movimiento también valida la zona y la cantidad. La cantidad se abre
    # a >= 0 para que el conteo físico pueda dejar un ítem en 0 (el service
    # sigue rechazando 0 en ENTRADA/SALIDA/DAÑO/DEVOLUCION).
    op.drop_constraint("movimiento_inventario_departamento_check", "movimiento_inventario", type_="check")
    op.create_check_constraint(
        "movimiento_inventario_departamento_check",
        "movimiento_inventario",
        f"departamento IS NULL OR departamento IN ({deptos_sql})",
    )
    op.drop_constraint("movimiento_inventario_cantidad_check", "movimiento_inventario", type_="check")
    op.create_check_constraint(
        "movimiento_inventario_cantidad_check",
        "movimiento_inventario",
        "cantidad >= 0",
    )

    conn = op.get_bind()
    existe = conn.execute(
        text(
            "SELECT id FROM categoria_inventario "
            "WHERE tipo = 'MATERIAL' AND UPPER(nombre) LIKE '%OFICINA%' "
            "ORDER BY id LIMIT 1"
        )
    ).fetchone()
    if existe is None:
        conn.execute(
            text(
                "INSERT INTO categoria_inventario (nombre, tipo, orden, activo) "
                "VALUES (:nombre, 'MATERIAL', 90, true)"
            ),
            {"nombre": CATEGORIA},
        )

    # Los materiales que ya estaban en una categoría de oficina pasan a
    # departamento OFICINA para que aparezcan en la pestaña nueva.
    conn.execute(
        text(
            "UPDATE material SET departamento = 'OFICINA' "
            "WHERE departamento IS NULL AND categoria_inventario_id IN ("
            "  SELECT id FROM categoria_inventario "
            "  WHERE tipo = 'MATERIAL' AND UPPER(nombre) LIKE '%OFICINA%'"
            ")"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("UPDATE material SET departamento = NULL WHERE departamento = 'OFICINA'"))
    conn.execute(text("UPDATE movimiento_inventario SET departamento = NULL WHERE departamento = 'OFICINA'"))

    op.drop_constraint("material_departamento_check", "material", type_="check")
    deptos_sql = ", ".join(f"'{d}'" for d in DEPARTAMENTOS if d != "OFICINA")
    op.create_check_constraint(
        "material_departamento_check",
        "material",
        f"departamento IS NULL OR departamento IN ({deptos_sql})",
    )

    op.drop_constraint("movimiento_inventario_departamento_check", "movimiento_inventario", type_="check")
    op.create_check_constraint(
        "movimiento_inventario_departamento_check",
        "movimiento_inventario",
        f"departamento IS NULL OR departamento IN ({deptos_sql})",
    )
    op.drop_constraint("movimiento_inventario_cantidad_check", "movimiento_inventario", type_="check")
    op.create_check_constraint(
        "movimiento_inventario_cantidad_check",
        "movimiento_inventario",
        "cantidad > 0",
    )

    conn.execute(
        text(
            "DELETE FROM categoria_inventario "
            "WHERE tipo = 'MATERIAL' AND UPPER(nombre) LIKE '%OFICINA%' "
            "AND NOT EXISTS (SELECT 1 FROM material WHERE categoria_inventario_id = categoria_inventario.id)"
        )
    )
    op.drop_column("movimiento_inventario", "consumido_por")
