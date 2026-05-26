"""Unified memory facade — bridges JSON legacy store and SQLite semantic memory."""

from __future__ import annotations

from memory.db import init_db, list_active_tasks, list_memories
from memory.memory_manager import format_memory_for_prompt, load_memory, update_memory
from memory.retrieval import format_relevant_for_prompt, get_relevant_memory, store_with_embedding
from memory.working import append_turn, get_recent


def bootstrap_from_json() -> None:
    """One-time seed: copy key facts from long_term.json into SQLite."""
    init_db()
    mem = load_memory()
    if list_memories(limit=1):
        return
    for category, items in mem.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = entry.get("value") if isinstance(entry, dict) else str(entry)
            if val:
                store_with_embedding(
                    mem_type="preference" if category == "preferences" else "note",
                    content=f"{category}/{key}: {val}",
                    tags=[category, key],
                )


def remember_fact(
    content: str,
    *,
    mem_type: str = "note",
    client_id: str = "",
    tags: list[str] | None = None,
) -> int:
    bootstrap_from_json()
    mid = store_with_embedding(
        mem_type=mem_type,
        content=content,
        tags=tags,
        client_id=client_id,
    )
    return mid


def build_memory_context(user_input: str, client_id: str | None = None) -> str:
    bootstrap_from_json()
    parts: list[str] = []

    legacy = format_memory_for_prompt(load_memory())
    if legacy:
        parts.append(legacy)

    relevant = get_relevant_memory(user_input, client_id=client_id or "", top_k=6)
    rel_text = format_relevant_for_prompt(relevant)
    if rel_text:
        parts.append(rel_text)

    tasks = list_active_tasks(client_id or "", limit=5)
    if tasks:
        lines = ["[ACTIVE TASKS]"]
        for t in tasks:
            lines.append(f"- {t['title']} ({t['status']})")
        parts.append("\n".join(lines))

    return "\n".join(parts)
