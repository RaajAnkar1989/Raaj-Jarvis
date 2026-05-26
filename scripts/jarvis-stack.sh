#!/usr/bin/env bash
# Start/stop JARVIS PWA backend + HTTPS tunnel (named Cloudflare or free mode).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${JARVIS_PORT:-8765}"
TUNNEL_NAME="${JARVIS_TUNNEL_NAME:-jarvis-pwa}"
LOG_DIR="$ROOT/data/logs"
PWA_PID_FILE="$LOG_DIR/pwa.pid"
TUNNEL_PID_FILE="$LOG_DIR/tunnel.pid"
MODE_FILE="$ROOT/data/tunnel-mode.txt"

mkdir -p "$LOG_DIR"

is_running() {
  local pid_file="$1"
  [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

tunnel_mode() {
  if [ -f "$MODE_FILE" ]; then
    cat "$MODE_FILE"
  elif [ -f "${HOME}/.cloudflared/config.yml" ]; then
    echo "named"
  else
    echo "free"
  fi
}

start_pwa() {
  if is_running "$PWA_PID_FILE"; then
    return 0
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti ":${PORT}" 2>/dev/null | xargs kill -9 2>/dev/null || true
  fi
  source "$ROOT/.venv/bin/activate"
  pip install -q fastapi uvicorn python-multipart 2>/dev/null || true
  nohup python "$ROOT/pwa_main.py" >>"$LOG_DIR/pwa.log" 2>&1 &
  echo $! > "$PWA_PID_FILE"
  for _ in $(seq 1 60); do
    if curl -sf --max-time 2 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_tunnel() {
  local mode
  mode="$(tunnel_mode)"

  if [ "$mode" = "free" ]; then
    bash "$ROOT/scripts/free-tunnel.sh" start-daemon
    return 0
  fi

  if is_running "$TUNNEL_PID_FILE"; then
    return 0
  fi
  if [ -f "$ROOT/data/tunnel-name.txt" ]; then
    TUNNEL_NAME="$(cat "$ROOT/data/tunnel-name.txt")"
  fi
  if [ ! -f "${HOME}/.cloudflared/config.yml" ]; then
    echo "No named tunnel — using free mode. Run: ./scripts/setup-free-https.sh"
    echo "free" > "$MODE_FILE"
    bash "$ROOT/scripts/free-tunnel.sh" start-daemon
    return 0
  fi
  nohup cloudflared tunnel run "$TUNNEL_NAME" >>"$LOG_DIR/tunnel.log" 2>&1 &
  echo $! > "$TUNNEL_PID_FILE"
}

stop_all() {
  bash "$ROOT/scripts/free-tunnel.sh" stop 2>/dev/null || true
  for f in "$TUNNEL_PID_FILE" "$PWA_PID_FILE"; do
    if is_running "$f"; then
      kill "$(cat "$f")" 2>/dev/null || true
      wait "$(cat "$f")" 2>/dev/null || true
    fi
    rm -f "$f"
  done
  pkill -f "cloudflared tunnel run" 2>/dev/null || true
}

status() {
  echo "Mode:                       $(tunnel_mode)"
  echo "PWA backend (port ${PORT}): $(is_running "$PWA_PID_FILE" && echo up || echo down)"
  if [ "$(tunnel_mode)" = "free" ]; then
    bash "$ROOT/scripts/free-tunnel.sh" status
  else
    echo "Cloudflare tunnel:          $(is_running "$TUNNEL_PID_FILE" && echo up || echo down)"
  fi
  if [ -f "$ROOT/data/public_url.txt" ]; then
    echo "Public URL:                 $(cat "$ROOT/data/public_url.txt")"
  fi
}

case "${1:-start}" in
  start)
    start_pwa
    start_tunnel || true
    status
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    sleep 1
    start_pwa
    start_tunnel || true
    status
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
