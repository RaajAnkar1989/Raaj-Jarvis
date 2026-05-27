"""Unified LLM response format."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    fallback: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMMessage:
    role: str
    content: str
