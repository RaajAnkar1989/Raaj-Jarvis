"""Fast intent routing — skip LLM for common voice commands."""

from __future__ import annotations

import re

_PREFIX = re.compile(
    r"^(?:hey\s+)?jarvis[,\s]+|^(?:can you|could you|would you|please)\s+",
    re.I,
)
_YOUTUBE_OPEN = re.compile(
    r"\b(open|launch|start|go to)\s+(youtube|you\s*tube)\b", re.I
)
_YOUTUBE_PLAY_ON = re.compile(
    r"\b(?:play|put on|start|listen to)\s+(.+?)\s+on\s+(?:youtube|you\s*tube)\b",
    re.I,
)
_YOUTUBE_PLAY_TRAIL = re.compile(
    r"\b(?:play|put on|start|listen to)\s+(.+?)\s+(?:youtube|you\s*tube)\s*$",
    re.I,
)
_YOUTUBE_PREFIX = re.compile(
    r"\b(?:youtube|you\s*tube)\s+(?:play\s+)?(.+)$", re.I
)
_GENERIC_PLAY = re.compile(
    r"\b(play|put on|start|listen to)\s+(?:a\s+)?(?:nice\s+)?(?:song|music|video)s?\b",
    re.I,
)

_FILLER = re.compile(
    r"^(?:a\s+)?(?:nice\s+)?(?:song|music|video|something|anything)(?:\s+please)?$",
    re.I,
)
_DEFAULT_MUSIC = "nice relaxing music"


def _clean(text: str) -> str:
    t = text.strip()
    while True:
        n = _PREFIX.sub("", t, count=1).strip()
        if n == t:
            break
        t = n
    return t


def _normalize_query(query: str) -> str:
    q = query.strip()
    q = re.sub(r"\s+on\s+(?:youtube|you\s*tube).*$", "", q, flags=re.I).strip()
    q = re.sub(r"\s+(?:youtube|you\s*tube).*$", "", q, flags=re.I).strip()
    q = re.sub(r"[?.!]+$", "", q).strip()
    if not q or _FILLER.match(q):
        return _DEFAULT_MUSIC
    return q


def try_fast_route(text: str) -> tuple[str, dict] | None:
    """Return (tool_name, args) for instant execution, or None."""
    t = _clean(text)
    lower = t.lower()

    if _YOUTUBE_OPEN.search(lower):
        return ("browser_control", {"action": "go_to", "url": "https://www.youtube.com"})

    for pattern in (_YOUTUBE_PLAY_ON, _YOUTUBE_PLAY_TRAIL, _YOUTUBE_PREFIX):
        m = pattern.search(t)
        if m:
            query = _normalize_query(m.group(1))
            return ("youtube_video", {"action": "play", "query": query})

    if _GENERIC_PLAY.search(lower):
        return ("youtube_video", {"action": "play", "query": _DEFAULT_MUSIC})

    app_m = re.search(r"\b(open|launch|start)\s+(chrome|safari|firefox|spotify)\b", lower)
    if app_m:
        return ("open_app", {"app_name": app_m.group(2)})

    if re.search(r"\b(weather|forecast)\b", lower):
        city_m = re.search(r"(?:in|for|at)\s+([a-zA-Z\s]+?)(?:\?|$)", t, re.I)
        city = city_m.group(1).strip() if city_m else "London"
        return ("weather_report", {"city": city})

    return None
