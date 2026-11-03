"""gastos: unificar "Gasto de Casa" dentro de "Gasto Familiar".

Decisión de la dueña (03/11/2026): "gastos familiares" y "gastos de casa" son
la misma canasta. Queda una sola clasificación, GASTO_FAMILIAR ("Gasto
Familiar").

- gasto.clasificacion: GASTO_CASA → GASTO_FAMILIAR
- El tipo de gasto "Gasto de Casa" se repunta a "Gasto Familiar" (se crea si
  no existe) y se elimina del catálogo si queda sin uso, para que no siga
  apareciendo como una categoría aparte en los formularios.
- cuenta_por_pagar también se repunta.

El código "G C" del libro se sigue aceptando al importar, pero se guarda como
GASTO_FAMILIAR (ver `normalizar_clasificacion`).

Revision ID: u9n8i7f6g5a4
Revises: b2c3d4e5f6a7
Create Date: 2026-11-03
"""
from alembic import op
from sqlalchemy import text

revision = "u9n8i7f6g5a4"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Tipo de gasto destino (idempotente: puede existir ya con gastos).
    conn.execute(text(
        """
        INSERT INTO tipo_gasto (nombre, categoria)
        SELECT 'Gasto Familiar', 'OPERATIVO'
        WHERE NOT EXISTS (
            SELECT 1 FROM tipo_gasto WHERE lower(nombre) = lower('Gasto Familiar')
        )
        """
    ))

    # 2. Reclasificar y repuntar los gastos que eran de Casa (por clasificación
    #    o por tipo de gasto: hay filas con una sola de las dos marcas).
    conn.execute(text(
        """
        UPDATE gasto g
        SET clasificacion = 'GASTO_FAMILIAR',
            tipo_gasto_id = (
                SELECT tg.id FROM tipo_gasto tg
                WHERE lower(tg.nombre) = lower('Gasto Familiar')
                ORDER BY tg.id
                LIMIT 1
            )
        WHERE g.clasificacion = 'GASTO_CASA'
           OR g.tipo_gasto_id IN (
                SELECT tg.id FROM tipo_gasto tg
                WHERE lower(tg.nombre) = lower('Gasto de Casa')
           )
        """
    ))

    # 3. Cuentas por pagar que apuntaban al tipo viejo.
    conn.execute(text(
        """
        UPDATE cuenta_por_pagar c
        SET tipo_gasto_id = (
            SELECT tg.id FROM tipo_gasto tg
            WHERE lower(tg.nombre) = lower('Gasto Familiar')
            ORDER BY tg.id
            LIMIT 1
        )
        WHERE c.tipo_gasto_id IN (
            SELECT tg.id FROM tipo_gasto tg
            WHERE lower(tg.nombre) = lower('Gasto de Casa')
        )
        """
    ))

    # 4. Eliminar el tipo viejo si ya nadie lo usa.
    conn.execute(text(
        """
        DELETE FROM tipo_gasto tg
        WHERE lower(tg.nombre) = lower('Gasto de Casa')
          AND NOT EXISTS (SELECT 1 FROM gasto g WHERE g.tipo_gasto_id = tg.id)
          AND NOT EXISTS (
              SELECT 1 FROM cuenta_por_pagar c WHERE c.tipo_gasto_id = tg.id
          )
        """
    ))


def downgrade() -> None:
    # La fusión es de datos: no se puede saber qué gastos eran "Casa" antes.
    # Se deja documentado y sin reversa (los códigos "G C" del libro siguen
    # funcionando al importar y ahora se guardan como Familiar).
    pass
