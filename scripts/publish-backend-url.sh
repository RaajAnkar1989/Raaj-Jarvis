#!/usr/bin/env bash
# Publish current HTTPS backend URL so raajarvis.netlify.app can auto-discover it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-}"
URL="${URL%/}"
FILE="data/public-backend-url.txt"
REDIRECTS="web/static/_redirects"

if [ -z "$URL" ] || [[ ! "$URL" =~ ^https:// ]]; then
  echo "Usage: $0 https://your-backend-url" >&2
  exit 1
fi

mkdir -p "$ROOT/data" "$ROOT/web/static"
echo "$URL" > "$ROOT/$FILE"

cat > "$ROOT/$REDIRECTS" <<EOF
# Proxy API through Netlify — OAuth + REST (WebSocket still uses tunnel discovery)
/api/*  ${URL}/api/:splat  200
EOF

if ! command -v gh >/dev/null 2>&1; then
  echo "Saved locally: $ROOT/$FILE and $REDIRECTS (install gh to auto-publish)"
  exit 0
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Saved locally. Run: gh auth login  (then re-run jarvis-stack) to publish for Netlify."
  exit 0
fi

REMOTE="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
if [[ "$REMOTE" =~ github.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]] || [[ "$REMOTE" =~ git@github.com:([^/]+)/([^/.]+)(\.git)?$ ]]; then
  OWNER="${BASH_REMATCH[1]}"
  REPO="${BASH_REMATCH[2]%.git}"
else
  echo "Could not detect GitHub repo from git remote."
  exit 1
fi

_publish_file() {
  local path="$1"
  local message="$2"
  local content
  content="$(cat "$ROOT/$path")"
  local b64
  b64="$(printf '%s' "$content" | base64 | tr -d '\n')"
  local api="repos/${OWNER}/${REPO}/contents/${path}"
  local sha
  sha="$(gh api "$api" --jq .sha 2>/dev/null || true)"
  if [ -n "$sha" ]; then
    gh api "$api" -X PUT -f message="$message" -f content="$b64" -f sha="$sha" >/dev/null
  else
    gh api "$api" -X PUT -f message="$message" -f content="$b64" >/dev/null
  fi
}

_publish_file "$FILE" "chore: update JARVIS backend URL"
_publish_file "$REDIRECTS" "chore: update Netlify API proxy for Gmail OAuth"

echo "Published $URL → github.com/${OWNER}/${REPO}/${FILE}"
echo "Published Netlify proxy → github.com/${OWNER}/${REPO}/${REDIRECTS}"
