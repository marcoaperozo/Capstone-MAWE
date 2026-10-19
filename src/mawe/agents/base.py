"""Shared agent behaviour: one model call, parsed into a state update."""

from __future__ import annotations

from typing import Any, Dict

from ..config import Settings
from ..llm.base import LLMProvider


class Agent:
    role: str = "agent"
    system_prompt: str = ""

    def __init__(self, provider: LLMProvider, settings: Settings):
        self.provider = provider
        self.settings = settings
        self.last_usage: Dict[str, int] = {"prompt_tokens": 0,
                                           "completion_tokens": 0}

    def ask(self, user_prompt: str) -> str:
        response = self.provider.complete(
            self.system_prompt, user_prompt,
            temperature=self.settings.temperature)
        self.last_usage = {"prompt_tokens": response.prompt_tokens,
                           "completion_tokens": response.completion_tokens}
        return response.text

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError
