"""Supertonic on-device TTS (ONNX Runtime).

Lightning-fast, fully local text-to-speech — no network, no API calls.
Falls back gracefully (is_available() == False) when the package or model
assets are not installed, so callers can route to edge-tts instead.

Model: https://github.com/supertone-inc/supertonic
"""

from __future__ import annotations

import io
import re
import threading
import wave

from core.llm_config import load_llm_config

DEFAULT_VOICE = "M1"
DEFAULT_LANG = "en"
DEFAULT_STEPS = 8
SAMPLE_RATE = 44100

_lock = threading.Lock()
_tts = None
_style = None
_style_name: str | None = None
_unavailable = False
_warmed = False


def _cfg() -> dict:
    return load_llm_config()


def _voice_name() -> str:
    return _cfg().get("supertonic_voice") or DEFAULT_VOICE


def _lang() -> str:
    return _cfg().get("supertonic_lang") or DEFAULT_LANG


def _steps() -> int:
    try:
        return max(5, min(12, int(_cfg().get("supertonic_steps") or DEFAULT_STEPS)))
    except Exception:
        return DEFAULT_STEPS


def _speed() -> float:
    """Map the existing edge-style rate (e.g. '+8%') to a 0.7–2.0 multiplier."""
    cfg = _cfg()
    explicit = cfg.get("supertonic_speed")
    if explicit is not None:
        try:
            return max(0.7, min(2.0, float(explicit)))
        except Exception:
            pass
    rate = str(cfg.get("tts_rate") or "+0%")
    m = re.search(r"([+-]?\d+)", rate)
    pct = int(m.group(1)) if m else 0
    return max(0.7, min(2.0, 1.0 + pct / 100.0))


def _load() -> bool:
    """Lazily load the Supertonic model. Returns True when ready."""
    global _tts, _style, _style_name, _unavailable
    if _unavailable:
        return False
    if _tts is not None and _style is not None and _style_name == _voice_name():
        return True
    with _lock:
        if _tts is not None and _style is not None and _style_name == _voice_name():
            return True
        try:
            from supertonic import TTS  # type: ignore

            if _tts is None:
                _tts = TTS(auto_download=True)
            _style = _tts.get_voice_style(voice_name=_voice_name())
            _style_name = _voice_name()
            return True
        except Exception as e:  # pragma: no cover - depends on optional install
            print(f"[Supertonic] unavailable ({e}); falling back to edge-tts")
            _unavailable = True
            _tts = None
            _style = None
            return False


def is_available() -> bool:
    return _load()


def _to_wav_bytes(wav) -> bytes:
    import numpy as np

    samples = np.asarray(wav, dtype=np.float32).squeeze()
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def synthesize_wav_bytes(text: str) -> bytes | None:
    """Synthesize 16-bit 44.1kHz WAV bytes, or None if Supertonic is unavailable."""
    clean = (text or "").strip()
    if not clean:
        return None
    if not _load():
        return None
    try:
        with _lock:
            wav, _duration = _tts.synthesize(
                text=clean,
                lang=_lang(),
                voice_style=_style,
                total_steps=_steps(),
                speed=_speed(),
            )
        return _to_wav_bytes(wav)
    except Exception as e:  # pragma: no cover
        print(f"[Supertonic] synth error: {e}")
        return None


def warmup() -> None:
    global _warmed
    if _warmed:
        return
    if synthesize_wav_bytes("Ready.") is not None:
        _warmed = True
