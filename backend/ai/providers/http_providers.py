"""HTTP implementations for the supported LLM vendors.

All share one retrying HTTP helper. Model names come from configuration only.
"""
from __future__ import annotations

import time

from backend.ai.providers.base import AIConfig, LLMError, LLMProvider

RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504, 529}


def _post(url: str, *, headers: dict, payload: dict, timeout: float, attempts: int = 3) -> dict:
    import httpx

    last_error = ""
    for attempt in range(attempts):
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            last_error = str(exc)
        else:
            if response.status_code < 300:
                return response.json()
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code not in RETRY_STATUSES:
                break
        time.sleep(1.5 * (2 ** attempt))
    raise LLMError(f"LLM request failed: {last_error}")


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI, Ollama, LM Studio, Groq, Together, OpenRouter, Azure-style gateways…"""
    name = "openai_compatible"
    default_base_url = "https://api.openai.com/v1"

    @property
    def available(self) -> bool:
        return bool(self.config.model) and (bool(self.config.api_key) or self.name == "ollama"
                                            or bool(self.config.base_url))

    def complete(self, system, prompt, *, temperature=None, max_tokens=None, json_mode=False) -> str:
        base = (self.config.base_url or self.default_base_url).rstrip("/")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post(f"{base}/chat/completions", headers=headers, payload=payload, timeout=self.config.timeout_seconds)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected response shape: {str(data)[:200]}") from exc


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"


class OllamaProvider(OpenAICompatibleProvider):
    name = "ollama"
    default_base_url = "http://localhost:11434/v1"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    @property
    def available(self) -> bool:
        return bool(self.config.api_key and self.config.model)

    def complete(self, system, prompt, *, temperature=None, max_tokens=None, json_mode=False) -> str:
        base = (self.config.base_url or "https://api.anthropic.com").rstrip("/")
        headers = {"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        payload = {
            "model": self.config.model, "system": system,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": self.config.temperature if temperature is None else temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        data = _post(f"{base}/v1/messages", headers=headers, payload=payload, timeout=self.config.timeout_seconds)
        parts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
        if not parts:
            raise LLMError(f"Unexpected response shape: {str(data)[:200]}")
        return "".join(parts)


class GeminiProvider(LLMProvider):
    name = "gemini"

    @property
    def available(self) -> bool:
        return bool(self.config.api_key and self.config.model)

    def complete(self, system, prompt, *, temperature=None, max_tokens=None, json_mode=False) -> str:
        base = (self.config.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        payload: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.config.temperature if temperature is None else temperature,
                                 "maxOutputTokens": max_tokens or self.config.max_tokens},
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.config.api_key}
        data = _post(f"{base}/models/{self.config.model}:generateContent", headers=headers, payload=payload,
                     timeout=self.config.timeout_seconds)
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected response shape: {str(data)[:200]}") from exc


class NoAIProvider(LLMProvider):
    """Used when no AI is configured. Everything still works through deterministic fallbacks."""
    name = "none"

    @property
    def available(self) -> bool:
        return False

    def complete(self, system, prompt, **kwargs) -> str:
        raise LLMError("No AI provider is configured. Add one in Settings to enable AI rewriting.")


PROVIDERS: dict[str, type[LLMProvider]] = {
    "none": NoAIProvider, "openai": OpenAIProvider, "openai_compatible": OpenAICompatibleProvider,
    "ollama": OllamaProvider, "anthropic": AnthropicProvider, "gemini": GeminiProvider,
}


def get_provider(config: AIConfig) -> LLMProvider:
    cls = PROVIDERS.get((config.provider or "none").lower())
    if cls is None:
        raise LLMError(f"Unknown AI provider {config.provider!r}. Options: {', '.join(PROVIDERS)}")
    return cls(config)
