"""Semantic memory retrieval — get_relevant_memory(user_input)."""

from __future__ import annotations

from typing import Any

from memory.db import fetch_embeddings, insert_memory, init_db
from memory.embeddings import cosine_similarity, embed_text, pack_embedding, unpack_embedding


def store_with_embedding(
    *,
    mem_type: str,
    content: str,
    tags: list[str] | None = None,
    client_id: str = "",
) -> int:
    init_db()
    vec = embed_text(content)
    blob = pack_embedding(vec) if vec else None
    return insert_memory(
        mem_type=mem_type,
        content=content,
        embedding=blob,
        tags=tags,
        client_id=client_id,
    )


def get_relevant_memory(
    user_input: str,
    *,
    client_id: str = "",
    top_k: int = 6,
) -> list[dict[str, Any]]:
    """Return top-k memories ranked by embedding similarity."""
    init_db()
    query = (user_input or "").strip()
    if not query:
        return []

    q_vec = embed_text(query)
    if not q_vec:
        return []

    scored: list[tuple[float, int, str]] = []
    for mid, content, blob in fetch_embeddings(client_id=client_id):
        if not blob:
            continue
        try:
            vec = unpack_embedding(blob)
            score = cosine_similarity(q_vec, vec)
            if score > 0.05:
                scored.append((score, mid, content))
        except Exception:
            continue

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"id": mid, "score": round(score, 3), "content": content}
        for score, mid, content in scored[:top_k]
    ]


def format_relevant_for_prompt(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = ["[RELEVANT MEMORY — use naturally]"]
    for m in memories:
        lines.append(f"- {m['content']}")
    return "\n".join(lines) + "\n"
