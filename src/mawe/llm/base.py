"""Provider-agnostic LLM interface.

Every agent talks to this, never to a vendor SDK, so the same pipeline runs
against a scripted mock in CI and against a real API in Phase 4 without the
graph or the agents changing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    """One completion plus the accounting the evaluation needs."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMProvider(Protocol):
    """The whole contract.  Keeping it this small is what makes the mock
    honest: it implements exactly what a real provider implements."""

    name: str
    model: str

    def complete(self, system: str, user: str, *,
                 temperature: float = 0.2,
                 max_tokens: int = 4096) -> LLMResponse:
        ...


def estimate_tokens(text: str) -> int:
    """Rough tokenizer stand-in: ~4 characters per token.

    Only used by the mock and as a fallback when a provider does not report
    usage.  Real providers report exact counts, which is what gets persisted.
    """
    return max(1, len(text) // 4)


class ProviderError(RuntimeError):
    """Raised when a provider cannot be constructed or a call fails."""
