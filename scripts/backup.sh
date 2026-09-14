#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────
# YEIKAR — Backup diario local de PostgreSQL
# Lo ejecuta el servicio "backup" (cron interno, 3:00 a. m. hora Venezuela).
#
# Qué hace:
#   1. pg_dump comprimido del día completo (incluye fotos/comprobantes
#      guardados como BLOB dentro de la BD).
#   2. Verifica que el dump se pueda LEER (un backup no verificado
#      es solo una esperanza).
#   3. Borra los dumps locales más viejos que RETENTION_DAYS.
#
# El envío offsite (Cloudflare R2) lo hace el servicio "offsite-sync".
# ──────────────────────────────────────────────────────────────────────────
set -eu

TS=$(date +%Y%m%d_%H%M%S)
OUT="/backups/yeikar_${TS}.dump"

echo "[$(date '+%F %T')] pg_dump → $OUT"
pg_dump -Fc -Z 9 -f "$OUT"

# Verificación: listar el contenido del dump valida que no esté truncado
TAM=$(du -h "$OUT" | cut -f1)
if pg_restore --list "$OUT" > /dev/null 2>&1; then
    echo "[$(date '+%F %T')] OK  ($TAM) — dump verificable"
else
    echo "[$(date '+%F %T')] ERROR: el dump NO se puede leer — revisar YA"
    exit 1
fi

# Retención local (los dumps también viven en R2, ahí la retención la
# maneja la regla de lifecycle del bucket)
find /backups -name 'yeikar_*.dump' -mtime +"${RETENTION_DAYS:-14}" -delete
echo "[$(date '+%F %T')] retención local aplicada (${RETENTION_DAYS:-14} días)"
