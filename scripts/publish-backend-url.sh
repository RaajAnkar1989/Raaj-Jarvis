#!/usr/bin/env bash
# Publish current HTTPS backend URL so raajarvis.netlify.app can auto-discover it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-}"
URL="${URL%/}"
FILE="data/public-backend-url.txt"

if [ -z "$URL" ] || [[ ! "$URL" =~ ^https:// ]]; then
  echo "Usage: $0 https://your-backend-url" >&2
  exit 1
fi

mkdir -p "$ROOT/data"
echo "$URL" > "$ROOT/$FILE"

if ! command -v gh >/dev/null 2>&1; then
  echo "Saved locally: $ROOT/$FILE (install gh to auto-publish for Netlify discovery)"
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

B64="$(printf '%s' "$URL" | base64 | tr -d '\n')"
API="repos/${OWNER}/${REPO}/contents/${FILE}"
SHA="$(gh api "$API" --jq .sha 2>/dev/null || true)"

if [ -n "$SHA" ]; then
  gh api "$API" -X PUT \
    -f message="chore: update JARVIS backend URL" \
    -f content="$B64" \
    -f sha="$SHA" >/dev/null
else
  gh api "$API" -X PUT \
    -f message="chore: add JARVIS backend URL" \
    -f content="$B64" >/dev/null
fi

echo "Published $URL → github.com/${OWNER}/${REPO}/${FILE}"
