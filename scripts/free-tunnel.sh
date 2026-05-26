#!/usr/bin/env bash
# Free HTTPS tunnel (Cloudflare quick) + publish URL for Netlify auto-discovery.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${JARVIS_PORT:-8765}"
URL_FILE="$ROOT/data/public_url.txt"
LOG_FILE="$ROOT/data/tunnel.log"
PID_FILE="$ROOT/data/logs/free-tunnel.pid"
TUNNEL_PID=""

mkdir -p "$ROOT/data/logs"

stop_tunnel() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    wait "$(cat "$PID_FILE")" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  TUNNEL_PID=""
}

verify_tunnel() {
  local url="$1"
  for _ in $(seq 1 25); do
    if curl -sf --max-time 15 "${url}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

start_tunnel() {
  stop_tunnel
  if ! command -v cloudflared >/dev/null 2>&1; then
    echo "Install cloudflared: brew install cloudflared"
    return 1
  fi

  : > "$LOG_FILE"
  cloudflared tunnel --url "http://127.0.0.1:${PORT}" --protocol http2 >>"$LOG_FILE" 2>&1 &
  TUNNEL_PID=$!
  echo "$TUNNEL_PID" > "$PID_FILE"

  local url=""
  for _ in $(seq 1 120); do
    url="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" 2>/dev/null | head -1 || true)"
    if grep -q "Registered tunnel connection" "$LOG_FILE" 2>/dev/null && [ -n "$url" ]; then
      break
    fi
    if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
      echo "Cloudflare tunnel exited. Log:"
      tail -n 8 "$LOG_FILE" 2>/dev/null || true
      rm -f "$PID_FILE"
      return 1
    fi
    sleep 1
  done

  if [ -z "$url" ]; then
    stop_tunnel
    return 1
  fi

  echo "Verifying tunnel ..."
  if verify_tunnel "$url"; then
    :
  else
    echo "Tunnel slow to respond — keeping it running anyway: $url"
  fi

  url="${url%/}"
  echo "$url" > "$URL_FILE"
  bash "$ROOT/scripts/publish-backend-url.sh" "$url" || true
  echo "Free HTTPS URL: $url"
  return 0
}

start_daemon() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Free tunnel already running"
    return 0
  fi
  if start_tunnel; then
    return 0
  fi
  return 1
}

case "${1:-start}" in
  start-daemon)
    start_daemon
    ;;
  start)
    if start_daemon; then
      wait "$(cat "$PID_FILE")" 2>/dev/null || true
    fi
    ;;
  stop)
    stop_tunnel
    ;;
  restart)
    stop_tunnel
    sleep 1
    start_tunnel
    ;;
  status)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Free tunnel: up  $(cat "$URL_FILE" 2>/dev/null || echo)"
    else
      echo "Free tunnel: down"
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
