#!/usr/bin/env bash
# Publish stable named-tunnel config (one-time or after setup-named-tunnel.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-}"
URL="${URL%/}"

if [ -z "$URL" ] || [[ ! "$URL" =~ ^https:// ]]; then
  if [ -f "$ROOT/data/public_url.txt" ]; then
    URL="$(cat "$ROOT/data/public_url.txt" | tr -d ' ')"
  fi
fi

if [[ ! "$URL" =~ ^https:// ]]; then
  echo "Usage: $0 https://jarvis.yourdomain.com" >&2
  exit 1
fi

echo "$URL" > "$ROOT/data/public_url.txt"
echo "named" > "$ROOT/data/tunnel-mode.txt"

cat > "$ROOT/web/static/_redirects" <<EOF
# Stable named tunnel — API proxied through Netlify for OAuth
/api/*  ${URL}/api/:splat  200
EOF

bash "$ROOT/scripts/publish-backend-url.sh" "$URL" || true

echo ""
echo "Stable URL configured: $URL"
echo "Set Netlify env JARVIS_API_URL=$URL (optional — _redirects also works)"
echo "Gmail OAuth redirect: https://raajarvis.netlify.app/api/gmail/oauth/callback"
