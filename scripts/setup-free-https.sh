#!/usr/bin/env bash
# Free setup: no domain, no Netlify env vars, no manual URL in the app.
# Backend publishes HTTPS URL to GitHub; raajarvis.netlify.app discovers it automatically.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo ""
echo "  Free HTTPS auto-connect for raajarvis.netlify.app"
echo "  ─────────────────────────────────────────────────"
echo ""
echo "  • No domain needed"
echo "  • No URL to paste in the app"
echo "  • Mac publishes backend URL → GitHub → Netlify app finds it"
echo ""

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Installing cloudflared ..."
  brew install cloudflared
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required to publish the backend URL."
  echo "Install: brew install gh"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Log in to GitHub (needed once to publish backend URL for your phone):"
  gh auth login
fi

echo "free" > "$ROOT/data/tunnel-mode.txt"

bash "$ROOT/scripts/inject-backend-url.sh"
chmod +x "$ROOT/scripts/"*.sh 2>/dev/null || true

echo ""
echo "Installing autostart (backend + free tunnel on Mac login) ..."
bash "$ROOT/scripts/install-autostart.sh"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Done! Next:"
echo ""
echo "  1. Push this repo to GitHub (if not already):"
echo "       git add -A && git commit -m 'free https auto-discovery' && git push"
echo ""
echo "  2. Netlify redeploys automatically from GitHub"
echo ""
echo "  3. On Mac login, JARVIS starts and publishes its HTTPS URL"
echo ""
echo "  4. Open https://raajarvis.netlify.app — connects automatically"
echo "     (first time: wait ~30s for Mac tunnel + GitHub update)"
echo ""
echo "  Manual start now:  ./scripts/jarvis-stack.sh start"
echo "════════════════════════════════════════════════════════════"
echo ""
