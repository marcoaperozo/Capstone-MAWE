"""Scoring a candidate solution against a task's hidden tests.

Week 9.  This is the only thing in the project that decides whether a task was
solved, and it has no access to the Reviewer, the specification or anything the
model said.  It runs the program and compares bytes.

Two distinct numbers come out of a scoring run, and the proposal needs both:

* **pass rate** - the fraction of hidden tests that passed.  Partial credit.
* **task success** - every hidden test passed.  This is the binary that
  cost-per-success divides by, so it is deliberately unforgiving.

A program that fails to start at all - no entry point, syntax error, missing
interpreter - scores zero rather than raising.  That is the correct result: the
condition under test produced something that does not run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..agents.checks import stdout_matches
from ..sandbox.runner import Sandbox, interpreter_available
from .tasks import BenchTask, HiddenTest

#: a hidden test gets less time than an interactive review check; the tasks are
#: small and a slow one is usually an accidental infinite loop
DEFAULT_TIMEOUT_S = 10

#: An uncaught exception exits 1 in both Python and Node, which is the same
#: status a correct program uses to *report* a bad input.  Without this, every
#: error-path test in the suite would accept a crash, and mutation testing
#: showed that is not hypothetical: deleting an input guard left the tests
#: green because the resulting TypeError still exited 1.  Every task prompt
#: asks for "an error message to stderr", so a traceback is a failure to meet
#: the contract, not an unusual way of meeting it.
#: Code that does not even parse is the same hazard in a sharper form: a
#: Python SyntaxError prints no traceback and exits 1, so a file of prose
#: scored on fizzbuzz's three error-path tests before this pattern covered the
#: interpreter's "File ..., line N" header.
CRASH_SIGNATURES = re.compile(
    r"Traceback \(most recent call last\)"      # python runtime exception
    r"|^\s*File \".+\", line \d+"               # python syntax error header
    r"|^\s+at .+:\d+:\d+\)?\s*$"                # node stack frame
    r"|^\w*(?:Error|Exception):.*$\n^\s+at "    # node uncaught throw
    , re.MULTILINE)


@dataclass
class TestOutcome:
    test: HiddenTest
    passed: bool
    reason: str = ""
    timed_out: bool = False

    def line(self) -> str:
        mark = "PASS" if self.passed else "FAIL"
        text = f"[{mark}] {self.test.name}"
        if not self.passed:
            text += f"  -  {self.reason}"
        return text


@dataclass
class TaskScore:
    task: BenchTask
    outcomes: List[TestOutcome] = field(default_factory=list)
    skipped: Optional[str] = None

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def tests_passed(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def tests_failed(self) -> int:
        return self.total - self.tests_passed

    @property
    def pass_rate(self) -> float:
        """Partial credit, in [0, 1]."""
        return self.tests_passed / self.total if self.total else 0.0

    @property
    def success(self) -> bool:
        """The binary the cost-per-success metric divides by."""
        return self.total > 0 and self.tests_failed == 0

    @property
    def failed_names(self) -> List[str]:
        return [o.test.name for o in self.outcomes if not o.passed]

    def report(self) -> str:
        if self.skipped:
            return f"{self.task.slug}: skipped - {self.skipped}"
        head = (f"{self.task.slug} ({self.task.difficulty}, "
                f"{self.task.language}): {self.tests_passed}/{self.total}"
                f"{'  SUCCESS' if self.success else ''}")
        return "\n".join([head] + ["    " + o.line() for o in self.outcomes])

    def as_metrics(self) -> Dict[str, float]:
        return {
            "hidden_tests_total": float(self.total),
            "hidden_tests_passed": float(self.tests_passed),
            "pass_rate": round(self.pass_rate, 6),
            "task_success": 1.0 if self.success else 0.0,
        }


def _judge(test: HiddenTest, result: Dict[str, Any]) -> TestOutcome:
    stdout = result.get("stdout") or ""
    exit_code = result.get("exit_code")
    stderr = (result.get("stderr") or "")[:300].strip()

    if result.get("timed_out"):
        return TestOutcome(test, False, "timed out", timed_out=True)

    if test.expect_exit is not None and exit_code != test.expect_exit:
        reason = f"exit {exit_code}, expected {test.expect_exit}"
        if stderr:
            reason += f"; stderr: {stderr[:160]}"
        return TestOutcome(test, False, reason)

    if test.expect_exit not in (None, 0) and             CRASH_SIGNATURES.search(result.get("stderr") or ""):
        return TestOutcome(
            test, False,
            "crashed instead of reporting the error; the task asks for a "
            "message on stderr and this exited through an uncaught exception")

    if not stdout_matches(test.expect_stdout, stdout, test.match):
        return TestOutcome(
            test, False,
            f"stdout {stdout.strip()[:90]!r}, expected ({test.match}) "
            f"{(test.expect_stdout or '')[:90]!r}")

    return TestOutcome(test, True)


def score(files: Sequence[Dict[str, str]], task: BenchTask,
          timeout_s: int = DEFAULT_TIMEOUT_S,
          stop_on_first_failure: bool = False) -> TaskScore:
    """Run every hidden test for `task` against `files`.

    The project is materialised once and every test runs against that same
    directory, so a 12-test task costs one write instead of twelve.

    `stop_on_first_failure` is for mutation testing, where the only question
    is whether *any* test notices the mutation.  It makes the resulting
    `pass_rate` meaningless, so it is off by default and never used for
    scoring a condition.
    """
    if not interpreter_available(task.language):
        return TaskScore(task, [], skipped=f"no {task.language} interpreter")

    result = TaskScore(task, [])
    with Sandbox(list(files), language=task.language,
                 timeout_s=timeout_s) as box:
        for test in task.tests:
            if not box.usable:
                # the project does not run at all; every test fails for the
                # same reason, and we record that rather than pretending to
                # have executed them
                result.outcomes.append(
                    TestOutcome(test, False, box.setup_error or "unusable"))
                if stop_on_first_failure:
                    break
                continue
            outcome = _judge(test, box.run(argv=list(test.argv),
                                           stdin=test.stdin))
            result.outcomes.append(outcome)
            if stop_on_first_failure and not outcome.passed:
                break
    return result


@dataclass
class SuiteScore:
    """Scores for one condition across many tasks."""

    scores: List[TaskScore] = field(default_factory=list)

    @property
    def scored(self) -> List[TaskScore]:
        return [s for s in self.scores if s.skipped is None]

    @property
    def successes(self) -> int:
        return sum(1 for s in self.scored if s.success)

    @property
    def task_success_rate(self) -> float:
        return self.successes / len(self.scored) if self.scored else 0.0

    @property
    def mean_pass_rate(self) -> float:
        rows = self.scored
        return sum(s.pass_rate for s in rows) / len(rows) if rows else 0.0

    def by_difficulty(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for level in ("easy", "medium", "hard"):
            rows = [s for s in self.scored if s.task.difficulty == level]
            if not rows:
                continue
            out[level] = {
                "tasks": float(len(rows)),
                "successes": float(sum(1 for s in rows if s.success)),
                "mean_pass_rate": sum(s.pass_rate for s in rows) / len(rows),
            }
        return out


def score_all(solutions: Dict[str, Sequence[Dict[str, str]]],
              tasks: Sequence[BenchTask],
              timeout_s: int = DEFAULT_TIMEOUT_S) -> SuiteScore:
    """Score a mapping of task slug -> files against `tasks`."""
    suite = SuiteScore()
    for task in tasks:
        files = solutions.get(task.slug)
        if files is None:
            suite.scores.append(TaskScore(task, [], skipped="no solution"))
            continue
        suite.scores.append(score(files, task, timeout_s))
    return suite
