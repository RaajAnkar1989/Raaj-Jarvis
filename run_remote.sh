#!/usr/bin/env bash
# Start PWA backend + HTTPS tunnel (for Netlify PWA on your phone).
set -euo pipefail
cd "$(dirname "$0")"

PORT="${JARVIS_PORT:-8765}"
PWA_PID=""

cleanup() {
  echo ""
  echo "Stopping JARVIS remote stack ..."
  if [[ -n "$PWA_PID" ]] && kill -0 "$PWA_PID" 2>/dev/null; then
    kill "$PWA_PID" 2>/dev/null || true
    wait "$PWA_PID" 2>/dev/null || true
  fi
  pkill -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" 2>/dev/null || true
  pkill -f "localtunnel --port ${PORT}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "  MARK XXXIX — Remote mode (backend + HTTPS tunnel)"
echo "  ─────────────────────────────────────────────────"
echo ""

pkill -f "python main.py" 2>/dev/null || true
pkill -f "python pwa_main.py" 2>/dev/null || true
if command -v lsof >/dev/null 2>&1; then
  lsof -ti ":${PORT}" 2>/dev/null | xargs kill -9 2>/dev/null || true
fi
sleep 1

source .venv/bin/activate
pip install -q fastapi uvicorn python-multipart 2>/dev/null || true
bash scripts/prepare-pwa-assets.sh >/dev/null

if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "  ⚠️  Ollama not running — start it first (ollama serve or Ollama app)"
fi

echo "  Starting PWA backend on port ${PORT} ..."
python pwa_main.py &
PWA_PID=$!

echo "  Waiting for backend ..."
for _ in $(seq 1 90); do
  if curl -sf --max-time 2 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    echo "  Backend ready at http://127.0.0.1:${PORT}"
    break
  fi
  if ! kill -0 "$PWA_PID" 2>/dev/null; then
    echo "ERROR: Backend process exited." >&2
    exit 1
  fi
  sleep 1
done

if ! curl -sf --max-time 2 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
  echo "ERROR: Backend did not start on port ${PORT}." >&2
  exit 1
fi

echo "  Warming up JARVIS engine (first load may take a minute) ..."
curl -sf --max-time 180 "http://127.0.0.1:${PORT}/api/status" >/dev/null 2>&1 || true

echo ""
exec bash scripts/start_tunnel.sh
