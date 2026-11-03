"""The single-model baselines the engine is measured against.

Week 10.  Without these, Phase 4 can only report that the multi-agent engine
solves N of 20 tasks, which answers nothing: the research question is whether
*role separation* earns its cost, and that is a comparison or it is nothing.

Four conditions, as the proposal sets them out:

====  ====================  ===================================================
A     ``SingleModel``       one model, one call, no iteration and no review
B     ``SelfRefine``        one model that critiques and revises its own code
C     ``Engine``            the multi-agent engine (``engine.py``)
C'    ``Engine`` + setting  the engine with summarisation off (the ablation)
====  ====================  ===================================================

What each comparison can actually support:

* **C vs A** - does the whole apparatus beat a single shot?  This is the
  headline, and it conflates everything the engine does.
* **B vs A** - does *iterating at all* help?  B has no roles, no
  specification, no execution evidence.  Any gain here is iteration alone,
  which is what makes B the control that stops "multi-agent is better" from
  being a restatement of "more attempts are better".
* **C vs B** - does role separation beat self-criticism at equal iteration
  budget?  This is the closest thing to the actual hypothesis, and it is
  worth being precise about its limit: C differs from B in *two* ways, role
  separation and sandbox-grounded review, so a gain cannot be attributed to
  one of them by this design alone.  Giving B the sandbox would make it a
  different experiment - it would no longer isolate iteration - so the
  confound is stated rather than removed.

Fairness is the whole point, so everything the conditions share is shared
deliberately: the same provider instance, the same temperature, the same
iteration cap, the same file parser (``agents.developer.parse_files``, so a
model that returns a fenced code block instead of the JSON contract is treated
identically everywhere), the same token accounting at the single call site, and
the same hidden-test scoring, which never sees any of this.

What the baselines deliberately do **not** get is anything from the engine's
own machinery: no Product Manager specification, no executable acceptance
checks, no sandbox evidence, and no loop-prevention policy.  B stops when the
model declares itself finished or when the cap is reached - nothing else - so
the engine's loop prevention cannot flatter B's cost figures.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Protocol

from .agents.developer import DeveloperError, parse_files
from .agents.parsing import ParseError, as_str_list, extract_json
from .config import Settings, settings as default_settings
from .db import make_engine, session_scope
from .db.repository import RunRepository
from .engine import CountingProvider, RunResult
from .llm import get_provider
from .llm.base import LLMProvider

# --------------------------------------------------------------------- prompts
#: Condition A, and the writing step of condition B.  Deliberately the same
#: output contract as the Developer agent: the comparison is about the process
#: around the model, not about which condition guessed the response format.
SOLO = """You are an expert programmer working alone.

Write a complete, runnable program that satisfies the request. You have no
colleagues to check your work, so get it right in one pass.

Return ONLY a JSON object:
{
  "files": [
    {"path": "src/main.py", "language": "python", "content": "<full file>"}
  ]
}

Rules:
- "content" is the entire file, ready to run
- no placeholders, no "..." and no "rest of the code unchanged"
- put the program in src/main.py, or src/main.js for JavaScript
- handle the error cases the request describes, and use the exact output
  format it specifies
"""

SELF_CRITIQUE = """You are reviewing your own code before you ship it.

Read the original request and the program you wrote, and decide honestly
whether the program does everything the request asks for.

Return ONLY a JSON object:
{
  "done": true,
  "issues": ["concrete problem to fix", ...]
}

