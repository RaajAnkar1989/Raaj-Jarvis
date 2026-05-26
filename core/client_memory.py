"""Per-device / per-client memory stored on the JARVIS backend."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()
_BASE = Path(__file__).resolve().parent.parent / "data" / "client_memory"
_MAX_VALUE = 400
_MAX_ENTRIES = 40
_MAX_HISTORY = 20


def _path(client_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", client_id or "default")[:64] or "default"
    return _BASE / f"{safe}.json"


def load_client_memory(client_id: str | None) -> dict:
    if not client_id:
        return {"entries": {}, "updated": None}
    p = _path(client_id)
    if not p.exists():
        return {"entries": {}, "updated": None}
    with _lock:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("entries"), dict):
                return data
        except Exception:
            pass
    return {"entries": {}, "updated": None}


def save_client_memory(client_id: str, data: dict) -> None:
    if not client_id:
        return
    _BASE.mkdir(parents=True, exist_ok=True)
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    with _lock:
        _path(client_id).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def remember(client_id: str | None, key: str, value: str) -> None:
    if not client_id or not key or not value:
        return
    val = value.strip()[:_MAX_VALUE]
    data = load_client_memory(client_id)
    entries = data.setdefault("entries", {})
    entries[key.strip().lower()[:80]] = {
        "value": val,
        "updated": datetime.now().strftime("%Y-%m-%d"),
    }
    if len(entries) > _MAX_ENTRIES:
        oldest = sorted(entries.items(), key=lambda x: x[1].get("updated", ""))
        for k, _ in oldest[: len(entries) - _MAX_ENTRIES]:
            del entries[k]
    save_client_memory(client_id, data)


def format_for_prompt(client_id: str | None) -> str:
    data = load_client_memory(client_id)
    entries = data.get("entries") or {}
    if not entries:
        return ""
    lines = ["[DEVICE MEMORY — use naturally]"]
    for key, entry in list(entries.items())[-20:]:
        val = entry.get("value") if isinstance(entry, dict) else str(entry)
        if val:
            lines.append(f"- {key.replace('_', ' ')}: {val}")
    return "\n".join(lines) + "\n"


def load_chat_history(client_id: str | None) -> list[dict]:
    if not client_id:
        return []
    data = load_client_memory(client_id)
    hist = data.get("chat_history") or []
    out: list[dict] = []
    for item in hist:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out[-_MAX_HISTORY:]


def append_chat_turn(client_id: str | None, role: str, content: str) -> None:
    if not client_id or role not in ("user", "assistant"):
        return
    text = (content or "").strip()
    if not text or text.startswith("[FILE_READY]"):
        return
    data = load_client_memory(client_id)
    hist = data.get("chat_history") or []
    hist.append({"role": role, "content": text[:800]})
    data["chat_history"] = hist[-_MAX_HISTORY:]
    save_client_memory(client_id, data)


def auto_remember_from_text(client_id: str | None, text: str) -> None:
    """Lightweight extraction so JARVIS learns without a tool call."""
    if not client_id or not text:
        return
    t = text.strip()
    patterns = [
        (r"(?:call me|address me as)\s+([A-Za-z]+)", "address_as"),
        (r"(?:my name is|call me|i am)\s+([A-Za-z][A-Za-z\s'-]{1,30})", "name"),
        (r"(?:i like|i love|i enjoy)\s+(.{3,80})", "likes"),
        (r"(?:i live in|i'm from|i am from)\s+(.{2,60})", "location"),
        (r"(?:remember that|remember)\s+(.{5,120})", "note"),
        (r"(?:my favourite|my favorite)\s+(.{3,80})", "favorite"),
    ]
    for pat, key in patterns:
        m = re.search(pat, t, re.I)
        if m:
            remember(client_id, key, m.group(1).strip().rstrip("."))
