"""Fast intent routing — skip LLM for common voice commands."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_PREFIX = re.compile(
    r"^(?:hey\s+)?jarvis[,\s]+|^(?:can you|could you|would you|please)\s+",
    re.I,
)
_YOUTUBE_OPEN = re.compile(
    r"^\s*(?:open|launch|start|go to)\s+(?:the\s+)?(?:youtube|you\s*tube)\s*$",
    re.I,
)
_YOUTUBE_PLAY_ON = re.compile(
    r"\b(?:play|put on|start|listen to|hear)\s+(.+?)\s+on\s+(?:youtube|you\s*tube)\b",
    re.I,
)
_YOUTUBE_PLAY_TRAIL = re.compile(
    r"\b(?:play|put on|start|listen to|hear)\s+(.+?)\s+(?:youtube|you\s*tube)\s*$",
    re.I,
)
_YOUTUBE_PREFIX = re.compile(
    r"\b(?:youtube|you\s*tube)\s+(?:play\s+)?(.+)$", re.I
)
_SONG_PLAY = re.compile(
    r"\b(?:play|put on|start|listen to|hear)\s+(?:a\s+|an\s+|some\s+)?(.+?\s+song)\b",
    re.I,
)
_MUSIC_PLAY = re.compile(
    r"\b(?:play|put on|start|listen to|hear)\s+(?:a\s+|an\s+|some\s+)?(.+?\s+(?:music|track|video))\b",
    re.I,
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

_WORD_NUM = {
    "a": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "ten": 10,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 45,
    "sixty": 60,
}


def _word_to_int(token: str) -> int | None:
    t = token.strip().lower()
    if t.isdigit():
        return int(t)
    return _WORD_NUM.get(t)


def _parse_timer(text: str) -> tuple[str, dict] | None:
    lower = text.lower()
    if not re.search(r"\b(timer|timers|remind|alarm|countdown)\b", lower):
        if not re.search(r"\b(minute|min|hour|second)s?\b", lower):
            return None

    m = re.search(
        r"\b(\d+|one|two|three|four|five|ten|fifteen|twenty|thirty|sixty)\s*"
        r"(minute|min|minutes|hour|hr|hours|second|sec|seconds)s?\b",
        lower,
    )
    if not m:
        return None

    amount = _word_to_int(m.group(1))
    if not amount or amount <= 0:
        return None

    unit = m.group(2)
    if unit.startswith("hour") or unit == "hr":
        delta = timedelta(hours=amount)
        label = f"{amount} hour timer"
    elif unit.startswith("sec"):
        delta = timedelta(seconds=amount)
        label = f"{amount} second timer"
    else:
        delta = timedelta(minutes=amount)
        label = f"{amount} minute timer"

    target = datetime.now() + delta
    msg_m = re.search(r"\bfor\s+(.+?)(?:\s+timer|\s+alarm|$)", text, re.I)
    message = (msg_m.group(1).strip() if msg_m else label)[:120] or label

    return (
        "reminder",
        {
            "date": target.strftime("%Y-%m-%d"),
            "time": target.strftime("%H:%M"),
            "message": message,
        },
    )


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

    if _YOUTUBE_OPEN.match(lower):
        return ("browser_control", {"action": "go_to", "url": "https://www.youtube.com"})

    for pattern in (_YOUTUBE_PLAY_ON, _YOUTUBE_PLAY_TRAIL, _YOUTUBE_PREFIX):
        m = pattern.search(t)
        if m:
            query = _normalize_query(m.group(1))
            return ("youtube_video", {"action": "play", "query": query})

    for pattern in (_SONG_PLAY, _MUSIC_PLAY):
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

    timer = _parse_timer(t)
    if timer:
        return timer

    return None
