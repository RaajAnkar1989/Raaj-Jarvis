"""Synchronous wrapper around core.tool_executor.execute_tool."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

_loop_lock = threading.Lock()
_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_thread: threading.Thread | None = None


class HeadlessUI:
    """Minimal UI adapter for agent/background tool runs."""

    web_mode = False
    muted = False
    current_file: str | None = None
    client_id: str | None = None

    def set_state(self, state: str) -> None:
        print(f"[Tool] state → {state}")

    def write_log(self, text: str) -> None:
        print(f"[Tool] {text}")


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop, _bg_thread
    with _loop_lock:
        if _bg_loop and _bg_loop.is_running():
            return _bg_loop

        def _run() -> None:
            global _bg_loop
            _bg_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_bg_loop)
            _bg_loop.run_forever()

        _bg_thread = threading.Thread(target=_run, name="jarvis-tool-loop", daemon=True)
        _bg_thread.start()
        while _bg_loop is None:
            pass
        return _bg_loop


def run_tool_sync(
    name: str,
    args: dict[str, Any] | None = None,
    *,
    ui=None,
    speak: Callable[[str], None] | None = None,
) -> str:
    from core.tool_executor import execute_tool

    adapter = ui or HeadlessUI()
    if speak is None:
        speak = lambda _t: None

    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(
        execute_tool(name, args or {}, adapter, speak),
        loop,
    )
    return str(future.result(timeout=300))
