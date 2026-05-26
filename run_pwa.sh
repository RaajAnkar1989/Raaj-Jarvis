#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Avoid duplicate engines (desktop + PWA both listening/speaking).
pkill -f "python main.py" 2>/dev/null || true
pkill -f "python pwa_main.py" 2>/dev/null || true
sleep 1

source .venv/bin/activate
pip install -q fastapi uvicorn python-multipart 2>/dev/null || true
bash scripts/prepare-pwa-assets.sh

if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "  ⚠️  Ollama not running — start it first (ollama serve or Ollama app)"
fi

echo ""
echo "  MARK XXXIX PWA Backend"
echo "  ─────────────────────────────────────"
echo "  Local:    http://localhost:8765"
IP=$(python -c "import socket;s=socket.socket();s.connect(('8.8.8.8',80));print(s.getsockname()[0]);s.close()" 2>/dev/null || echo "YOUR-IP")
echo "  Phone:    http://${IP}:8765  (same Wi‑Fi)"
echo ""
echo "  Netlify:  run ./run_remote.sh for HTTPS tunnel URL → paste in PWA settings"
echo "  See DEPLOY-PWA.md for full guide"
echo "  ─────────────────────────────────────"
echo ""
python pwa_main.py
