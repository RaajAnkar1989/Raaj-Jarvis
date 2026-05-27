"""Test a single provider connection."""

from __future__ import annotations

from typing import Any

from core.llm.token_manager import build_compact_messages
from core.providers.implementations import get_provider


def test_provider(name: str) -> dict[str, Any]:
    provider = get_provider(name)
    if not provider:
        return {"ok": False, "provider": name, "error": "Unknown provider"}
    try:
        messages, _ = build_compact_messages(
            system="You are JARVIS. Reply in one short sentence.",
            user_input="Say exactly: connection ok",
            history=[],
            max_tokens=200,
        )
        timeout = 45 if name == "ollama" else 25
        resp = provider.complete(messages, timeout=timeout, max_tokens=32)
        return {
            "ok": bool(resp.content),
            "provider": resp.provider,
            "model": resp.model,
            "latency_ms": resp.latency_ms,
            "sample": resp.content[:100],
        }
    except Exception as e:
        return {"ok": False, "provider": name, "error": str(e)[:200]}
