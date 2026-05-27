"""Provider implementations."""

from __future__ import annotations

import time
from typing import Any

import requests

from core.llm.token_manager import estimate_tokens
from core.llm_config import load_llm_config
from core.providers.base import LLMResponse


def _opts() -> dict[str, Any]:
    return load_llm_config()


class OllamaProvider:
    name = "ollama"

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        timeout: float = 45,
        max_tokens: int = 256,
        stream: bool = False,
    ) -> LLMResponse:
        cfg = _opts()
        base = cfg.get("ollama_base_url", "http://localhost:11434").rstrip("/")
        model = cfg.get("ollama_model") or "qwen2.5:7b"
        opts = cfg.get("ollama_options") or {}
        t0 = time.time()
        resp = requests.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": stream,
                "options": {
                    "temperature": float(opts.get("temperature", 0.45)),
                    "num_predict": max_tokens,
                    "num_ctx": int(opts.get("num_ctx", 1024)),
                },
            },
            timeout=timeout,
            stream=stream,
        )
        resp.raise_for_status()
        if stream:
            content = ""
            for line in resp.iter_lines():
                if not line:
                    continue
                import json

                chunk = json.loads(line)
                content += (chunk.get("message") or {}).get("content") or ""
            data = {"message": {"content": content}}
        else:
            data = resp.json()
        text = (data.get("message") or {}).get("content") or ""
        ms = int((time.time() - t0) * 1000)
        inp = estimate_tokens("\n".join(m["content"] for m in messages))
        return LLMResponse(
            content=text.strip(),
            provider=self.name,
            model=model,
            input_tokens=inp,
            output_tokens=estimate_tokens(text),
            latency_ms=ms,
        )

    def stream_tokens(self, messages: list[dict[str, str]], *, timeout: float = 60, max_tokens: int = 256):
        cfg = _opts()
        base = cfg.get("ollama_base_url", "http://localhost:11434").rstrip("/")
        model = cfg.get("ollama_model") or "qwen2.5:7b"
        resp = requests.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {"num_predict": max_tokens},
            },
            timeout=timeout,
            stream=True,
        )
        resp.raise_for_status()
        import json

        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            token = (chunk.get("message") or {}).get("content") or ""
            if token:
                yield token


class GeminiProvider:
    name = "gemini"

    def complete(self, messages: list[dict[str, str]], *, timeout: float = 40, max_tokens: int = 256, **_k) -> LLMResponse:
        from core.secrets import decrypt_secret

        cfg = _opts()
        key = decrypt_secret(str(cfg.get("gemini_api_key") or ""))
        if not key:
            raise RuntimeError("Gemini API key not configured")
        model = cfg.get("gemini_model") or "gemini-2.0-flash-lite"
        import google.generativeai as genai

        genai.configure(api_key=key)
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        hist = [m for m in messages if m["role"] != "system"]
        user_parts = []
        for m in hist:
            if m["role"] == "user":
                user_parts.append(m["content"])
            elif m["role"] == "assistant":
                user_parts.append(f"Assistant: {m['content']}")
        prompt = (system + "\n\n" if system else "") + "\n".join(user_parts[-6:])
        t0 = time.time()
        gm = genai.GenerativeModel(model)
        resp = gm.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.4},
            request_options={"timeout": timeout},
        )
        text = (resp.text or "").strip()
        ms = int((time.time() - t0) * 1000)
        return LLMResponse(
            content=text,
            provider=self.name,
            model=model,
            input_tokens=estimate_tokens(prompt),
            output_tokens=estimate_tokens(text),
            latency_ms=ms,
        )


class OpenAIProvider:
    name = "openai"

    def complete(self, messages: list[dict[str, str]], *, timeout: float = 40, max_tokens: int = 256, **_k) -> LLMResponse:
        from core.secrets import decrypt_secret

        cfg = _opts()
        key = decrypt_secret(str(cfg.get("openai_api_key") or ""))
        if not key:
            raise RuntimeError("OpenAI API key not configured")
        model = cfg.get("openai_model") or "gpt-4o-mini"
        t0 = time.time()
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.4},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = (data["choices"][0]["message"]["content"] or "").strip()
        usage = data.get("usage") or {}
        ms = int((time.time() - t0) * 1000)
        return LLMResponse(
            content=text,
            provider=self.name,
            model=model,
            input_tokens=int(usage.get("prompt_tokens") or estimate_tokens(str(messages))),
            output_tokens=int(usage.get("completion_tokens") or estimate_tokens(text)),
            latency_ms=ms,
        )


class AnthropicProvider:
    name = "anthropic"

    def complete(self, messages: list[dict[str, str]], *, timeout: float = 40, max_tokens: int = 256, **_k) -> LLMResponse:
        from core.secrets import decrypt_secret

        cfg = _opts()
        key = decrypt_secret(str(cfg.get("anthropic_api_key") or ""))
        if not key:
            raise RuntimeError("Anthropic API key not configured")
        model = cfg.get("anthropic_model") or "claude-3-5-haiku-latest"
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        msgs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
        t0 = time.time()
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": msgs,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
        usage = data.get("usage") or {}
        ms = int((time.time() - t0) * 1000)
        return LLMResponse(
            content=text,
            provider=self.name,
            model=model,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or estimate_tokens(text)),
            latency_ms=ms,
        )


_PROVIDERS = {
    "ollama": OllamaProvider(),
    "gemini": GeminiProvider(),
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
}


def get_provider(name: str):
    return _PROVIDERS.get(name)
