#!/usr/bin/env bash
# Bake PWA config for Netlify (optional JARVIS_API_URL) + GitHub discovery URL.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${JARVIS_API_URL:-}"
URL="${URL%/}"
REDIRECTS="$ROOT/web/static/_redirects"

REMOTE="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
DISCOVERY_REPO="RaajAnkar1989/Raaj-Jarvis"
if [[ "$REMOTE" =~ github.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]] || [[ "$REMOTE" =~ git@github.com:([^/]+)/([^/.]+)(\.git)?$ ]]; then
  DISCOVERY_REPO="${BASH_REMATCH[1]}/${BASH_REMATCH[2]%.git}"
fi

cat > "$ROOT/web/static/discovery.js" <<EOF
// Auto-discovery: Mac publishes HTTPS URL to GitHub; app fetches it on load.
window.__JARVIS_DISCOVERY__ = {
  url: "https://raw.githubusercontent.com/${DISCOVERY_REPO}/main/data/public-backend-url.txt",
};
EOF

if [ -n "$URL" ]; then
  echo "Injecting backend URL: $URL"
  WS_URL="${URL/https:\/\//wss://}/ws"

  cat > "$ROOT/web/static/config.js" <<EOF
// Generated at build time — do not edit by hand.
window.__JARVIS_API__ = "";
window.__JARVIS_WS_URL__ = "${WS_URL}";
window.__JARVIS_NETLIFY_PROXY__ = true;
EOF

  cat > "$REDIRECTS" <<EOF
# Proxy API through Netlify (same-origin) — frontend: https://raajarvis.netlify.app
/api/*  ${URL}/api/:splat  200
EOF
  echo "Netlify proxy: /api/* → ${URL}/api/*"
else
  cat > "$ROOT/web/static/config.js" <<EOF
// Generated at build time — do not edit by hand.
window.__JARVIS_API__ = "";
window.__JARVIS_WS_URL__ = "";
window.__JARVIS_NETLIFY_PROXY__ = false;
EOF
  rm -f "$REDIRECTS"
  echo "Discovery mode: app auto-fetches backend URL from GitHub (free, no domain)."
fi
