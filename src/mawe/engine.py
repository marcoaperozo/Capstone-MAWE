"""Engine facade: run the graph and persist everything it does.

The graph itself stays free of database code; this module subscribes to its
events and writes them through `RunRepository`.  That separation is what lets
`tests/` execute the whole pipeline against an in-memory database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import Settings, settings as default_settings
from .db import make_engine, session_scope
from .db.repository import RunRepository
from .graph.state import initial_state
from .graph.workflow import EngineContext, build_graph
from .llm import get_provider
from .llm.base import LLMProvider


@dataclass
class RunResult:
    run_id: Optional[int]
    status: str
    termination_reason: str
    iterations: int
    files: List[Dict[str, str]] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def approved(self) -> bool:
        return self.status == "approved"


class Engine:
    """One object that owns a provider, a database and the compiled graph."""

    def __init__(self, provider: Optional[LLMProvider] = None,
                 settings: Optional[Settings] = None,
                 database_url: Optional[str] = None):
        self.settings = settings or default_settings
        self.provider = provider or get_provider()
        self.db = make_engine(database_url or self.settings.database_url)

    def run(self, prompt: str, *, language: str = "python",
            max_iterations: Optional[int] = None,
            persist: bool = True,
            on_event=None) -> RunResult:
        cap = max_iterations or self.settings.max_iterations

        with session_scope(self.db) as session:
            repo = RunRepository(session)
            run_row = None
            if persist:
                project = repo.create_project(prompt, language=language)
                run_row = repo.start_run(project, max_iterations=cap)

            counter = CountingProvider(self.provider)
            recorder = _Recorder(repo, run_row, counter)

            def handle(kind: str, payload: dict) -> None:
                if persist:
                    recorder.handle(kind, payload)
                if on_event:
                    on_event(kind, payload)

            ctx = EngineContext(provider=counter, settings=self.settings,
                                on_event=handle)
            app = build_graph(ctx)
            state = initial_state(prompt, max_iterations=cap,
                                  language=language,
                                  run_id=run_row.id if run_row else None)
            final = app.invoke(state, {"recursion_limit": 4 * cap + 10})

            iterations = int(final.get("iteration", 0))
            status = final.get("status", "failed")
            reason = final.get("termination_reason", "error")

            if persist and run_row is not None:
                run_row.total_prompt_tokens = counter.prompt_tokens
                run_row.total_completion_tokens = counter.completion_tokens
                repo.finish_run(run_row, status, reason, iterations)
                repo.add_metric(run_row, "llm_calls", counter.call_count)
                repo.add_metric(run_row, "iterations", iterations)
                repo.add_metric(run_row, "tokens", run_row.total_tokens)
                repo.add_metric(run_row, "tests_passed",
                                final.get("tests_passed", 0))
                repo.add_metric(run_row, "tests_failed",
                                final.get("tests_failed", 0))

            return RunResult(
                run_id=run_row.id if run_row else None,
                status=status,
                termination_reason=reason,
                iterations=iterations,
                files=final.get("files", []),
                acceptance_criteria=final.get("acceptance_criteria", []),
                issues=final.get("issues", []),
                warnings=final.get("warnings", []),
                errors=final.get("errors", []),
                prompt_tokens=run_row.total_prompt_tokens if run_row else 0,
                completion_tokens=run_row.total_completion_tokens if run_row else 0,
            )


class CountingProvider:
    """Wraps a provider and totals the usage it reports.

    Token accounting has to be exact for the cost-per-successful-task figure
    in the Phase 4 evaluation, so it is measured at the one place every call
    passes through rather than estimated after the fact.
    """

    def __init__(self, inner: LLMProvider):
        self._inner = inner
        self.name = inner.name
        self.model = inner.model
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.call_count = 0

    def complete(self, system: str, user: str, **kwargs):
        response = self._inner.complete(system, user, **kwargs)
        self.prompt_tokens += response.prompt_tokens
        self.completion_tokens += response.completion_tokens
        self.call_count += 1
        return response

    def __getattr__(self, item):  # delegate anything else (e.g. mock helpers)
        return getattr(self._inner, item)


class _Recorder:
    """Turns graph events into database rows."""

    def __init__(self, repo: RunRepository, run_row, provider: LLMProvider):
        self.repo = repo
        self.run = run_row
        self.provider = provider
        self._last_total = 0

    def handle(self, kind: str, payload: Dict[str, Any]) -> None:
        if self.run is None:
            return

        if kind == "plan":
            spec = payload.get("spec")
            if spec:
                self.repo.add_specification(
                    self.run, spec,
                    "\n".join(payload.get("acceptance_criteria", [])))
                self.repo.add_message(self.run, 0, "product_manager", spec)

        elif kind == "develop":
            iteration = int(payload.get("iteration", 0))
            for f in payload.get("files", []):
                self.repo.add_code_artifact(
                    self.run, iteration, f["path"], f["content"],
                    language=f.get("language", "python"))
            if payload.get("files"):
                summary = ", ".join(f["path"] for f in payload["files"])
                self.repo.add_message(self.run, iteration, "developer",
                                      f"produced {summary}")

        elif kind == "review":
            iteration = self.run.code_artifacts[-1].iteration if \
                self.run.code_artifacts else 1
            feedback = "\n".join(payload.get("issues", [])) or "(no issues)"
            self.repo.add_review(
                self.run, iteration,
                payload.get("verdict", "reject"),
                payload.get("severity"),
                feedback,
                tests_passed=payload.get("tests_passed", 0),
                tests_failed=payload.get("tests_failed", 0))
            self.repo.add_message(self.run, iteration, "reviewer", feedback)
