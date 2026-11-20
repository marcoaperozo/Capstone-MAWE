"""Anthropic backend.

Not imported unless MAWE_PROVIDER=anthropic, so `anthropic` stays an optional
dependency and CI never needs a key.
"""

from __future__ import annotations

import os

from .base import LLMResponse, ProviderError

#: Claude Sonnet 5.5 - the current Sonnet, same price as Claude Sonnet 5
#: ($2/$10 per million tokens) and the tier this project budgeted for.
#: Override with MAWE_MODEL.
DEFAULT_MODEL = "claude-sonnet-5-5"


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
        # A Phase 4 sweep is ~240 runs and several hundred calls, so a single
        # rate-limit response or transient 5xx would otherwise abandon the
        # sweep partway and waste everything spent up to that point. The SDK
        # retries 408/409/429/5xx and connection errors with exponential
        # backoff; the default of 2 is raised because a long sweep is exactly
        # the case where the limiter has time to clear. The long timeout is
        # for the same reason: a slow response is cheaper to wait for than to
        # re-request.
        self._client = anthropic.Anthropic(api_key=key, max_retries=8,
                                           timeout=600.0)

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
