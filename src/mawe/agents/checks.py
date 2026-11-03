"""Executable acceptance checks.

Week 5.  An acceptance criterion written in English can be *claimed* to pass by
a language model that never ran anything.  To stop that, the Product Manager
also emits machine-runnable checks: an invocation and the output it must
produce.  The Reviewer executes them in the sandbox and the result is evidence
the model cannot argue with.

A check is deliberately simple - argv, stdin, expected stdout, expected exit
code - because the generated programs are small command-line tools.  Criteria
that cannot be expressed this way are still judged by the model, but they are
judged *alongside* the execution evidence rather than instead of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..sandbox.runner import run_files
from .parsing import ParseError


@dataclass
class AcceptanceCheck:
    """One runnable assertion about the generated program."""

    criterion: int                      # 1-based index into acceptance_criteria
    argv: List[str] = field(default_factory=list)
    stdin: str = ""
    expect_stdout: Optional[str] = None   # substring or exact, see `match`
    match: str = "exact"                  # exact | contains | regex
    expect_exit: Optional[int] = 0

    def describe(self) -> str:
        call = " ".join(self.argv) if self.argv else "(no arguments)"
        if self.stdin:
            call += f"  <stdin: {self.stdin[:40]!r}>"
        return call


@dataclass
class CheckResult:
    check: AcceptanceCheck
    passed: bool
    actual_stdout: str = ""
    actual_exit: Optional[int] = None
    timed_out: bool = False
    stderr: str = ""
    reason: str = ""

    def as_evidence(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        line = (f"[{verdict}] criterion {self.check.criterion}: "
                f"{self.check.describe()}")
        if not self.passed:
            line += f"\n        {self.reason}"
        return line


def parse_checks(raw: Any) -> List[AcceptanceCheck]:
    """Parse the optional `checks` array of a specification."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ParseError(f"checks should be a list, got {type(raw).__name__}")

    checks: List[AcceptanceCheck] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ParseError(f"checks[{i}] is not an object")
        try:
            criterion = int(item.get("criterion", 0))
        except (TypeError, ValueError) as exc:
            raise ParseError(
                f"checks[{i}].criterion must be an integer") from exc
        argv = item.get("argv") or []
        if isinstance(argv, str):
            argv = [argv]
        if not isinstance(argv, list):
            raise ParseError(f"checks[{i}].argv must be a list")

        match = str(item.get("match", "exact")).lower()
        if match not in ("exact", "contains", "regex"):
            match = "exact"

        expect_exit = item.get("expect_exit", 0)
        if expect_exit is not None:
            try:
                expect_exit = int(expect_exit)
            except (TypeError, ValueError):
                expect_exit = 0

        expect_stdout = item.get("expect_stdout")
        checks.append(AcceptanceCheck(
            criterion=criterion,
            argv=[str(a) for a in argv],
            stdin=str(item.get("stdin") or ""),
            expect_stdout=None if expect_stdout is None else str(expect_stdout),
            match=match,
            expect_exit=expect_exit,
        ))
    return checks


def stdout_matches(expected: Optional[str], actual: str,
                   match: str = "exact") -> bool:
    """Compare captured stdout against an expectation.

    One definition, used by both the Reviewer's acceptance checks and the
    Phase 4 benchmark harness.  Two copies of this would be two copies that
    drift, and a benchmark that grades slightly differently from the engine's
    own checks would quietly invalidate the comparison.

    Both sides are stripped, so a missing or extra trailing newline is not a
    failure; differences *inside* the output still are.
    """
    if expected is None:
        return True
    want = expected.strip()
    got = actual.strip()
    if match == "contains":
        return want in got
    if match == "regex":
        try:
            return re.search(want, got, re.MULTILINE) is not None
        except re.error:
            return False
    return got == want


def _stdout_matches(check: AcceptanceCheck, actual: str) -> bool:
    return stdout_matches(check.expect_stdout, actual, check.match)


def run_check(files: List[Dict[str, str]], check: AcceptanceCheck,
              language: str = "python", timeout_s: int = 10) -> CheckResult:
    result = run_files(files, language=language, timeout_s=timeout_s,
                       argv=check.argv, stdin=check.stdin)

    stdout = result.get("stdout", "") or ""
    exit_code = result.get("exit_code")
    timed_out = bool(result.get("timed_out"))
    stderr = (result.get("stderr", "") or "")[:600]

    if timed_out:
        return CheckResult(check, False, stdout, exit_code, True, stderr,
                           reason=f"timed out after {timeout_s}s")

    if check.expect_exit is not None and exit_code != check.expect_exit:
        return CheckResult(
            check, False, stdout, exit_code, False, stderr,
            reason=(f"exit code was {exit_code}, expected {check.expect_exit}"
                    + (f"; stderr: {stderr.strip()[:200]}" if stderr.strip() else "")))

    if not _stdout_matches(check, stdout):
        return CheckResult(
            check, False, stdout, exit_code, False, stderr,
            reason=(f"stdout was {stdout.strip()[:120]!r}, expected "
                    f"({check.match}) {check.expect_stdout!r}"))

    return CheckResult(check, True, stdout, exit_code, False, stderr)


def run_checks(files: List[Dict[str, str]], checks: List[AcceptanceCheck],
               language: str = "python", timeout_s: int = 10
               ) -> List[CheckResult]:
    return [run_check(files, c, language, timeout_s) for c in checks]


def summarise(results: List[CheckResult]) -> Dict[str, Any]:
    """Counts plus the criterion numbers that failed."""
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    return {
        "tests_passed": len(passed),
        "tests_failed": len(failed),
        "failed_criteria": sorted({r.check.criterion for r in failed}),
        "any_timeout": any(r.timed_out for r in results),
        "crashed": any(r.actual_exit not in (0, None) and not r.passed
                       for r in results),
        "evidence": "\n".join(r.as_evidence() for r in results),
    }
