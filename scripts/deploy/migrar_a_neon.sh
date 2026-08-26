#!/usr/bin/env bash
# =============================================================================
# migrar_a_neon.sh — copia la base de datos local de YEIKAR a Neon (Postgres).
#
# Uso:
#   ./scripts/deploy/migrar_a_neon.sh "CADENA_POOLED_DE_NEON"
#
# Ejemplo de cadena Neon (proyecto → Dashboard → Connection string, modo POOLED):
#   postgresql://usuario:password@ep-xxxx-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
#
# Qué hace:
#   1. pg_dump local (incluye TODO: usuarios, roles, estructuras, fotos bytea)
#   2. pg_restore en Neon (--clean --if-exists: se puede re-ejecutar)
#   3. Verifica alembic y conteos clave
# =============================================================================
set -euo pipefail

LOCAL_DB="${LOCAL_DB:-postgresql://yeikar:yeikar123@localhost:5432/yeikar}"
NEON_URL="${1:-}"
[ -n "$NEON_URL" ] || { echo "Uso: $0 <cadena_pooled_de_neon>"; exit 1; }
[[ "$NEON_URL" == *sslmode=* ]] || NEON_URL="${NEON_URL}?sslmode=require"

command -v pg_dump >/dev/null || { echo "Falta pg_dump"; exit 1; }

DUMP="$(mktemp -u /tmp/yeikar_neon_XXXX).dump"
echo "► 1/3 Volcando BD local…"
pg_dump --format=custom --no-owner --no-privileges --file "$DUMP" "$LOCAL_DB"
echo "   $(du -h "$DUMP" | cut -f1) volcados"

echo "► 2/3 Restaurando en Neon…"
pg_restore --no-owner --no-privileges --clean --if-exists \
  --dbname="$NEON_URL" --jobs=4 "$DUMP" 2>&1 | grep -vE "^pg_restore: (warning|error: could not execute query: ERROR:  (must be owner|role))" || true

rm -f "$DUMP"

echo "► 3/3 Verificación…"
export PGPASSWORD=""
psql "$NEON_URL" -tAc "SELECT 'tablas: ' || count(*) FROM information_schema.tables WHERE table_schema='public'" | sed 's/^/   /'
psql "$NEON_URL" -tAc "SELECT 'usuarios: ' || count(*) FROM usuario" | sed 's/^/   /'
psql "$NEON_URL" -tAc "SELECT 'productos: ' || count(*) FROM producto" | sed 's/^/   /'
psql "$NEON_URL" -tAc "SELECT 'alembic: ' || version_num FROM alembic_version" | sed 's/^/   /'

cat <<'MSG'

✔ Migración lista. Siguiente paso: correr migraciones pendientes si las hubiera
  DATABASE_URL="<cadena_neon>" alembic upgrade head
MSG
