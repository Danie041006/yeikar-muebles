"""Adjuntar el trigger de sync offline a tablas que aún no lo tengan.

La migración `sync_offline` (b3c4d5e6f7a8) adjuntó `trg_sync_cambio` a todas
las tablas que existían en ese momento. Cuando se cree una tabla nueva en una
migración futura, ejecutar este script para sumarla a la réplica offline.
Idempotente: solo crea los triggers faltantes. Dry-run por defecto.

Ejecutar:
    cd backend && venv/bin/python scripts/adjuntar_triggers_sync.py          # dry-run
    cd backend && venv/bin/python scripts/adjuntar_triggers_sync.py --aplicar
"""

import argparse
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.main  # noqa: F401,E402
from app.db.session import engine  # noqa: E402

# Mismas exclusiones que la migración sync_offline.
TABLAS_EXCLUIDAS = {
    "alembic_version",
    "sync_cambio",
    "sync_operacion",
    "audit_event",
    "refresh_token",
    "login_intento",
    "sesion",
    "credencial_webauthn",
}


def main(aplicar: bool = False):
    with engine.begin() as conn:
        tablas = [
            t for (t,) in conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )).fetchall()
            if t not in TABLAS_EXCLUIDAS
        ]
        faltantes = [
            t for t in tablas
            if not conn.execute(text(
                "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_sync_cambio' "
                "AND tgrelid = to_regclass(:t) AND NOT tgisinternal"
            ), {"t": t}).first()
        ]

        if not faltantes:
            print(f"OK: las {len(tablas)} tablas elegibles ya tienen el trigger.")
            return

        print("Tablas sin trigger de sync:")
        for tabla in faltantes:
            print(f"  - {tabla}")

        if not aplicar:
            print("\n(dry-run: usa --aplicar para crear los triggers)")
            return

        for tabla in faltantes:
            conn.execute(text(
                f'CREATE TRIGGER trg_sync_cambio AFTER INSERT OR UPDATE OR DELETE '
                f'ON "{tabla}" FOR EACH ROW EXECUTE FUNCTION sync_registrar_cambio()'
            ))
        print(f"\nTriggers creados: {len(faltantes)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--aplicar", action="store_true")
    args = parser.parse_args()
    main(aplicar=args.aplicar)
