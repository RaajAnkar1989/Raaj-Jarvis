"""Always-on mic with VAD + local Whisper STT (echo-safe)."""

from __future__ import annotations

import queue
import re
import tempfile
import threading
import time
import wave
from collections.abc import Callable
from pathlib import Path

from core.llm_config import load_llm_config
from core.stt_filters import clean_transcript, whisper_opts

import numpy as np
import sounddevice as sd

_whisper_model = None
_whisper_model_name: str | None = None
_whisper_lock = threading.Lock()
_mic_lock = threading.Lock()
_listen_gate: Callable[[], bool] | None = None
SAMPLE_RATE = 16000


def _whisper_model_id() -> str:
    return load_llm_config().get("whisper_model") or "base.en"


def set_listen_gate(fn: Callable[[], bool] | None) -> None:
    """Return True when the mic is allowed to capture (not during JARVIS speech)."""
    global _listen_gate
    _listen_gate = fn


def _may_listen() -> bool:
    if _listen_gate is None:
        return True
    try:
        return bool(_listen_gate())
    except Exception:
        return False


def warmup_stt() -> None:
    _get_whisper()


def _get_whisper():
    global _whisper_model, _whisper_model_name
    model_id = _whisper_model_id()
    with _whisper_lock:
        if _whisper_model is None or _whisper_model_name != model_id:
            from faster_whisper import WhisperModel

            _whisper_model = WhisperModel(
                model_id,
                device="cpu",
                compute_type="int8",
            )
            _whisper_model_name = model_id
    return _whisper_model


def _save_wav(recording: np.ndarray, path: str) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(recording.tobytes())


def record_until_silence(
    max_seconds: float = 6.5,
    silence_ms: int = 650,
    speech_threshold: int = 700,
) -> np.ndarray | None:
    """Record one utterance. Aborts if listen gate closes (JARVIS speaking)."""
    block_ms = 50
    block_size = int(SAMPLE_RATE * block_ms / 1000)
    max_blocks = int(max_seconds * 1000 / block_ms)
    silence_blocks = max(1, int(silence_ms / block_ms))

    audio_q: queue.Queue[np.ndarray] = queue.Queue()

    def callback(indata, frames, time_info, status):
        if _may_listen():
            audio_q.put(indata.copy())

    chunks: list[np.ndarray] = []
    heard_speech = False
    silent_run = 0
    speech_run = 0
    min_speech_blocks = 3

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=block_size,
        callback=callback,
    ):
        for _ in range(max_blocks):
            if not _may_listen():
                if heard_speech:
                    return None
                heard_speech = False
                silent_run = 0
                chunks.clear()
                while not audio_q.empty():
                    try:
                        audio_q.get_nowait()
                    except queue.Empty:
                        break
                time.sleep(0.05)
                continue

            try:
                chunk = audio_q.get(timeout=0.12)
            except queue.Empty:
                if heard_speech and silent_run >= silence_blocks:
                    break
                continue

            peak = int(np.max(np.abs(chunk)))
            if peak >= speech_threshold:
                speech_run += 1
                if speech_run >= min_speech_blocks:
                    heard_speech = True
                silent_run = 0
                if heard_speech:
                    chunks.append(chunk)
            else:
                speech_run = 0
                if heard_speech:
                    silent_run += 1
                    chunks.append(chunk)
                    if silent_run >= silence_blocks:
                        break

    if not chunks:
        return None
    audio = np.concatenate(chunks, axis=0)
    if len(audio) < int(SAMPLE_RATE * 0.55):
        return None
    peak = float(np.max(np.abs(audio)))
    if peak < 900:
        return None
    return audio


def transcribe_audio(recording: np.ndarray) -> str | None:
    wav_path = tempfile.mktemp(suffix=".wav")
    try:
        _save_wav(recording.reshape(-1), wav_path)
        segments, _ = _get_whisper().transcribe(wav_path, **whisper_opts())
        parts: list[str] = []
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            if getattr(seg, "no_speech_prob", 0.0) > 0.55:
                continue
            if getattr(seg, "avg_logprob", 0.0) < -0.85:
                continue
            parts.append(text)
        return clean_transcript(" ".join(parts).strip())
    finally:
        Path(wav_path).unlink(missing_ok=True)


def _strip_wake_words(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^(?:hey\s+)?jarvis[,\s]+", "", t, flags=re.I)
    return t.strip() or text.strip()


def listen_once() -> tuple[str | None, str | None]:
    if not _may_listen():
        return None, None
    if not _mic_lock.acquire(blocking=False):
        return None, None

    try:
        if not _may_listen():
            return None, None
        try:
            recording = record_until_silence()
        except Exception as e:
            return None, f"Microphone error: {e}"

        if recording is None or not _may_listen():
            return None, None

        text = transcribe_audio(recording)
        if text:
            return _strip_wake_words(text), None
        return None, None
    finally:
        _mic_lock.release()


def transcribe_file(path: str, min_bytes: int = 2000) -> str | None:
    try:
        if Path(path).stat().st_size < min_bytes:
            return None
        segments, _ = _get_whisper().transcribe(path, **whisper_opts())
        parts = [
            s.text.strip()
            for s in segments
            if s.text.strip() and getattr(s, "no_speech_prob", 0.0) <= 0.55
        ]
        return clean_transcript(" ".join(parts).strip())
    except Exception:
        return None
