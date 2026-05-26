"""In-memory working memory (short-term) per client."""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

_lock = threading.Lock()
_MAX = 50
_store: dict[str, deque[dict[str, Any]]] = {}


def append_turn(client_id: str | None, role: str, content: str) -> None:
    cid = (client_id or "default").strip() or "default"
    text = (content or "").strip()
    if not text or role not in ("user", "assistant", "system"):
        return
    with _lock:
        buf = _store.setdefault(cid, deque(maxlen=_MAX))
        buf.append({"role": role, "content": text[:1200]})


def get_recent(client_id: str | None, limit: int = 30) -> list[dict[str, str]]:
    cid = (client_id or "default").strip() or "default"
    with _lock:
        buf = _store.get(cid, deque())
        return [{"role": m["role"], "content": m["content"]} for m in list(buf)[-limit:]]


def clear(client_id: str | None) -> None:
    cid = (client_id or "default").strip() or "default"
    with _lock:
        _store.pop(cid, None)
