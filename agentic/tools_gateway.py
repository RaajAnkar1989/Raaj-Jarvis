"""Validated tool gateway — logging, safety, wraps core/tool_executor."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from agentic.safety import is_allowed, tool_meta
from memory.db import log_tool_execution


async def execute_tool_safe(
    name: str,
    args: dict[str, Any],
    ui,
    speak: Callable[[str], None],
    *,
    client_id: str = "",
    confirmed: bool = False,
) -> tuple[str, bool]:
    """
    Run a tool with safety checks and audit log.
    Returns (result_text, needs_confirmation).
    """
    if not is_allowed(name):
        return f"Tool '{name}' is not permitted.", False

    meta = tool_meta(name)
    if meta.requires_confirmation and not confirmed:
        return (
            f"This action ({name}) needs confirmation. Say 'yes proceed' to continue.",
            True,
        )

    from core.tool_executor import execute_tool

    try:
        result = await execute_tool(name, args, ui, speak)
        ok = True
        text = str(result or "Done.")
    except Exception as e:
        traceback.print_exc()
        ok = False
        text = f"Tool {name} failed: {e}"

    log_tool_execution(name, args, text, ok=ok, client_id=client_id)
    return text, False
