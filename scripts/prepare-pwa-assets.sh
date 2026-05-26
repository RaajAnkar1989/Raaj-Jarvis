#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/web/static/icons"
cp -f "$ROOT/face.png" "$ROOT/web/static/icons/face.png"
bash "$ROOT/scripts/inject-backend-url.sh"
echo "PWA assets ready."
