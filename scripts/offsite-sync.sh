#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────
# YEIKAR — Sincronización offsite de backups → Cloudflare R2
# Lo ejecuta el servicio "offsite-sync" en bucle (cada hora).
#
# Anti-ransomware: la copia vive FUERA del VPS. Aunque te secuestren el
# servidor, el atacante no puede borrar el bucket con la credencial que
# usa este servicio (solo-agregar). La retención de versiones viejas la
# maneja la regla de lifecycle del bucket (ver DEPLOY.md, paso 7).
#
# Config por .env: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
# R2_BUCKET. Sin credenciales → inactivo (queda solo el backup local).
# ──────────────────────────────────────────────────────────────────────────

if [ -z "$R2_ACCOUNT_ID" ] || [ -z "$R2_ACCESS_KEY_ID" ] || [ -z "$R2_SECRET_ACCESS_KEY" ]; then
    echo "[offsite-sync] Sin credenciales R2 en .env — inactivo."
    echo "[offsite-sync] Para activar: completa R2_* en .env y ejecuta"
    echo "[offsite-sync]   docker compose --profile backup up -d offsite-sync"
    echo "[offsite-sync] Guía completa: DEPLOY.md paso 7."
    sleep infinity
fi

REMOTE="R2:${R2_BUCKET:-yeikar-backups}"
echo "[offsite-sync] Destino: $REMOTE (cuenta $R2_ACCOUNT_ID)"

# Primera pasada inmediata (al arrancar el contenedor)
while true; do
    # --min-age 2m: no copiar un dump que se esté escribiendo todavía
    # rclone copy solo AÑADE/actualiza; nunca borra en el bucket
    if rclone copy /backups "$REMOTE" \
        --min-age 2m \
        --transfers 2 --checkers 4 \
        --log-level NOTICE 2>&1; then
        echo "[offsite-sync] $(date '+%F %T') sincronizado OK"
    else
        echo "[offsite-sync] $(date '+%F %T') ERROR sincronizando — reintento en 10 min"
        sleep 10m
        continue
    fi
    sleep 1h
done
