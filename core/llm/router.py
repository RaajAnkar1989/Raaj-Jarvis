"""Smart routing — local-first, cloud for hard tasks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from core.llm_config import load_llm_config


class RouteReason(str, Enum):
    CASUAL = "casual"
    TOOLS = "tools"
    CODING = "coding"
    REASONING = "reasoning"
    LONG_CONTEXT = "long_context"
    WEB = "web"
    TIMEOUT_FALLBACK = "timeout_fallback"
    QUOTA_FALLBACK = "quota_fallback"


@dataclass
class RouteDecision:
    primary: str
    reason: RouteReason
    allow_cloud: bool
    chain: list[str]


_CODING = re.compile(
    r"\b(code|python|javascript|typescript|debug|refactor|function|class|api|sql|regex)\b",
    re.I,
)
_REASONING = re.compile(
    r"\b(analy[sz]e|compare|pros and cons|strategy|plan|why|explain in detail|think through)\b",
    re.I,
)
_WEB = re.compile(r"\b(search the web|google|latest news|current events)\b", re.I)


def classify_intent(text: str, *, use_tools: bool = False, char_count: int = 0) -> RouteReason:
    t = (text or "").strip()
    if use_tools:
        return RouteReason.TOOLS
    if _CODING.search(t):
        return RouteReason.CODING
    if _REASONING.search(t):
        return RouteReason.REASONING
    if _WEB.search(t):
        return RouteReason.WEB
    if char_count > 6000 or len(t) > 800:
        return RouteReason.LONG_CONTEXT
    return RouteReason.CASUAL


def provider_chain(reason: RouteReason, cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_llm_config()
    enabled = {
        "ollama": cfg.get("enable_ollama", True) is not False,
        "gemini": bool(cfg.get("enable_gemini", True)) and _has_key(cfg, "gemini"),
        "openai": bool(cfg.get("enable_openai", False)) and _has_key(cfg, "openai"),
        "anthropic": bool(cfg.get("enable_anthropic", False)) and _has_key(cfg, "anthropic"),
    }

    def pick(order: list[str]) -> list[str]:
        return [p for p in order if enabled.get(p)]

    if reason == RouteReason.CASUAL:
        chain = pick(["ollama", "gemini", "openai", "anthropic"])
    elif reason == RouteReason.TOOLS:
        chain = pick(["ollama"])
    elif reason == RouteReason.CODING:
        chain = pick(["ollama", "openai", "gemini", "anthropic"])
    elif reason == RouteReason.REASONING:
        chain = pick(["ollama", "anthropic", "gemini", "openai"])
    elif reason == RouteReason.LONG_CONTEXT:
        chain = pick(["ollama", "gemini", "openai", "anthropic"])
    elif reason == RouteReason.WEB:
        chain = pick(["ollama", "gemini"])
    else:
        chain = pick(["ollama", "gemini", "openai", "anthropic"])

    return chain or ["ollama"]


def _has_key(cfg: dict, provider: str) -> bool:
    from core.secrets import decrypt_secret

    keys = {
        "gemini": "gemini_api_key",
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
    }
    raw = cfg.get(keys.get(provider, ""), "")
    if not raw:
        return False
    if str(raw).startswith(("enc:", "b64:")):
        return bool(decrypt_secret(str(raw)))
    return bool(str(raw).strip())


def route(text: str, *, use_tools: bool = False, char_count: int = 0) -> RouteDecision:
    cfg = load_llm_config()
    reason = classify_intent(text, use_tools=use_tools, char_count=char_count)
    chain = provider_chain(reason, cfg)
    allow_cloud = reason != RouteReason.TOOLS and any(p != "ollama" for p in chain)
    return RouteDecision(
        primary=chain[0] if chain else "ollama",
        reason=reason,
        allow_cloud=allow_cloud,
        chain=chain,
    )
