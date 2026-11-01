"""Code Reviewer agent.

Week 5 deliverable, and the point at which the pipeline becomes a real QA
gate rather than one model grading another.

The review is produced in three steps:

1. **Evidence.** Every executable acceptance check from the specification is
   run in the sandbox.  This is objective: the program either produced the
   expected output or it did not.
2. **Judgement.** The model is shown the code, the criteria and the execution
   evidence, and reports on the criteria that cannot be checked mechanically.
3. **Reconciliation.** Where the two disagree, evidence wins.  A model cannot
   approve code that demonstrably failed a check, and it cannot reject code
   over formatting once every check passes.

Step 3 is what stops the two failure modes the proposal calls out: false
approval, and rejection loops over trivia.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Agent
from ..graph.policy import issue_signature
from .checks import parse_checks, run_checks, summarise
from .parsing import ParseError, as_str_list, extract_json
from .prompts import REVIEWER

VALID_VERDICTS = ("approve", "reject")
VALID_SEVERITIES = ("critical", "major", "minor")

SEVERITY_RANK = {"minor": 0, "major": 1, "critical": 2}


def normalise_severity(value: Any, verdict: str) -> Optional[str]:
    """Coerce whatever the model said into one of the three levels.

    A reject with no severity becomes `major`: treating it as minor would
    silently approve broken code, and inventing `critical` would escalate
    every ambiguous review, so `major` is the value that keeps the loop
    running but bounded.
    """
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in VALID_SEVERITIES:
            return lowered
        if lowered in ("blocker", "fatal", "severe"):
            return "critical"
        if lowered in ("moderate", "medium", "normal"):
            return "major"
        if lowered in ("trivial", "nit", "low", "style", "none"):
            return "minor"
    return "major" if verdict == "reject" else "minor"


def max_severity(*values: Optional[str]) -> Optional[str]:
    present = [v for v in values if v in SEVERITY_RANK]
    if not present:
        return None
    return max(present, key=lambda v: SEVERITY_RANK[v])


class ReviewerAgent(Agent):
    role = "reviewer"
    system_prompt = REVIEWER

    def build_prompt(self, state: Dict[str, Any],
                     evidence: Optional[Dict[str, Any]] = None,
                     execution: Optional[Dict[str, Any]] = None) -> str:
        files = state.get("files") or []
        rendered = "\n\n".join(
            f"--- {f['path']} ---\n{f['content']}" for f in files)

        parts = ["SPECIFICATION:", state.get("spec", ""), "",
                 "ACCEPTANCE CRITERIA:",
                 "\n".join(f"{i}. {c}" for i, c in
                           enumerate(state.get("acceptance_criteria", []), 1)),
                 "", "CODE UNDER REVIEW:", rendered]

        if evidence and evidence.get("evidence"):
            parts += [
                "",
                "SANDBOX EXECUTION EVIDENCE (objective - these checks were run):",
                evidence["evidence"],
                "",
                f"{evidence['tests_passed']} check(s) passed, "
                f"{evidence['tests_failed']} failed.",
            ]
            if evidence["failed_criteria"]:
                parts.append(
                    "Criteria proven to fail: "
                    + ", ".join(str(c) for c in evidence["failed_criteria"])
                    + ". You must reject, and you must cite these.")
            else:
                parts.append(
                    "Every executable check passed. Reject only if you can "
                    "identify an acceptance criterion that is genuinely unmet; "
                    "style preferences are 'minor' and do not block.")
        elif execution is not None:
            parts += ["", "SANDBOX RUN (no executable checks were supplied):",
                      f"exit code: {execution.get('exit_code')}",
                      f"timed out: {execution.get('timed_out')}",
                      f"stdout:\n{(execution.get('stdout') or '')[:1500]}",
                      f"stderr:\n{(execution.get('stderr') or '')[:1500]}"]

        parts += ["", "Return the review JSON."]
        return "\n".join(parts)

    # ------------------------------------------------------------------
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        files = state.get("files") or []
        language = state.get("language", "python")
        timeout = self.settings.sandbox_timeout_s

        evidence: Optional[Dict[str, Any]] = None
        execution: Optional[Dict[str, Any]] = None
        warnings = list(state.get("warnings", []))

        checks = self._checks_for(state)
        if checks and files and timeout > 0:
            try:
                results = run_checks(files, checks, language, timeout)
                evidence = summarise(results)
            except Exception as exc:        # a broken sandbox must not hang the run
                warnings.append(f"acceptance checks could not run: {exc}")
        elif files and timeout > 0:
            execution = self._smoke_run(state)

        raw = self.ask(self.build_prompt(state, evidence, execution))

        try:
            data = extract_json(raw)
        except ParseError as exc:
            update = self._fallback_review(evidence, exc)
            update["issue_history"] = list(state.get("issue_history", [])) + [
                issue_signature(update.get("issues", []))]
            update["warnings"] = warnings + [
                "reviewer returned malformed output; the verdict came from "
                "the execution evidence instead"]
            return update

        verdict = str(data.get("verdict", "reject")).strip().lower()
        if verdict not in VALID_VERDICTS:
            verdict = "reject"
        issues = as_str_list(data.get("issues"), "issues")
        severity = normalise_severity(data.get("severity"), verdict)

        tests_passed = self._as_int(data.get("tests_passed"))
        tests_failed = self._as_int(data.get("tests_failed"))

        # ---- reconciliation: measured evidence overrides the model ----
        if evidence is not None:
            tests_passed = evidence["tests_passed"]
            tests_failed = evidence["tests_failed"]

            if evidence["tests_failed"] > 0:
                failed = ", ".join(str(c) for c in evidence["failed_criteria"])
                measured_severity = "critical" if evidence["crashed"] or \
                    evidence["any_timeout"] else "major"
                if verdict == "approve":
                    warnings.append(
                        f"reviewer approved code that failed "
                        f"{evidence['tests_failed']} executable check(s); "
                        f"overridden by the sandbox result")
                    issues = issues or []
                verdict = "reject"
                severity = max_severity(severity, measured_severity)
                evidence_issue = (
                    f"criteria {failed} fail when the program is run. "
                    f"Sandbox evidence:\n{evidence['evidence']}")
                if not any("Sandbox evidence" in i for i in issues):
                    issues = [evidence_issue] + issues
            elif verdict == "reject" and severity in ("critical", "major"):
                # every measurable criterion passed, so a blocking reject has
                # to be justified by something the checks could not cover
                warnings.append(
                    "all executable checks passed; the reviewer's blocking "
                    "reject was downgraded to minor")
                severity = "minor"

        update: Dict[str, Any] = {
            "verdict": verdict,
            "severity": severity,
            "issues": issues,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "warnings": warnings,
            # fingerprint of this review's complaints, so the loop policy can
            # notice the same objections coming back unfixed
            "issue_history": list(state.get("issue_history", []))
                             + [issue_signature(issues)],
        }
        if evidence is not None:
            update["check_evidence"] = evidence["evidence"]
        return update

    # ------------------------------------------------------------------
    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _checks_for(state: Dict[str, Any]):
        spec_json = state.get("spec_json") or {}
        try:
            return parse_checks(spec_json.get("checks"))
        except ParseError:
            return []

    def _fallback_review(self, evidence: Optional[Dict[str, Any]],
                         exc: Exception) -> Dict[str, Any]:
        """The model's answer was unusable; fall back to the measurements."""
        if evidence is not None:
            failing = evidence["tests_failed"] > 0
            return {
                "verdict": "reject" if failing else "approve",
                "severity": ("critical" if evidence["crashed"] else "major") \
                    if failing else "minor",
                "issues": ([f"criteria "
                            f"{', '.join(str(c) for c in evidence['failed_criteria'])} "
                            f"fail when the program is run"] if failing else []),
                "tests_passed": evidence["tests_passed"],
                "tests_failed": evidence["tests_failed"],
            }
        return {
            "verdict": "reject",
            "severity": "major",
            "issues": [f"reviewer output could not be parsed: {exc}"],
            "tests_passed": 0,
            "tests_failed": 0,
        }

    def _smoke_run(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            from ..sandbox.runner import run_files
            return run_files(state.get("files") or [],
                             language=state.get("language", "python"),
                             timeout_s=self.settings.sandbox_timeout_s)
        except Exception as exc:
            return {"exit_code": None, "timed_out": False, "stdout": "",
                    "stderr": f"sandbox unavailable: {exc}"}
