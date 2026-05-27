"""Multi-provider manager — failover, retry, timeout."""

from __future__ import annotations

import time
from typing import Any, Callable, Iterator

from core.llm.router import RouteReason, route
from core.llm.token_manager import build_compact_messages, dedupe_assistant_replies
from core.llm.usage_tracker import quota_exceeded, record_usage
from core.llm_config import load_llm_config
from core.providers.base import LLMResponse
from core.providers.implementations import get_provider


class ProviderManager:
    def __init__(self):
        self._cache: dict[str, tuple[float, LLMResponse]] = {}
        self._cache_ttl = 120.0

    def _cache_key(self, provider: str, user_input: str) -> str:
        return f"{provider}:{user_input[:120].lower()}"

    def complete(
        self,
        *,
        system: str,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        client_id: str | None = None,
        use_tools: bool = False,
        max_tokens: int | None = None,
        reason_override: RouteReason | None = None,
    ) -> LLMResponse:
        cfg = load_llm_config()
        budget = int(cfg.get("cloud_token_budget") or 1200)
        max_out = max_tokens or int(cfg.get("cloud_max_output_tokens") or 220)

        decision = route(user_input, use_tools=use_tools)
        if reason_override:
            from core.llm.router import provider_chain

            decision.chain = provider_chain(reason_override, cfg)

        messages, meta = build_compact_messages(
            system=system,
            user_input=user_input,
            history=history,
            client_id=client_id,
            max_tokens=budget if any(p != "ollama" for p in decision.chain) else 800,
        )

        errors: list[str] = []
        for idx, name in enumerate(decision.chain):
            if name != "ollama" and quota_exceeded(name, cfg):
                errors.append(f"{name}: daily quota reached")
                continue

            ck = self._cache_key(name, user_input)
            cached = self._cache.get(ck)
            if cached and time.time() - cached[0] < self._cache_ttl:
                hit = cached[1]
                hit.raw = {"cache_hit": True}
                return hit

            provider = get_provider(name)
            if not provider:
                continue

            timeout = float(cfg.get("ollama_timeout_sec") or 45) if name == "ollama" else float(
                cfg.get("cloud_timeout_sec") or 35
            )
            retries = 1 if name == "ollama" else 2

            for attempt in range(retries):
                try:
                    t0 = time.time()
                    resp = provider.complete(messages, timeout=timeout, max_tokens=max_out)
                    resp.content = dedupe_assistant_replies(resp.content)
                    resp.fallback = idx > 0
                    resp.raw = {"route": decision.reason.value, "meta": meta}
                    if name != "ollama":
                        record_usage(name, input_tokens=resp.input_tokens, output_tokens=resp.output_tokens)
                    self._cache[ck] = (time.time(), resp)
                    return resp
                except Exception as e:
                    errors.append(f"{name}: {e}")
                    if attempt + 1 < retries:
                        time.sleep(0.4 * (attempt + 1))
                    continue

        raise RuntimeError("All providers failed: " + "; ".join(errors[:3]))

    def stream_local(
        self,
        *,
        system: str,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        client_id: str | None = None,
    ) -> Iterator[str]:
        messages, _ = build_compact_messages(
            system=system,
            user_input=user_input,
            history=history,
            client_id=client_id,
            max_tokens=800,
        )
        provider = get_provider("ollama")
        if not provider:
            return iter(())
        yield from provider.stream_tokens(messages, max_tokens=220)


_manager: ProviderManager | None = None


def get_provider_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager
