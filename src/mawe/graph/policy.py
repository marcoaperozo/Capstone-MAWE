"""The loop-prevention policy, in one place.

Week 6.  Until now the routing decision and the termination reason were
computed by two separate functions that mirrored each other's logic - a shape
that works right up until someone edits one and not the other.  They are now
one `decide()` call returning both, so the two can never disagree.

The policy is a frozen dataclass with no I/O and no model access, which is
what lets the stress test in scripts/week6_loop_stress.py drive hundreds of
thousands of randomised review sequences through it in a second.

Termination reasons
    approved         the review passed, or only non-blocking issues remain
    no_progress      the Developer returned byte-identical code twice running
    oscillation      the Developer is cycling between versions it already tried
    repeated_issues  the same review complaints keep coming back unfixed
    iteration_cap    the hard ceiling was reached
    error            an agent failed; the run is finalized rather than hung
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

APPROVED = "approved"
ITERATION_CAP = "iteration_cap"
NO_PROGRESS = "no_progress"
OSCILLATION = "oscillation"
REPEATED_ISSUES = "repeated_issues"
ERROR = "error"

DEVELOP = "develop"
FINALIZE = "finalize"

#: every reason that means "we stopped without the Reviewer approving"
UNRESOLVED = (NO_PROGRESS, OSCILLATION, REPEATED_ISSUES, ITERATION_CAP, ERROR)

_WS = re.compile(r"\s+")


class Decision(NamedTuple):
    """Where the graph goes next, and why it stopped if it did."""

    route: str                    # DEVELOP or FINALIZE
    reason: Optional[str]         # None while the loop continues
    detail: str = ""              # human-readable note for the warnings report

    @property
    def terminal(self) -> bool:
        return self.route == FINALIZE


def issue_signature(issues: Sequence[str]) -> str:
    """A stable fingerprint of a set of review complaints.

    Normalised so that reordering, re-numbering or re-casing the same
    complaints does not read as progress.
    """
    normalised = sorted(
        _WS.sub(" ", re.sub(r"^\s*\d+[.)]\s*", "", i)).strip().lower()[:160]
        for i in issues if i and i.strip()
    )
    return "|".join(normalised)


@dataclass(frozen=True)
class LoopPolicy:
    """Every rule that can stop the review/fix cycle."""

    max_iterations: int = 5
    blocking_severities: Tuple[str, ...] = ("critical", "major")

    detect_no_progress: bool = True
    detect_oscillation: bool = True
    detect_repeated_issues: bool = True

    #: how many times the identical complaint set may recur before giving up
    repeated_issue_limit: int = 3

    # ------------------------------------------------------------------
    def decide(self, state: Dict[str, Any]) -> Decision:
        # an agent failure finalizes rather than hanging the graph
        if state.get("errors"):
            return Decision(FINALIZE, ERROR,
                            f"agent error: {state['errors'][0]}")

        verdict = state.get("verdict", "reject")
        severity = state.get("severity")

        if verdict == "approve":
            return Decision(FINALIZE, APPROVED, "approved by the reviewer")

        if severity not in self.blocking_severities:
            return Decision(
                FINALIZE, APPROVED,
                f"only non-blocking issues remain (severity {severity!r})")

        hashes: List[str] = list(state.get("seen_hashes", []))
        current = state.get("code_hash")

        if self.detect_no_progress and current and len(hashes) >= 2 \
                and hashes[-1] == current and hashes[-2] == current:
            return Decision(FINALIZE, NO_PROGRESS,
                            "the developer returned identical code twice")

        if self.detect_oscillation and current and hashes.count(current) > 1:
            return Decision(
                FINALIZE, OSCILLATION,
                "the developer is cycling between versions it already produced")

        if self.detect_repeated_issues:
            history: List[str] = list(state.get("issue_history", []))
            signature = history[-1] if history else ""
            if signature and history.count(signature) >= self.repeated_issue_limit:
                return Decision(
                    FINALIZE, REPEATED_ISSUES,
                    f"the same {len(signature.split('|'))} issue(s) were "
                    f"reported {history.count(signature)} times without a fix")

        if state.get("iteration", 0) >= self.max_iterations:
            return Decision(FINALIZE, ITERATION_CAP,
                            f"iteration cap of {self.max_iterations} reached")

        return Decision(DEVELOP, None, "")

    # ------------------------------------------------------------------
    @classmethod
    def from_settings(cls, settings) -> "LoopPolicy":
        return cls(
            max_iterations=getattr(settings, "max_iterations", 5),
            blocking_severities=tuple(
                getattr(settings, "blocking_severities", ("critical", "major"))),
        )


DEFAULT_POLICY = LoopPolicy()
