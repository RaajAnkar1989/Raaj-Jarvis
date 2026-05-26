#!/usr/bin/env bash
# Expose local JARVIS backend (port 8765) over HTTPS for Netlify PWA.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${JARVIS_PORT:-8765}"
URL_FILE="$ROOT/data/public_url.txt"
LOG_FILE="$ROOT/data/tunnel.log"
TUNNEL_PID=""

mkdir -p "$ROOT/data"

cleanup() {
  if [[ -n "$TUNNEL_PID" ]] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
    kill "$TUNNEL_PID" 2>/dev/null || true
    wait "$TUNNEL_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

wait_backend() {
  if curl -sf --max-time 2 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    return 0
  fi
  echo "Waiting for backend on http://127.0.0.1:${PORT} ..."
  for _ in $(seq 1 90); do
    if curl -sf --max-time 2 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
      echo "Backend is ready."
      return 0
    fi
    sleep 1
  done
  echo ""
  echo "ERROR: Nothing is listening on port ${PORT}."
  echo "Start the backend first:  ./run_pwa.sh"
  echo "Or use one command:       ./run_remote.sh"
  exit 1
}

save_url() {
  local url="$1"
  url="${url%/}"
  echo "$url" > "$URL_FILE"
  export JARVIS_PUBLIC_URL="$url"
  bash "$ROOT/scripts/publish-backend-url.sh" "$url" 2>/dev/null || true

  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo "  HTTPS backend URL — paste this in the Netlify PWA settings:"
  echo ""
  echo "    ${url}"
  echo ""
  echo "  Saved to: data/public_url.txt"
  echo "  Verify:   curl ${url}/api/status"
  echo "════════════════════════════════════════════════════════════"
  echo ""
}

verify_tunnel() {
  local url="$1"
  for _ in $(seq 1 30); do
    if curl -sf --max-time 20 "${url}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
  done
  return 1
}

start_cloudflared() {
  local proto="${1:-quic}"
  if ! command -v cloudflared >/dev/null 2>&1; then
    return 1
  fi

  : > "$LOG_FILE"
  echo "Starting Cloudflare tunnel (protocol=${proto}) ..."
  cloudflared tunnel --url "http://127.0.0.1:${PORT}" --protocol "$proto" >>"$LOG_FILE" 2>&1 &
  TUNNEL_PID=$!

  local url=""
  for _ in $(seq 1 120); do
    url="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" 2>/dev/null | head -1 || true)"
    if [[ -n "$url" ]]; then
      break
    fi
    if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
      echo "Cloudflare tunnel exited early. Last log lines:"
      tail -n 8 "$LOG_FILE" 2>/dev/null || true
      TUNNEL_PID=""
      return 1
    fi
    sleep 1
  done

  if [[ -z "$url" ]]; then
    kill "$TUNNEL_PID" 2>/dev/null || true
    wait "$TUNNEL_PID" 2>/dev/null || true
    TUNNEL_PID=""
    return 1
  fi

  echo "Tunnel URL detected, verifying ..."
  if verify_tunnel "$url"; then
    save_url "$url"
    echo "Cloudflare tunnel is live. Press Ctrl+C to stop."
    wait "$TUNNEL_PID"
    return 0
  fi

  echo "Tunnel URL did not respond in time."
  kill "$TUNNEL_PID" 2>/dev/null || true
  wait "$TUNNEL_PID" 2>/dev/null || true
  TUNNEL_PID=""
  return 1
}

start_localtunnel() {
  if ! command -v npx >/dev/null 2>&1; then
    return 1
  fi

  : > "$LOG_FILE"
  echo "Starting localtunnel (fallback) ..."
  npx --yes localtunnel --port "$PORT" >>"$LOG_FILE" 2>&1 &
  TUNNEL_PID=$!

  local url=""
  for _ in $(seq 1 60); do
    url="$(grep -oE 'https://[a-z0-9-]+\.loca\.lt' "$LOG_FILE" 2>/dev/null | head -1 || true)"
    if [[ -n "$url" ]]; then
      break
    fi
    if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
      TUNNEL_PID=""
      return 1
    fi
    sleep 1
  done

  if [[ -z "$url" ]]; then
    kill "$TUNNEL_PID" 2>/dev/null || true
    wait "$TUNNEL_PID" 2>/dev/null || true
    TUNNEL_PID=""
    return 1
  fi

  save_url "$url"
  echo "localtunnel is live (WebSocket may be less reliable than Cloudflare)."
  echo "Press Ctrl+C to stop."
  wait "$TUNNEL_PID"
  return 0
}

start_ngrok() {
  if ! command -v ngrok >/dev/null 2>&1; then
    return 1
  fi

  : > "$LOG_FILE"
  echo "Starting ngrok ..."
  ngrok http "$PORT" --log=stdout >>"$LOG_FILE" 2>&1 &
  TUNNEL_PID=$!

  local url=""
  for _ in $(seq 1 60); do
    url="$(curl -sf http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.ngrok[^"]*' | head -1 || true)"
    if [[ -n "$url" ]]; then
      break
    fi
    if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
      TUNNEL_PID=""
      return 1
    fi
    sleep 1
  done

  if [[ -z "$url" ]]; then
    kill "$TUNNEL_PID" 2>/dev/null || true
    wait "$TUNNEL_PID" 2>/dev/null || true
    TUNNEL_PID=""
    return 1
  fi

  if verify_tunnel "$url"; then
    save_url "$url"
    echo "ngrok tunnel is live. Press Ctrl+C to stop."
    wait "$TUNNEL_PID"
    return 0
  fi

  kill "$TUNNEL_PID" 2>/dev/null || true
  wait "$TUNNEL_PID" 2>/dev/null || true
  TUNNEL_PID=""
  return 1
}

wait_backend

if start_cloudflared quic; then exit 0; fi
if start_cloudflared http2; then exit 0; fi
if start_ngrok; then exit 0; fi
if start_localtunnel; then exit 0; fi

echo ""
echo "Could not start any HTTPS tunnel."
echo "  • Ensure cloudflared is installed: brew install cloudflared"
echo "  • Check your network / DNS (Cloudflare needs outbound HTTPS)"
echo "  • Same Wi‑Fi workaround: open http://YOUR-MAC-IP:${PORT} on your phone (no Netlify)"
exit 1
