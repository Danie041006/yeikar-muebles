#!/bin/sh
# Migra el esquema antes de arrancar (un solo comando para desplegar):
#   git pull && docker compose up -d --build
# Si la migración falla, el contenedor no arranca (fail-fast).
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --no-proxy-headers
