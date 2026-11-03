"""Running a condition over the benchmark and recording what happened.

Week 10.  The point of this module is uniformity: the four conditions differ
enormously inside, and the comparison is only meaningful if everything
*outside* them is identical.  So one function runs a condition on a task, and
every condition goes through it - same prompt, same cap, same scoring, same
columns.

Each row is one (condition, task, repetition).  Nothing here aggregates or
tests for significance; that is Week 11's job, and keeping collection separate
from analysis means a sweep can be re-analysed without being re-run.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from ..config import Settings
from .harness import DEFAULT_TIMEOUT_S, TaskScore, score
from .tasks import TASKS, BenchTask

#: Condition labels, in the order the proposal presents them.
CONDITIONS = ("A", "B", "C", "C'")

CONDITION_NAMES = {
    "A": "single model",
    "B": "self-refinement",
    "C": "multi-agent engine",
    "C'": "engine, no summarisation",
}


@dataclass
class RunRow:
    """One run of one condition on one task: everything the report needs."""

    condition: str
    task: str
    difficulty: str
    language: str
    repetition: int

    # outcome, as the condition itself reported it
    status: str = ""
    termination_reason: str = ""
    iterations: int = 0

    # outcome, as the hidden tests measured it
    hidden_tests_total: int = 0
    hidden_tests_passed: int = 0
    pass_rate: float = 0.0
    success: bool = False
    skipped: Optional[str] = None

    # cost
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0

    run_id: Optional[int] = None
    error: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def as_dict(self) -> Dict[str, Any]:
        row = dataclasses.asdict(self)
        row["total_tokens"] = self.total_tokens
        return row


# ----------------------------------------------------------------- cost model
@dataclass(frozen=True)
class Pricing:
    """Dollars per million tokens.

    Cost is computed from the measured token counts rather than estimated, and
    the rates are an input to the report rather than a constant buried in the
    code, because they change and the thesis has to say which ones it used.
    """

    prompt_per_mtok: float = 0.0
    completion_per_mtok: float = 0.0
    label: str = "free (mock provider)"

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.prompt_per_mtok
                + completion_tokens * self.completion_per_mtok) / 1_000_000


FREE = Pricing()


# ------------------------------------------------------------------ one run
def _accepts(function: Any, parameter: str) -> bool:
    """Does `function` take a keyword argument of this name?

    True for anything with `**kwargs`, since that will accept it.
    """
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):          # builtins, C functions
        return False
    for name, item in signature.parameters.items():
        if item.kind is inspect.Parameter.VAR_KEYWORD:
            return True
        if name == parameter:
            return True
    return False


def run_one(condition: str, runner: Any, task: BenchTask, repetition: int = 1,
            *, max_iterations: Optional[int] = None,
            pricing: Pricing = FREE,
            timeout_s: int = DEFAULT_TIMEOUT_S,
            benchmark_task_id: Optional[int] = None) -> RunRow:
    """Run `runner` on `task` and score whatever it produced.

    `runner` is an `Engine` or a baseline: anything with a `.run(prompt, ...)`
    returning a `RunResult`.  A condition that raises is recorded as a failed
    row rather than aborting the sweep - losing 239 rows because one run threw
    would be the worst possible outcome of a long experiment.
    """
    row = RunRow(condition=condition, task=task.slug,
                 difficulty=task.difficulty, language=task.language,
                 repetition=repetition)

    kwargs: Dict[str, Any] = {"language": task.language}
    if max_iterations is not None:
        kwargs["max_iterations"] = max_iterations
    # Only the baselines take `benchmark_task_id`; the Engine does not.
    # This used to be discovered by calling and catching TypeError, which was
    # wrong in a way that would have been very hard to see: a genuine
    # TypeError raised *inside* a condition's own code looked identical to
    # "this runner has a different signature", so the sweep silently retried
    # and, if the retry happened to work, recorded a clean row for a run that
    # had hit a real bug. Asking the signature is deterministic and swallows
    # nothing.
    if benchmark_task_id is not None and _accepts(runner.run,
                                                  "benchmark_task_id"):
        kwargs["benchmark_task_id"] = benchmark_task_id

    started = time.time()
    try:
        result = runner.run(task.prompt, **kwargs)
    except Exception as exc:
        row.error = f"{type(exc).__name__}: {exc}"
        row.latency_s = round(time.time() - started, 3)
        return row

    row.latency_s = round(time.time() - started, 3)
    row.status = result.status
    row.termination_reason = result.termination_reason
    row.iterations = result.iterations
    row.prompt_tokens = result.prompt_tokens
    row.completion_tokens = result.completion_tokens
    row.run_id = result.run_id
    row.cost_usd = pricing.cost(result.prompt_tokens, result.completion_tokens)

    measured: TaskScore = score(result.files, task, timeout_s=timeout_s)
    row.skipped = measured.skipped
    row.hidden_tests_total = measured.total
    row.hidden_tests_passed = measured.tests_passed
    row.pass_rate = round(measured.pass_rate, 6)
    row.success = measured.success
    return row


# ------------------------------------------------------------------ a sweep
def run_condition(condition: str, runner_factory: Callable[[], Any],
                  tasks: Sequence[BenchTask] = TASKS,
                  repetitions: int = 1, *,
                  max_iterations: Optional[int] = None,
                  pricing: Pricing = FREE,
                  timeout_s: int = DEFAULT_TIMEOUT_S,
                  task_ids: Optional[Dict[str, int]] = None,
                  on_row: Optional[Callable[[RunRow], None]] = None
                  ) -> List[RunRow]:
    """Run one condition over every task, `repetitions` times.

    `runner_factory` is called once per run rather than once per sweep: a
    condition must start each task with no memory of the last one, and sharing
    one engine across tasks would quietly let a provider fixture's call
    counter leak between them.
    """
    rows: List[RunRow] = []
    for repetition in range(1, repetitions + 1):
        for task in tasks:
            row = run_one(condition, runner_factory(), task, repetition,
                          max_iterations=max_iterations, pricing=pricing,
                          timeout_s=timeout_s,
                          benchmark_task_id=(task_ids or {}).get(task.slug))
            rows.append(row)
            if on_row:
                on_row(row)
    return rows


# ------------------------------------------------------------------- storage
def to_json(rows: Iterable[RunRow], path, metadata: Optional[Dict] = None):
    """Write a sweep to disk so the analysis can be re-run without the API.

    The metadata block records what produced the numbers - provider, model,
    temperature, caps, pricing.  A results file that does not say which model
    it came from cannot be defended in a write-up.
    """
    payload = {
        "metadata": metadata or {},
        "rows": [r.as_dict() for r in rows],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return path


def from_json(path) -> List[RunRow]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    fields = {f.name for f in dataclasses.fields(RunRow)}
    return [RunRow(**{k: v for k, v in row.items() if k in fields})
            for row in payload["rows"]]


def to_csv(rows: Sequence[RunRow], path):
    import csv

    if not rows:
        open(path, "w", encoding="utf-8").close()
        return path
    header = list(rows[0].as_dict())
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())
    return path


def metadata_for(settings: Settings, provider: Any, pricing: Pricing,
                 repetitions: int) -> Dict[str, Any]:
    return {
        "provider": getattr(provider, "name", "?"),
        "model": getattr(provider, "model", "?"),
        "temperature": settings.temperature,
        "max_iterations": settings.max_iterations,
        "sandbox_timeout_s": settings.sandbox_timeout_s,
        "context_token_budget": settings.context_token_budget,
        "repetitions": repetitions,
        "pricing": dataclasses.asdict(pricing),
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
