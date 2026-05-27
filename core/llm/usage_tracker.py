"""Daily token quota and provider usage tracking."""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

_lock = threading.Lock()
_USAGE_FILE = Path(__file__).resolve().parent.parent / "data" / "provider_usage.json"


def _load() -> dict:
    if not _USAGE_FILE.exists():
        return {}
    try:
        return json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _today_key() -> str:
    return date.today().isoformat()


def record_usage(
    provider: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    requests: int = 1,
) -> None:
    with _lock:
        data = _load()
        day = data.setdefault(_today_key(), {})
        row = day.setdefault(provider, {"in": 0, "out": 0, "requests": 0})
        row["in"] += input_tokens
        row["out"] += output_tokens
        row["requests"] += requests
        _save(data)


def get_usage_today() -> dict:
    with _lock:
        data = _load()
        return data.get(_today_key(), {})


def quota_exceeded(provider: str, cfg: dict) -> bool:
    limits = cfg.get("provider_daily_limits") or {}
    limit = int(limits.get(provider, 0) or 0)
    if limit <= 0:
        return False
    usage = get_usage_today().get(provider, {})
    total = int(usage.get("in", 0)) + int(usage.get("out", 0))
    return total >= limit


def total_cloud_tokens_today() -> int:
    usage = get_usage_today()
    return sum(int(v.get("in", 0)) + int(v.get("out", 0)) for v in usage.values())
