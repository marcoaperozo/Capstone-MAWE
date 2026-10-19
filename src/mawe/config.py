"""Engine configuration.  Values come from the environment (.env) with the
defaults used in the proposal."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    # orchestration
    max_iterations: int = field(default_factory=lambda: _int("MAWE_MAX_ITERATIONS", 5))
    blocking_severities: tuple = ("critical", "major")

    # memory management (phase 3)
    context_token_budget: int = field(
        default_factory=lambda: _int("MAWE_CONTEXT_BUDGET", 12000))

    # sandbox
    sandbox_timeout_s: int = field(default_factory=lambda: _int("MAWE_SANDBOX_TIMEOUT", 10))

    # persistence
    database_url: str = field(
        default_factory=lambda: os.environ.get("MAWE_DATABASE_URL", "sqlite:///mawe.db"))

    # llm
    provider: str = field(default_factory=lambda: os.environ.get("MAWE_PROVIDER", "mock"))
    model: str = field(default_factory=lambda: os.environ.get("MAWE_MODEL", "mock-1"))
    temperature: float = 0.2


settings = Settings()
