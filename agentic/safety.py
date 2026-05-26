"""Tool registry — risk levels and confirmation requirements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DESTRUCTIVE = frozenset({
    "computer_control", "file_controller", "dev_agent", "shutdown_jarvis",
})
CONFIRM = frozenset({
    "gmail", "send_message", "computer_settings", "desktop_control",
}) | DESTRUCTIVE

BLACKLIST = frozenset({"shutdown_jarvis"})

WHITELIST: set[str] | None = None  # None = all allowed except blacklist


@dataclass
class ToolMeta:
    name: str
    risk: str  # low | medium | high
    requires_confirmation: bool


def tool_meta(name: str) -> ToolMeta:
    if name in DESTRUCTIVE:
        risk = "high"
    elif name in CONFIRM:
        risk = "medium"
    else:
        risk = "low"
    return ToolMeta(
        name=name,
        risk=risk,
        requires_confirmation=name in CONFIRM,
    )


def is_allowed(name: str) -> bool:
    if name in BLACKLIST:
        return False
    if WHITELIST is not None:
        return name in WHITELIST
    return True


def plan_requires_confirmation(steps: list[dict[str, Any]]) -> bool:
    for step in steps:
        tool = (step.get("tool") or step.get("name") or "").strip()
        if tool_meta(tool).requires_confirmation:
            return True
    return False
