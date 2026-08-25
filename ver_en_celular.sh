#!/usr/bin/env bash
# =============================================================================
# ver_en_celular.sh — levanta TODO el YEIKAR ERP (base de datos + backend +
# frontend) y lo expone a tu celular.
#
# DOS modos:
#   1) RED LOCAL (mismo WiFi, sin túnel):  ./ver_en_celular.sh --lan
#   2) TÚNEL Cloudflare (desde CUALQUIER red, sin cuenta): ./ver_en_celular.sh
#      (por defecto abre también el túnel)
#
# Cómo funciona el flujo en el celular:
#   Celular  →  https://xxx.trycloudflare.com  (frontend)
#            →  Vite hace proxy de /api → http://localhost:8000  (backend)
#            →  backend usa postgresql://yeikar@localhost:5432/yeikar  (BD)
#   La BD NO se expone por internet: solo la alcanza el backend localmente.
#
# Detener:
#   - Túnel: Ctrl+C en esta terminal (o: pkill -f "cloudflared tunnel")
#   - Backend/frontend que el script haya arrancado: ./ver_en_celular.sh --stop
#     (los que ya estaban corriendo antes se dejan intactos)
# =============================================================================
set -euo pipefail

ROOT="$HOME/YEIKAR"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
CLOUDFLARED="/tmp/opencode/cloudflared"
LOGS="$ROOT/.celular-logs"
BACK_PORT=8000
FE_PORT=5173
DB_PORT=5432

# Detección de la IP local (la de la interfaz con ruta por defecto)
LAN_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"
[ -z "$LAN_IP" ] && LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

paso() { echo -e "\n\033[1;34m► $1\033[0m"; }
ok()   { echo -e "   \033[0;32m✔ $1\033[0m"; }
no()   { echo -e "   \033[0;33m$1\033[0m"; }

puerto_escucha() { ss -ltn 2>/dev/null | grep -q ":$1 "; }

arrancar_bd() {
  if puerto_escucha "$DB_PORT"; then
    ok "PostgreSQL ya corre en :$DB_PORT"
    return
  fi
  # Debian: cluster postgres (o arranque por docker como alternativa)
  if command -v pg_lsclusters >/dev/null 2>&1 && pg_lsclusters 2>/dev/null | grep -q "online"; then
    ok "PostgreSQL (cluster) ya está online"
    return
  fi
  if command -v sudo >/dev/null 2>&1 && command -v pg_ctlcluster >/dev/null 2>&1; then
    CLUSTER="$(pg_lsclusters 2>/dev/null | awk 'NR==2{print $1" "$2}')"
    if [ -n "$CLUSTER" ]; then
      no "PostgreSQL apagado. Arrancando cluster $CLUSTER..."
      sudo pg_ctlcluster $CLUSTER start
      sleep 2
      ok "PostgreSQL arrancado"
      return
    fi
  fi
  no "PostgreSQL no está corriendo. Intentando con Docker Compose..."
  (cd "$ROOT" && docker compose up -d db 2>/dev/null || true)
  if puerto_escucha "$DB_PORT"; then
    ok "PostgreSQL (Docker) arrancado"
  else
    err "No pude arrancar la BD. Iníciala manualmente (pg_ctlcluster o docker compose up -d db)."
    exit 1
  fi
}

arrancar_backend() {
  if puerto_escucha "$BACK_PORT"; then
    ok "Backend ya corre en :$BACK_PORT"
    return
  fi
  no "Backend apagado. Arrancando uvicorn en :$BACK_PORT..."
  mkdir -p "$LOGS"
  # NOTA: NO se usa --no-proxy-headers. El túnel aterriza en 127.0.0.1 (vite), que
  # uvicorn ya considera proxy de confianza por defecto → conserva la IP real del
  # celular para rate-limit y lockout de login.
  nohup "$BACKEND_DIR/venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$BACK_PORT" \
    --reload >"$LOGS/backend.log" 2>&1 &
  echo $! >"$LOGS/backend.pid"
  sleep 3
  if puerto_escucha "$BACK_PORT"; then
    ok "Backend arrancado (log: $LOGS/backend.log)"
  else
    no "El backend no respondió aún; revisa $LOGS/backend.log"
  fi
}

arrancar_frontend() {
  if puerto_escucha "$FE_PORT"; then
    ok "Frontend ya corre en :$FE_PORT"
    return
  fi
  no "Frontend apagado. Arrancando Vite en :$FE_PORT..."
  mkdir -p "$LOGS"
  nohup npm --prefix "$FRONTEND_DIR" run dev >"$LOGS/frontend.log" 2>&1 &
  echo $! >"$LOGS/frontend.pid"
  sleep 4
  if puerto_escucha "$FE_PORT"; then
    ok "Frontend arrancado (log: $LOGS/frontend.log)"
  else
    no "El frontend no respondió aún; revisa $LOGS/frontend.log"
  fi
}

detener_levantados() {
  for s in backend frontend; do
    if [ -f "$LOGS/$s.pid" ]; then
      kill "$(cat "$LOGS/$s.pid")" 2>/dev/null || true
      rm -f "$LOGS/$s.pid"
      echo "   Detenido $s (arrancado por el script)"
    fi
  done
}

# ---------------------------------------------------------------- CLI
case "${1:-tunel}" in
  --stop)
    echo "Deteniendo servicios que levantó este script..."
    detener_levantados
    pkill -f "cloudflared tunnel" 2>/dev/null || true
    echo "Listo. Postgres y servicios que ya corrían antes se dejan intactos."
    exit 0
    ;;
  --lan)
    MODE="lan"
    ;;
  --tunel|--tunnel|"tunel")
    MODE="tunel"
    ;;
  *)
    echo "Uso: $0 [--lan|--tunel|--stop]   (por defecto: --tunel)"
    exit 1
    ;;
esac

echo "============================================================"
echo "  YEIKAR ERP — acceso desde el celular"
echo "============================================================"
paso "1/4 Base de datos"
arrancar_bd
paso "2/4 Backend (:$BACK_PORT)"
arrancar_backend
paso "3/4 Frontend (:$FE_PORT)"
arrancar_frontend

paso "4/4 Modo: $MODE"
if [ "$MODE" = "lan" ]; then
  echo ""
  echo "   Abre en el navegador del celular (misma WiFi):"
  echo -e "\n      \033[1;32mhttp://$LAN_IP:$FE_PORT\033[0m\n"
  echo "   Si no carga, revisa que el celular esté en la MISMA red y"
  echo "   que el firewall permita el puerto $FE_PORT."
else
  if [ ! -f "$CLOUDFLARED" ]; then
    echo "   Descargando cloudflared (una sola vez)..."
    ARCH=$(uname -m)
    case "$ARCH" in
      aarch64|arm64) BIN="cloudflared-linux-arm64" ;;
      *)             BIN="cloudflared-linux-amd64" ;;
    esac
    curl -sL -o "$CLOUDFLARED" \
      "https://github.com/cloudflare/cloudflared/releases/latest/download/$BIN"
    chmod +x "$CLOUDFLARED"
  fi
  echo "   Abriendo túnel Cloudflare (gratis, sin cuenta, URL válida ~1 día)..."
  echo "   LAN (misma WiFi, sin túnel): http://$LAN_IP:$FE_PORT"
  echo ""
  echo "   ════════════════════════════════════════════════════════"
  echo "   Copia la URL  https://....trycloudflare.com  que aparece"
  echo "   debajo y ábrela en el navegador del celular."
  echo "   Ctrl+C aquí detiene el túnel (el resto sigue corriendo)."
  echo "   ════════════════════════════════════════════════════════"
  echo ""
  "$CLOUDFLARED" tunnel --url "http://localhost:$FE_PORT" --no-autoupdate
fi
