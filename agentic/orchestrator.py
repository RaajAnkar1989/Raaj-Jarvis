"""Central agent orchestrator — plan → execute → memory → respond."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, TYPE_CHECKING

from agentic.context import build_agent_context, persist_turn_summary
from agentic.planner import create_plan
from agentic.safety import plan_requires_confirmation
from agentic.tools_gateway import execute_tool_safe
from memory.working import append_turn

if TYPE_CHECKING:
    from core.local_engine import JarvisLocal

_MULTI_STEP_RE = re.compile(
    r"\b(and then|after that|multi.?step|plan|schedule|organize|research and|"
    r"first.*then|step by step|automate|workflow)\b",
    re.I,
)

_CONFIRM_RE = re.compile(r"\b(yes proceed|go ahead|confirm|proceed|do it)\b", re.I)


def should_use_agent(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 12:
        return False
    if _MULTI_STEP_RE.search(t):
        return True
    if t.count(",") >= 2 and _ACTION_HINT(t):
        return True
    return False


def _ACTION_HINT(t: str) -> bool:
    return bool(re.search(
        r"\b(open|send|email|search|remind|create|write|file|browser|message)\b", t, re.I
    ))


def _normalize_step(step: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    tool = (step.get("tool") or step.get("name") or "").strip()
    inp = step.get("input") or step.get("args") or step.get("parameters") or {}
    if isinstance(inp, str):
        try:
            inp = json.loads(inp)
        except json.JSONDecodeError:
            inp = {"query": inp}
    if not isinstance(inp, dict):
        inp = {}
    return tool, inp


async def run_agent_turn(
    engine: "JarvisLocal",
    text: str,
    *,
    confirmed: bool = False,
) -> str | None:
    """
    Run agent loop for one user turn.
    Returns response text, or None to fall back to standard chat.
    """
    client_id = getattr(engine.ui, "client_id", None)
    append_turn(client_id, "user", text)

    engine.speak_immediate("One moment, sir.")

    ctx = build_agent_context(
        text,
        client_id=client_id,
        file_ctx=getattr(engine.ui, "file_context", None),
    )

    plan = await asyncio.to_thread(create_plan, text, ctx)
    steps = plan.get("steps") or []
    if not steps:
        return None

    if plan_requires_confirmation(steps) and not confirmed and not _CONFIRM_RE.search(text):
        goal = plan.get("goal") or text[:80]
        preview = ", ".join(_normalize_step(s)[0] for s in steps[:4])
        msg = (
            f"I've planned this: {goal}. Steps: {preview}. "
            "Shall I proceed? Say 'yes proceed'."
        )
        engine.ui.write_log(f"Jarvis: {msg}")
        engine.speak(msg)
        append_turn(client_id, "assistant", msg)
        engine._pending_plan = plan  # type: ignore[attr-defined]
        return msg

    engine.ui.write_log("SYS: Agent executing plan…")
    results: list[str] = []

    for step in steps:
        tool, args = _normalize_step(step)
        if not tool:
            continue
        result, needs_confirm = await execute_tool_safe(
            tool,
            args,
            engine.ui,
            engine.speak,
            client_id=client_id or "",
            confirmed=confirmed or _CONFIRM_RE.search(text) is not None,
        )
        if needs_confirm:
            engine.speak(result)
            engine._pending_plan = plan  # type: ignore[attr-defined]
            return result
        if result:
            results.append(result)

    if hasattr(engine, "_pending_plan"):
        delattr(engine, "_pending_plan")

    if not results:
        return None

    summary = results[-1] if len(results) == 1 else " ".join(r[:120] for r in results[:3])
    append_turn(client_id, "assistant", summary)
    persist_turn_summary(client_id, text, summary)
    engine.speak(summary)
    return summary


async def run_pending_plan(engine: "JarvisLocal", text: str) -> str | None:
    if not _CONFIRM_RE.search(text):
        return None
    plan = getattr(engine, "_pending_plan", None)
    if not plan:
        return None
    steps = plan.get("steps") or []
    results: list[str] = []
    client_id = getattr(engine.ui, "client_id", None)
    for step in steps:
        tool, args = _normalize_step(step)
        if not tool:
            continue
        result, _ = await execute_tool_safe(
            tool, args, engine.ui, engine.speak,
            client_id=client_id or "", confirmed=True,
        )
        if result:
            results.append(result)
    delattr(engine, "_pending_plan")
    summary = results[-1] if results else "Done, sir."
    engine.speak(summary)
    return summary
