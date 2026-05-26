"""Context engine — assembles prompt context before every LLM call."""

from __future__ import annotations

from core.client_memory import format_for_prompt as format_client_memory
from memory.store import build_memory_context, remember_fact
from memory.working import get_recent


def build_agent_context(
    user_input: str,
    *,
    client_id: str | None = None,
    file_ctx: str | None = None,
    max_working: int = 30,
) -> str:
    parts: list[str] = []

    mem_block = build_memory_context(user_input, client_id)
    if mem_block:
        parts.append(mem_block)

    client_block = format_client_memory(client_id)
    if client_block:
        parts.append(client_block)

    recent = get_recent(client_id, limit=max_working)
    if recent:
        lines = ["[RECENT WORKING MEMORY]"]
        for turn in recent[-12:]:
            role = turn["role"].upper()
            lines.append(f"{role}: {turn['content'][:300]}")
        parts.append("\n".join(lines))

    if file_ctx:
        parts.append(f"[UPLOADED FILE]\n{file_ctx}")

    return "\n\n".join(parts)


def summarize_if_needed(text: str, max_chars: int = 3500) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n…(truncated)"


def persist_turn_summary(client_id: str | None, user: str, assistant: str) -> None:
    if not user.strip() or not assistant.strip():
        return
    snippet = f"User asked: {user[:200]}. Jarvis replied: {assistant[:300]}"
    remember_fact(snippet, mem_type="conversation", client_id=client_id or "")
