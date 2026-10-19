"""OpenAI backend.  Optional dependency, same contract as the others."""

from __future__ import annotations

import os

from .base import LLMResponse, ProviderError

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ProviderError(
                "The openai package is not installed. Run: pip install openai"
            ) from exc

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and add it."
            )

        self.name = "openai"
        self.model = model if model and model != "mock-1" else DEFAULT_MODEL
        self._client = OpenAI(api_key=key)

    def complete(self, system: str, user: str, *, temperature: float = 0.2,
                 max_tokens: int = 4096) -> LLMResponse:
        completion = self._client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        usage = completion.usage
        return LLMResponse(
            text=completion.choices[0].message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=self.model,
            meta={"finish_reason": completion.choices[0].finish_reason},
        )