Rules:
- set "done" to true only when you believe the program is correct and complete
- when "done" is false, list specific defects, not style preferences
- each issue must name what is wrong and what the correct behaviour is
"""


def _request_block(prompt: str, language: str) -> str:
    return f"REQUEST ({language}):\n{prompt}\n"


def _render(files: List[Dict[str, str]]) -> str:
    return "\n\n".join(f"--- {f['path']} ---\n{f['content']}" for f in files)


# ------------------------------------------------------------------ the result
class Condition(Protocol):
    """What the experiment runner needs from any condition.

    A structural type, documenting the one method `bench.experiment` calls.
    It carried a `@dataclass` decorator for a while, which was meaningless on
    a Protocol and implied these were instantiable records rather than a
    shape that `Engine` and the baselines happen to share.
    """

    name: str

    def run(self, prompt: str, *, language: str = "python",
            max_iterations: Optional[int] = None,
            persist: bool = True) -> RunResult: ...


class _Baseline:
    """Shared plumbing: a provider, a database, exact token accounting."""

    name = "baseline"
    mode = "single_model"

    def __init__(self, provider: Optional[LLMProvider] = None,
                 settings: Optional[Settings] = None,
                 database_url: Optional[str] = None):
        self.settings = settings or default_settings
        self.provider = provider or get_provider()
        self.db = make_engine(database_url or self.settings.database_url)

    # -- helpers --------------------------------------------------------
    def _write(self, counter: CountingProvider, prompt: str, language: str,
               feedback: Optional[List[str]] = None,
               previous: Optional[List[Dict[str, str]]] = None) -> str:
        parts = [_request_block(prompt, language)]
        if previous:
            parts += ["YOUR CURRENT PROGRAM:", _render(previous), ""]
        if feedback:
            parts += ["PROBLEMS YOU FOUND IN IT:",
                      "\n".join(f"{i}. {issue}"
                                for i, issue in enumerate(feedback, 1)),
                      "",
                      "Return the corrected program in full."]
        else:
            parts.append("Return the program.")
        return counter.complete(SOLO, "\n".join(parts)).text

    @staticmethod
    def _parse(raw: str, language: str) -> List[Dict[str, str]]:
        return parse_files(raw, default_language=language)

    def _persist_start(self, repo: RunRepository, prompt: str, language: str,
                       cap: int, benchmark_task_id: Optional[int]):
        project = repo.create_project(prompt, language=language)
        run = repo.start_run(project, max_iterations=cap, mode=self.mode)
        if benchmark_task_id is not None:
            run.benchmark_task_id = benchmark_task_id
            repo.session.flush()
        return run

    def _persist_end(self, repo: RunRepository, run, counter, status, reason,
                     iterations, elapsed):
        run.total_prompt_tokens = counter.prompt_tokens
        run.total_completion_tokens = counter.completion_tokens
        repo.finish_run(run, status, reason, iterations)
        repo.add_metric(run, "llm_calls", counter.call_count)
        repo.add_metric(run, "iterations", iterations)
        repo.add_metric(run, "tokens", run.total_tokens)
        repo.add_metric(run, "latency_s", round(elapsed, 3))

    def _result(self, run, counter, status, reason, iterations, files,
                warnings, errors) -> RunResult:
        return RunResult(
            run_id=run.id if run is not None else None,
            status=status,
            termination_reason=reason,
            iterations=iterations,
            files=files,
            acceptance_criteria=[],   # no specification exists in a baseline
            issues=[],
            warnings=warnings,
            errors=errors,
            prompt_tokens=counter.prompt_tokens,
            completion_tokens=counter.completion_tokens,
        )


# ============================================================== condition A
class SingleModel(_Baseline):
    """Condition A: one model, one call, whatever comes back.

    `status` is "approved" when the call produced parseable files, because the
    schema has no "delivered, unreviewed" status and nothing in this condition
    reviews anything.  It is not a quality claim - A's quality is whatever the
    hidden tests say it is - and the comparison never reads this field.
    """

    name = "A: single model"
    mode = "single_model"

    def run(self, prompt: str, *, language: str = "python",
            max_iterations: Optional[int] = None,
            persist: bool = True,
            benchmark_task_id: Optional[int] = None) -> RunResult:
        started = time.time()
        with session_scope(self.db) as session:
            repo = RunRepository(session)
            run = self._persist_start(repo, prompt, language, 1,
                                      benchmark_task_id) if persist else None
            counter = CountingProvider(self.provider)

            files: List[Dict[str, str]] = []
            warnings: List[str] = []
            errors: List[str] = []
            try:
                raw = self._write(counter, prompt, language)
                files = self._parse(raw, language)
            except (DeveloperError, ParseError) as exc:
                errors.append(f"the model's output was unusable: {exc}")
            except Exception as exc:                 # provider failure
                errors.append(f"the provider failed: {exc}")

            status = "approved" if files else "failed"
            reason = "single_pass" if files else "error"

            if persist and run is not None:
                for f in files:
                    repo.add_code_artifact(run, 1, f["path"], f["content"],
                                           language=f.get("language", language))
                repo.add_message(run, 1, "developer",
                                 ", ".join(f["path"] for f in files)
                                 or "(nothing usable)")
                self._persist_end(repo, run, counter, status, reason, 1,
                                  time.time() - started)

            return self._result(run, counter, status, reason, 1, files,
                                warnings, errors)


# ============================================================== condition B
class SelfRefine(_Baseline):
    """Condition B: one model that criticises and revises its own code.

    The control for condition C.  It iterates, so any advantage C shows over
    it cannot be explained by "more attempts".  It has no roles, no
    specification and no execution evidence, so it also shows what iteration
    is worth when the critic is the author.

    Termination is only: the model says it is done, or the cap.  No
    no-progress, oscillation or repeated-issue detection - those are the
    engine's contribution and lending them to the baseline would understate
    the engine's cost advantage at the same time as overstating B's.
    """

    name = "B: self-refinement"
    mode = "self_refine"

    def run(self, prompt: str, *, language: str = "python",
            max_iterations: Optional[int] = None,
            persist: bool = True,
            benchmark_task_id: Optional[int] = None) -> RunResult:
        cap = max_iterations or self.settings.max_iterations
        started = time.time()

        with session_scope(self.db) as session:
            repo = RunRepository(session)
            run = self._persist_start(repo, prompt, language, cap,
                                      benchmark_task_id) if persist else None
            counter = CountingProvider(self.provider)

            files: List[Dict[str, str]] = []
            warnings: List[str] = []
            errors: List[str] = []
            iteration = 0
            reason = "iteration_cap"
            feedback: Optional[List[str]] = None

            while iteration < cap:
                iteration += 1
                try:
                    raw = self._write(counter, prompt, language, feedback,
                                      files or None)
                    candidate = self._parse(raw, language)
                except (DeveloperError, ParseError) as exc:
                    # keep the last good version rather than losing the run
                    warnings.append(f"iteration {iteration}: the model's "
                                    f"output was unusable ({exc})")
                    if not files:
                        errors.append(str(exc))
                        reason = "error"
                        break
                    reason = "error"
                    break
                except Exception as exc:
                    errors.append(f"the provider failed: {exc}")
                    reason = "error"
                    break

                files = candidate
                if persist and run is not None:
                    for f in files:
                        repo.add_code_artifact(
                            run, iteration, f["path"], f["content"],
                            language=f.get("language", language))
                    repo.add_message(run, iteration, "developer",
                                     ", ".join(f["path"] for f in files))

                done, issues, note = self._critique(counter, prompt, language,
                                                    files)
                if note:
                    warnings.append(f"iteration {iteration}: {note}")
                if persist and run is not None:
                    repo.add_review(
                        run, iteration,
                        "approve" if done else "reject",
                        None if done else "major",
                        "\n".join(issues) or "(no issues)",
                        tests_passed=0, tests_failed=0)
                    repo.add_message(run, iteration, "reviewer",
                                     "\n".join(issues) or "done")

                if done:
                    reason = "approved"
                    break
                feedback = issues or ["the program does not yet satisfy the "
                                      "request; find the defect and fix it"]

            status = ("approved" if reason == "approved"
                      else "failed" if reason == "error"
                      else "max_iterations")

            if persist and run is not None:
                self._persist_end(repo, run, counter, status, reason,
                                  iteration, time.time() - started)

            return self._result(run, counter, status, reason, iteration,
                                files, warnings, errors)

    # ------------------------------------------------------------------
    def _critique(self, counter: CountingProvider, prompt: str, language: str,
                  files: List[Dict[str, str]]):
        """Ask the model to judge its own work.

        A malformed critique is treated as "not done, no specific issues"
        rather than as success.  Reading an unparseable answer as approval
        would let a condition finish early by being incoherent, which would
        make B look cheap for the wrong reason.
        """
        user = "\n".join([_request_block(prompt, language),
                          "THE PROGRAM YOU WROTE:", _render(files), "",
                          "Return the review JSON."])
        raw = counter.complete(SELF_CRITIQUE, user).text
        try:
            data = extract_json(raw)
        except ParseError as exc:
            return False, [], f"self-critique was unparseable ({exc})"

        done = data.get("done")
        if isinstance(done, str):
            done = done.strip().lower() in ("true", "yes", "1")
        try:
            issues = as_str_list(data.get("issues"), "issues")
        except ParseError:
            issues = []

        if done and issues:
            # contradictory: it says finished and then lists defects.  Trust
            # the defects, which is the conservative reading.
            return False, issues, ("self-critique said done while listing "
                                   "issues; treated as not done")
        return bool(done), issues, None


# --------------------------------------------------------------------- lookup
BASELINES: Dict[str, Callable[..., _Baseline]] = {
    "single_model": SingleModel,
    "self_refine": SelfRefine,
}


def make_baseline(mode: str, **kwargs) -> _Baseline:
    try:
        return BASELINES[mode](**kwargs)
    except KeyError:
        raise KeyError(f"no baseline {mode!r}; "
                       f"known: {', '.join(sorted(BASELINES))}") from None
