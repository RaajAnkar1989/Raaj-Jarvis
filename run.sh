#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "⚠️  Ollama is not running. Start it with: ollama serve"
  echo "   Or open the Ollama app, then run this script again."
  exit 1
fi

python main.py
