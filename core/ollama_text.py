"""Local Ollama text helper for file indexing and summaries."""

from __future__ import annotations

import requests

from core.llm_config import load_llm_config


def ollama_complete(prompt: str, *, max_tokens: int = 220) -> str:
    cfg = load_llm_config()
    base = cfg.get("ollama_base_url", "http://localhost:11434").rstrip("/")
    model = cfg.get("ollama_model") or "qwen2.5:7b"
    try:
        resp = requests.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": max_tokens, "num_ctx": 4096},
            },
            timeout=90,
        )
        resp.raise_for_status()
        return (resp.json().get("message") or {}).get("content") or ""
    except Exception as e:
        return f"(Could not analyze: {e})"
