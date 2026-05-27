"""Token budgeting and compact prompt building for cloud APIs."""

from __future__ import annotations

import re
from typing import Any

from core.client_memory import format_for_prompt as format_client_memory
from memory.retrieval import format_relevant_for_prompt, get_relevant_memory
from memory.working import get_recent

CHARS_PER_TOKEN = 4
DEFAULT_BUDGET = 1200


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _trim(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 3].rstrip() + "..."


def summarize_turns(turns: list[dict[str, str]], max_chars: int = 400) -> str:
    if not turns:
        return ""
    lines: list[str] = []
    for t in turns:
        role = t.get("role", "user")[:1].upper()
        content = _trim(t.get("content", ""), 120)
        if content:
            lines.append(f"{role}: {content}")
    blob = " | ".join(lines)
    return _trim(blob, max_chars)


def build_compact_messages(
    *,
    system: str,
    user_input: str,
    history: list[dict[str, str]] | None = None,
    client_id: str | None = None,
    max_tokens: int = DEFAULT_BUDGET,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """
    Build minimal message list for cloud providers.
    Never sends full history — recent window + summary + semantic memory only.
    """
    budget_chars = max_tokens * CHARS_PER_TOKEN
    meta: dict[str, Any] = {"estimated_input_tokens": 0, "trimmed": False}

    recent = get_recent(client_id, limit=6)
    if not recent and history:
        recent = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]

    older = history[:-6] if history and len(history) > 6 else []
    summary = summarize_turns(older) if older else ""

    semantic = format_relevant_for_prompt(
        get_relevant_memory(user_input, client_id=client_id or "", top_k=3)
    )
    client_mem = format_client_memory(client_id)

    sys_parts = [_trim(system, 600)]
    if semantic:
        sys_parts.append(_trim(semantic, 350))
    if client_mem:
        sys_parts.append(_trim(client_mem, 250))
    if summary:
        sys_parts.append(f"[Earlier context summary] {_trim(summary, 300)}")

    system_block = "\n".join(p for p in sys_parts if p)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_block}]

    for turn in recent[-4:]:
        messages.append({
            "role": turn["role"],
            "content": _trim(turn["content"], 280),
        })

    messages.append({"role": "user", "content": _trim(user_input, 500)})

    total = sum(len(m["content"]) for m in messages)
    if total > budget_chars:
        meta["trimmed"] = True
        while len(messages) > 2 and total > budget_chars:
            messages.pop(1)
            total = sum(len(m["content"]) for m in messages)

    meta["estimated_input_tokens"] = estimate_tokens(
        "\n".join(m["content"] for m in messages)
    )
    return messages, meta


def dedupe_assistant_replies(text: str) -> str:
    """Remove repeated sentence patterns in assistant output."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        key = p.lower()[:80]
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return " ".join(out)
