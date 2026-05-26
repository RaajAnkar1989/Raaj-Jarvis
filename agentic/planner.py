"""Ollama-based planner — structured JSON step plans."""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from core.llm_config import load_llm_config

_PLANNER_TOOLS = (
    "open_app, web_search, weather_report, gmail, send_message, reminder, "
    "office_compose, browser_control, file_controller, youtube_video, "
    "file_processor, save_memory, computer_control, open_url"
)


def _ollama_json(prompt: str, max_tokens: int = 400) -> dict[str, Any]:
    cfg = load_llm_config()
    base = cfg.get("ollama_base_url", "http://localhost:11434").rstrip("/")
    model = cfg.get("ollama_model") or "qwen2.5:7b"
    resp = requests.post(
        f"{base}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": max_tokens, "num_ctx": 2048},
        },
        timeout=90,
    )
    resp.raise_for_status()
    raw = (resp.json().get("message") or {}).get("content") or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {}


def create_plan(goal: str, context: str = "") -> dict[str, Any]:
    prompt = f"""You are JARVIS planner. Create a minimal step plan as JSON only.

Available tools: {_PLANNER_TOOLS}

Context:
{context[:2000]}

User goal: {goal}

Return JSON:
{{
  "goal": "short goal",
  "steps": [{{"tool": "tool_name", "input": {{}}}}],
  "requires_confirmation": false
}}

Rules:
- Max 5 steps
- Use exact tool names
- Set requires_confirmation true for email send, file delete, system changes
- If simple chat with no tools, return {{"goal":"","steps":[],"requires_confirmation":false}}
"""
    plan = _ollama_json(prompt)
    if not isinstance(plan, dict):
        plan = {}
    steps = plan.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    plan["steps"] = steps[:5]
    plan.setdefault("goal", goal[:200])
    plan.setdefault("requires_confirmation", False)
    return plan
