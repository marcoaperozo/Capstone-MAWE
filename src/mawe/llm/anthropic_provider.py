"""Anthropic backend.

Not imported unless MAWE_PROVIDER=anthropic, so `anthropic` stays an optional
dependency and CI never needs a key.
"""

from __future__ import annotations

import os

from .base import LLMResponse, ProviderError

DEFAULT_MODEL = "claude-sonnet-5"


class AnthropicProvider:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ProviderError(
                "The anthropic package is not installed. Run: pip install anthropic"
            ) from exc

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add it."
            )

        self.name = "anthropic"
        self.model = model if model and model != "mock-1" else DEFAULT_MODEL
        self._client = anthropic.Anthropic(api_key=key)

    def complete(self, system: str, user: str, *, temperature: float = 0.2,
                 max_tokens: int = 4096) -> LLMResponse:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in message.content
                       if getattr(block, "type", None) == "text")
        return LLMResponse(
            text=text,
            prompt_tokens=message.usage.input_tokens,
            completion_tokens=message.usage.output_tokens,
            model=self.model,
            meta={"stop_reason": message.stop_reason},
        )
