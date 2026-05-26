"""Headless UI adapter for the PWA / web clients."""

from __future__ import annotations

import asyncio
import base64
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.jarvis_tts import synthesize_bytes


class WebUIAdapter:
    """Drop-in replacement for JarvisUI when running as a web server."""

    web_mode = True

    def __init__(self):
        self._muted = False
        self._state = "OFFLINE"
        self._current_file: str | None = None
        self._file_index: dict | None = None
        self._file_context: str | None = None
        self.client_id: str | None = None
        self.on_text_command: Callable[[str], None] | None = None
        self.on_voice_request: Callable[[], None] | None = None
        self._listeners: list[Callable[[dict], None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._speech_epoch = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, listener: Callable[[dict], None]) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[dict], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _broadcast(self, event: dict) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                pass

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool) -> None:
        self._muted = value
        self._broadcast({"type": "muted", "value": value})

    @property
    def current_file(self) -> str | None:
        return self._current_file

    @property
    def file_context(self) -> str | None:
        return self._file_context

    @property
    def file_index(self) -> dict | None:
        return self._file_index

    def set_current_file(self, path: str | None) -> None:
        self._current_file = path
        if not path:
            self._file_index = None
            self._file_context = None
        if path:
            self._broadcast({"type": "file", "name": Path(path).name})
        else:
            self._broadcast({"type": "file", "name": None})

    def set_file_index(self, indexed: dict) -> None:
        self._file_index = indexed
        self._file_context = (
            f"Name: {indexed.get('name')}\nSummary: {indexed.get('summary', '')}"
        )
        self._broadcast({
            "type": "file_index",
            "name": indexed.get("name"),
            "summary": indexed.get("summary", ""),
        })

    def set_state(self, state: str) -> None:
        self._state = state
        self._broadcast({"type": "state", "value": state})

    def write_log(self, text: str) -> None:
        self._broadcast({"type": "log", "text": text})

    def cancel_speech(self) -> None:
        self._speech_epoch += 1

    def emit_alarm(self, date: str, time: str, message: str) -> None:
        self._broadcast({
            "type": "alarm",
            "date": date,
            "time": time,
            "message": message,
            "client_id": self.client_id,
        })

    def emit_speech(self, text: str) -> None:
        """Synthesize TTS and push a speech event to all listeners."""
        target_client = self.client_id
        epoch = self._speech_epoch

        def _run() -> None:
            if epoch != self._speech_epoch:
                return
            audio = synthesize_bytes(text)
            if epoch != self._speech_epoch:
                return
            event: dict = {"type": "speech", "text": text}
            if target_client:
                event["client_id"] = target_client
            if audio:
                event["audio"] = base64.b64encode(audio).decode("ascii")
            else:
                event["audio"] = None
            self._broadcast(event)

        threading.Thread(target=_run, daemon=True).start()

    def emit_speech_sync(self, text: str) -> None:
        """Blocking TTS for web — caller should already be on a worker thread."""
        epoch = self._speech_epoch
        if epoch != self._speech_epoch:
            return
        audio = synthesize_bytes(text)
        if epoch != self._speech_epoch:
            return
        event: dict = {"type": "speech", "text": text}
        if self.client_id:
            event["client_id"] = self.client_id
        event["audio"] = base64.b64encode(audio).decode("ascii") if audio else None
        self._broadcast(event)

    def submit_text(self, text: str) -> None:
        if self.on_text_command:
            self.on_text_command(text)

    def wait_for_ready(self) -> None:
        return

    wait_for_api_key = wait_for_ready
