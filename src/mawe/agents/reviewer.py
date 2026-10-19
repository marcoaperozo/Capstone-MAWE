"""Code Reviewer agent.

Week 5 deliverable; the Week 2-4 version parses the review contract and
normalises severity so routing is reliable.  Running the generated code in the
sandbox before judging is wired in `mawe.sandbox` and enabled when
`settings.sandbox_timeout_s > 0`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Agent
from .parsing import ParseError, as_str_list, extract_json
from .prompts import REVIEWER

VALID_VERDICTS = ("approve", "reject")
VALID_SEVERITIES = ("critical", "major", "minor")


def normalise_severity(value: Any, verdict: str) -> Optional[str]:
    """Coerce whatever the model said into one of the three levels.

    A reject with no severity is treated as `major`: failing closed here would
    silently approve broken code, and failing open would loop forever, so we
    pick the value that keeps the loop running but bounded.
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


class ReviewerAgent(Agent):
    role = "reviewer"
    system_prompt = REVIEWER

    def build_prompt(self, state: Dict[str, Any],
                     execution: Optional[Dict[str, Any]] = None) -> str:
        files = state.get("files") or []
        rendered = "\n\n".join(
            f"--- {f['path']} ---\n{f['content']}" for f in files)
        parts = ["SPECIFICATION:", state.get("spec", ""), "",
                 "ACCEPTANCE CRITERIA:",
                 "\n".join(f"{i}. {c}" for i, c in
                           enumerate(state.get("acceptance_criteria", []), 1)),
                 "", "CODE UNDER REVIEW:", rendered]
        if execution:
            parts += ["", "SANDBOX EXECUTION RESULT:",
                      f"exit code: {execution.get('exit_code')}",
                      f"timed out: {execution.get('timed_out')}",
                      f"stdout:\n{execution.get('stdout', '')[:2000]}",
                      f"stderr:\n{execution.get('stderr', '')[:2000]}"]
        parts += ["", "Return the review JSON."]
        return "\n".join(parts)

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        execution = self._maybe_execute(state)
        raw = self.ask(self.build_prompt(state, execution))

        try:
            data = extract_json(raw)
        except ParseError as exc:
            # an unparseable review must not hang the loop
            return {
                "verdict": "reject",
                "severity": "major",
                "issues": [f"reviewer output could not be parsed: {exc}"],
                "tests_passed": 0,
                "tests_failed": 0,
                "warnings": list(state.get("warnings", [])) + [
                    "reviewer returned malformed output; treated as a major reject"],
            }

        verdict = str(data.get("verdict", "reject")).strip().lower()
        if verdict not in VALID_VERDICTS:
            verdict = "reject"

        issues: List[str] = as_str_list(data.get("issues"), "issues")
        severity = normalise_severity(data.get("severity"), verdict)

        update: Dict[str, Any] = {
            "verdict": verdict,
            "severity": severity,
            "issues": issues,
            "tests_passed": int(data.get("tests_passed") or 0),
            "tests_failed": int(data.get("tests_failed") or 0),
        }
        if execution is not None:
            update["warnings"] = list(state.get("warnings", []))
            if execution.get("timed_out"):
                update["warnings"].append(
                    f"sandbox execution timed out after "
                    f"{self.settings.sandbox_timeout_s}s")
        return update

    def _maybe_execute(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.settings.sandbox_timeout_s <= 0:
            return None
        files = state.get("files") or []
        if not files:
            return None
        try:
            from ..sandbox.runner import run_files
            return run_files(files, language=state.get("language", "python"),
                             timeout_s=self.settings.sandbox_timeout_s)
        except Exception as exc:  # sandbox problems must not kill the run
            return {"exit_code": None, "timed_out": False, "stdout": "",
                    "stderr": f"sandbox unavailable: {exc}"}
