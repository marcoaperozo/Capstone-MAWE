"""LLM provider registry."""

from __future__ import annotations

from typing import Optional

from .base import LLMProvider, LLMResponse, ProviderError, estimate_tokens
from .mock import MockProvider, picky_reviewer_script, stuck_developer_script

__all__ = [
    "LLMProvider", "LLMResponse", "ProviderError", "estimate_tokens",
    "MockProvider", "get_provider",
    "stuck_developer_script", "picky_reviewer_script",
]


def get_provider(name: Optional[str] = None, model: Optional[str] = None,
                 **kwargs) -> LLMProvider:
    """Construct a provider by name.

    The real providers are imported lazily so neither SDK is a hard dependency
    and the test suite never needs them installed.
    """
    from ..config import settings

    name = (name or settings.provider).lower()
    model = model or settings.model

    if name == "mock":
        return MockProvider(model=model if model != "mock-1" else "mock-1",
                            **kwargs)

    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model, **kwargs)

    if name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(model=model, **kwargs)

    raise ProviderError(
        f"Unknown provider {name!r}. Set MAWE_PROVIDER to mock, anthropic or openai."
    )
