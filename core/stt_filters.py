"""Filter Whisper hallucinations and tune transcription."""

from __future__ import annotations

import re

_HALLUCINATION_RE = re.compile(
    r"(?:"
    r"thank you for watching|thanks for watching|subscribe|subtitles by|"
    r"please subscribe|like and subscribe|"
    r"copyright|all rights reserved|"
    r"the following|this video|amara\.org|"
    r"^\s*\d+\s*(?:percent|%)?\s*$|"
    r"^\[.*\]\s*$|^\.+$"
    r")",
    re.I,
)

_JUNK_CLAUSE_RE = re.compile(
    r"^(?:"
    r"positive\s*,?\s*speak|positivity|"
    r"rate\s*(?:equals|=)\s*[^,.!?]+|"
    r"pitch\s*(?:equals|=)\s*[^,.!?]+|"
    r"volume\s*(?:equals|=)\s*[^,.!?]+|"
    r"affirmative(?:\s*,?\s*sir)?|"
    r"i can hear you clearly|"
    r"battery(?:\s+\w+){0,4}|"
    r"volume(?:\s+\w+){0,3}|"
    r"(?:\d+|one|two|three|four|five|ten|twenty|fifty|hundred)\s*(?:percent|%)|"
    r"everything(?:'?s|\s+is)\s+(?:ok|okay|fine)|"
    r"(?:it'?s|that'?s)\s+(?:ok|okay|fine)|"
    r"all\s+(?:good|clear|systems\s+go)|"
    r"routine(?:\s+command)?s?|"
    r"notification|charging|wifi|bluetooth|"
    r"thank you|thanks|okay|ok|so|um+|hmm+|you|"
    r"continue|proceed|standing by"
    r")(?:[.!?,\s]|$)",
    re.I,
)

_WHISPER_OPTS = dict(
    language="en",
    beam_size=3,
    best_of=1,
    vad_filter=True,
    condition_on_previous_text=False,
    compression_ratio_threshold=1.9,
    log_prob_threshold=-0.45,
    no_speech_threshold=0.78,
    hallucination_silence_threshold=0.85,
)


def whisper_opts() -> dict:
    return dict(_WHISPER_OPTS)


def _is_junk_clause(clause: str) -> bool:
    c = clause.strip()
    if len(c) < 3:
        return True
    if _JUNK_CLAUSE_RE.match(c):
        return True
    if _HALLUCINATION_RE.search(c):
        return True
    words = c.lower().split()
    if len(words) <= 2 and any(w in words for w in ("battery", "volume", "percent", "positive", "ok", "okay")):
        return True
    return False


_STRIP_PREFIX = re.compile(
    r"^(?:"
    r"positive\s*,?\s*speak|positivity|"
    r"rate\s*(?:equals|=)\s*[^,.!?]+|"
    r"pitch\s*(?:equals|=)\s*[^,.!?]+|"
    r"volume\s*(?:equals|=)\s*[^,.!?]+|"
    r"affirmative(?:\s*,?\s*sir)?|"
    r"i can hear you clearly|"
    r"battery(?:\s+(?:\d+|five|ten|twenty|fifteen))?(?:\s*(?:percent|%))?|"
    r"volume(?:\s+(?:\d+|five|ten|twenty|fifty|hundred))?(?:\s*(?:percent|%))?|"
    r"(?:\d+|one|two|three|four|five|ten|twenty|fifty|hundred)\s*(?:percent|%)|"
    r"everything(?:'?s|\s+is)\s+(?:ok|okay|fine)|"
    r"(?:it'?s|that'?s)\s+(?:ok|okay|fine)|"
    r"all\s+(?:good|clear|systems\s+go)|"
    r"routine(?:\s+commands?)?|"
    r"notification|charging|wifi|bluetooth|"
    r"thank\s+you|thanks|"
    r"continue|proceed|standing\s+by"
    r")[\s,.!?;\-–]*",
    re.I,
)


def prepare_user_text(text: str | None) -> str | None:
    """Strip Whisper noise captions from the start; keep the real user command."""
    if not text:
        return None
    t = re.sub(r"\s+", " ", text.strip())
    if not t:
        return None

    for _ in range(12):
        n = _STRIP_PREFIX.sub("", t, count=1).strip()
        if n == t:
            break
        t = n

    if len(t) < 4 or _is_junk_clause(t):
        return None
    if _HALLUCINATION_RE.search(t):
        return None

    alpha = sum(c.isalpha() for c in t)
    if alpha < len(t) * 0.4:
        return None
    return t


def clean_transcript(text: str | None) -> str | None:
    return prepare_user_text(text)
