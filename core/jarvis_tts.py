"""Natural JARVIS-style neural text-to-speech (Microsoft Edge neural voices)."""

from __future__ import annotations

import asyncio
import platform
import queue
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from core.llm_config import load_llm_config

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"
DEFAULT_RATE = "-2%"
DEFAULT_PITCH = "+0Hz"
DEFAULT_VOLUME = "+0%"

_tts_lock = threading.Lock()
_warmed_up = False
_speech_q: queue.Queue[str | None] = queue.Queue()
_speech_thread: threading.Thread | None = None
_on_speech_start: callable | None = None
_on_speech_end: callable | None = None
_disable_local_playback = False
_speech_active = 0
_speech_active_lock = threading.Lock()
_prefetch_lock = threading.Lock()
_prefetch_text: str | None = None
_prefetch_path: str | None = None
_prefetch_thread: threading.Thread | None = None


def _cfg() -> dict:
    return load_llm_config()


def _voice() -> str:
    return _cfg().get("tts_voice") or DEFAULT_VOICE


def _rate() -> str:
    return _cfg().get("tts_rate") or DEFAULT_RATE


def _pitch() -> str:
    return _cfg().get("tts_pitch") or DEFAULT_PITCH


def _volume() -> str:
    return _cfg().get("tts_volume") or DEFAULT_VOLUME


def set_speech_hooks(on_start=None, on_end=None) -> None:
    global _on_speech_start, _on_speech_end
    _on_speech_start = on_start
    _on_speech_end = on_end


def set_disable_local_playback(disable: bool) -> None:
    """When True, speak() will not play through Mac/PC speakers (PWA remote clients only)."""
    global _disable_local_playback
    _disable_local_playback = disable


def jarvisify(text: str) -> str:
    """Light touch-ups — keep speech conversational, not stiff."""
    t = text.strip()
    if not t:
        return t

    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"^(?:okay|ok|sure|yes)[,.]?\s+", "", t, flags=re.I)
    t = t.replace("...", ".")
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    return t


def _make_communicate(text: str):
    import edge_tts

    return edge_tts.Communicate(
        text,
        _voice(),
        rate=_rate(),
        pitch=_pitch(),
        volume=_volume(),
    )


async def _synthesize_bytes(text: str) -> bytes:
    communicate = _make_communicate(text)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


def synthesize_bytes(text: str) -> bytes | None:
    clean = jarvisify(text.strip())
    if not clean:
        return None
    with _tts_lock:
        try:
            data = asyncio.run(_synthesize_bytes(clean))
            return data if data else None
        except Exception:
            return None


async def _stream_to_file(text: str, out_path: str) -> None:
    communicate = _make_communicate(text)
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                f.write(chunk["data"])


def _play_file(path: str) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["afplay", path], check=False)
        return

    if system == "Windows":
        import winsound

        winsound.PlaySound(path, winsound.SND_FILENAME)
        return

    for cmd in (
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
        ["mpv", "--no-video", "--really-quiet", path],
        ["paplay", path],
    ):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=False)
            return


def _fallback_say(text: str) -> None:
    if platform.system() != "Darwin":
        print(f"[JARVIS] {text}")
        return
    for voice in ("Daniel", "Fred"):
        r = subprocess.run(["say", "-v", voice, "-r", 185, text], check=False)
        if r.returncode == 0:
            return


def _speech_begin() -> None:
    global _speech_active
    with _speech_active_lock:
        _speech_active += 1
        if _speech_active == 1 and _on_speech_start:
            _on_speech_start()


def _speech_end() -> None:
    global _speech_active
    with _speech_active_lock:
        _speech_active = max(0, _speech_active - 1)
        if _speech_active == 0 and _speech_q.empty() and _on_speech_end:
            _on_speech_end()


def _synth_to_file(text: str) -> str:
    path = tempfile.mktemp(suffix=".mp3")
    with _tts_lock:
        asyncio.run(_stream_to_file(text, path))
    return path


def _start_prefetch(text: str) -> None:
    global _prefetch_thread, _prefetch_text, _prefetch_path

    def run() -> None:
        global _prefetch_text, _prefetch_path
        try:
            path = _synth_to_file(text)
            with _prefetch_lock:
                if _prefetch_text == text:
                    _prefetch_path = path
        except Exception:
            pass

    with _prefetch_lock:
        if _prefetch_text == text and _prefetch_path:
            return
        if _prefetch_path:
            Path(_prefetch_path).unlink(missing_ok=True)
        _prefetch_text = text
        _prefetch_path = None
    _prefetch_thread = threading.Thread(target=run, daemon=True)
    _prefetch_thread.start()


def _take_prefetch(text: str) -> str | None:
    global _prefetch_text, _prefetch_path
    with _prefetch_lock:
        if _prefetch_text == text and _prefetch_path and Path(_prefetch_path).exists():
            path = _prefetch_path
            _prefetch_text = None
            _prefetch_path = None
            return path
    return None


def _peek_next_queued() -> str | None:
    with _speech_q.mutex:
        if _speech_q.queue:
            nxt = _speech_q.queue[0]
            return nxt if isinstance(nxt, str) else None
    return None


def _speak_blocking(text: str) -> None:
    clean = jarvisify(text.strip())
    if not clean:
        return

    _speech_begin()
    path = _take_prefetch(clean)
    try:
        if not path:
            path = _synth_to_file(clean)
        if Path(path).stat().st_size > 0:
            _play_file(path)
        else:
            _fallback_say(clean)
    except Exception:
        _fallback_say(clean)
    finally:
        Path(path).unlink(missing_ok=True)
        _speech_end()

    nxt = _peek_next_queued()
    if nxt:
        _start_prefetch(jarvisify(nxt))


def _speech_worker() -> None:
    while True:
        item = _speech_q.get()
        if item is None:
            break
        try:
            _speak_blocking(item)
        finally:
            _speech_q.task_done()


def _ensure_speech_worker() -> None:
    global _speech_thread
    if _speech_thread is None or not _speech_thread.is_alive():
        _speech_thread = threading.Thread(target=_speech_worker, daemon=True)
        _speech_thread.start()


def speak(text: str) -> None:
    """Queue speech — returns immediately; plays in order."""
    if _disable_local_playback:
        return
    clean = jarvisify(text.strip())
    if not clean:
        return
    _ensure_speech_worker()
    is_first = _speech_q.empty() and _speech_active == 0
    _speech_q.put(clean)
    if is_first:
        _start_prefetch(clean)


def speak_now(text: str) -> None:
    """Blocking speak — call from a worker thread."""
    if _disable_local_playback:
        return
    _speak_blocking(text)


def warmup_tts() -> None:
    global _warmed_up
    if _warmed_up:
        return
    try:
        path = tempfile.mktemp(suffix=".mp3")
        asyncio.run(_stream_to_file("Ready.", path))
        Path(path).unlink(missing_ok=True)
        _warmed_up = True
    except Exception:
        pass
