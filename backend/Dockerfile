# ── Stage 1: dependencias ─────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Instalar dependencias del sistema necesarias para psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: imagen final ─────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Runtime deps para psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copiar paquetes instalados desde builder
COPY --from=builder /install /usr/local

# Copiar código fuente
COPY . .

RUN chmod +x entrypoint.sh

# Puerto de la aplicación
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Comando de arranque: migra el esquema (alembic upgrade head) y luego sirve.
# --no-proxy-headers: no confiar en X-Forwarded-For (anti-spoofing del rate limit
# y del lockout de login). La app usa la IP real del socket (el proxy nginx).
CMD ["./entrypoint.sh"]