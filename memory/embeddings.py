"""Local embeddings via Ollama (nomic-embed-text) with keyword fallback."""

from __future__ import annotations

import math
import re
import struct
from typing import Iterable

import requests

from core.llm_config import load_llm_config

_EMBED_MODEL = "nomic-embed-text"
_cache: dict[str, list[float]] = {}


def _base_url() -> str:
    return load_llm_config().get("ollama_base_url", "http://localhost:11434").rstrip("/")


def embed_text(text: str) -> list[float] | None:
    key = text.strip()[:512]
    if not key:
        return None
    if key in _cache:
        return _cache[key]
    try:
        resp = requests.post(
            f"{_base_url()}/api/embeddings",
            json={"model": _EMBED_MODEL, "prompt": key},
            timeout=30,
        )
        if resp.ok:
            vec = resp.json().get("embedding")
            if isinstance(vec, list) and vec:
                _cache[key] = vec
                return vec
    except Exception:
        pass
    return _keyword_vector(key)


def _keyword_vector(text: str) -> list[float]:
    tokens = re.findall(r"[a-z0-9]{3,}", text.lower())
    if not tokens:
        return [0.0] * 32
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    keys = sorted(freq.keys())[:32]
    while len(keys) < 32:
        keys.append("")
    return [float(freq.get(k, 0)) for k in keys]


def pack_embedding(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def unpack_embedding(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    va, vb = list(a), list(b)
    if len(va) != len(vb) or not va:
        return 0.0
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
