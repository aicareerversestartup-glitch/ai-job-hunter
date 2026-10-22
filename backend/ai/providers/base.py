"""Vendor-neutral LLM interface. Business logic only ever talks to ``LLMProvider``."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMError(RuntimeError):
    pass


@dataclass
class AIConfig:
    provider: str = "none"  # none | openai | anthropic | gemini | ollama | openai_compatible
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.2
    max_tokens: int = 2500
    timeout_seconds: float = 90.0


class LLMProvider(ABC):
    name = "base"

    def __init__(self, config: AIConfig):
        self.config = config

    @property
    def available(self) -> bool:
        return True

    @abstractmethod
    def complete(self, system: str, prompt: str, *, temperature: float | None = None,
                 max_tokens: int | None = None, json_mode: bool = False) -> str:
        """Return the model's text reply."""

    def complete_json(self, system: str, prompt: str, **kwargs) -> dict:
        text = self.complete(system, prompt + "\n\nRespond with a single JSON object and nothing else.",
                             json_mode=True, **kwargs)
        return parse_json_reply(text)


def parse_json_reply(text: str) -> dict:
    """Parse JSON from a model reply, tolerating code fences and leading prose."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("Model did not return JSON")
        try:
            value = json.loads(cleaned[start: end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("Model returned JSON that is not an object")
    return value
