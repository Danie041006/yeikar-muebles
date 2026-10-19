"""fix trigger sync: comparar filas como jsonb (soporta columnas json)

El trigger `sync_registrar_cambio` usaba `NEW IS NOT DISTINCT FROM OLD` para
saltarse updates que no cambian nada. Esa comparación exige operador de
igualdad por TIPO de columna, y el tipo `json` de PostgreSQL NO tiene uno:
cualquier UPDATE a una tabla con columnas json (p. ej. `producto_material`
con `condicion_activacion`/`rangos`) fallaba con
"could not identify an equality operator for type json".

Fix: comparar `to_jsonb(NEW) IS NOT DISTINCT FROM to_jsonb(OLD)` — semántica
idéntica (misma fila completa) y funciona con cualquier tipo de columna.

Revision ID: g5c6d7e8f9a0
Revises: f4b5c6d7e8f9
Create Date: 2026-10-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'g5c6d7e8f9a0'
down_revision: Union[str, None] = 'f4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FUNCION_TRIGGER = """
CREATE OR REPLACE FUNCTION sync_registrar_cambio() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO sync_cambio (tabla, pk, op) VALUES (TG_TABLE_NAME, OLD.id::text, 'D');
        RETURN OLD;
    END IF;
    -- to_jsonb: la comparación de fila completa funciona con columnas json
    -- (el operador de igualdad directo NEW IS NOT DISTINCT FROM OLD falla
    -- para el tipo json, que no tiene equality operator).
    IF TG_OP = 'UPDATE' AND to_jsonb(NEW) IS NOT DISTINCT FROM to_jsonb(OLD) THEN
        RETURN NEW;
    END IF;
    INSERT INTO sync_cambio (tabla, pk, op)
    VALUES (TG_TABLE_NAME, NEW.id::text, CASE TG_OP WHEN 'INSERT' THEN 'I' ELSE 'U' END);
    RETURN NEW;
END;
$$;
"""


def upgrade() -> None:
    op.execute(FUNCION_TRIGGER)


def downgrade() -> None:
    op.execute("""
CREATE OR REPLACE FUNCTION sync_registrar_cambio() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO sync_cambio (tabla, pk, op) VALUES (TG_TABLE_NAME, OLD.id::text, 'D');
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN
        RETURN NEW;
    END IF;
    INSERT INTO sync_cambio (tabla, pk, op)
    VALUES (TG_TABLE_NAME, NEW.id::text, CASE TG_OP WHEN 'INSERT' THEN 'I' ELSE 'U' END);
    RETURN NEW;
END;
$$;
""")
