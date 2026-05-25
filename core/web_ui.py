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

    def emit_speech(self, text: str) -> None:
        def _run() -> None:
            audio = synthesize_bytes(text)
            if audio:
                encoded = base64.b64encode(audio).decode("ascii")
                self._broadcast({"type": "speech", "text": text, "audio": encoded})
            else:
                self._broadcast({"type": "speech", "text": text, "audio": None})

        threading.Thread(target=_run, daemon=True).start()

    def submit_text(self, text: str) -> None:
        if self.on_text_command:
            self.on_text_command(text)

    def wait_for_ready(self) -> None:
        return

    wait_for_api_key = wait_for_ready
