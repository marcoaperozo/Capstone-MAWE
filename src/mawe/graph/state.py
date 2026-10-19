"""The state carried between graph nodes.

LangGraph merges the partial dict each node returns into this structure, so a
node only declares what it changes.  Keeping the state a plain TypedDict is
what makes the routing function pure and unit-testable without a model.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class GeneratedFile(TypedDict):
    path: str
    language: str
    content: str


class WorkflowState(TypedDict, total=False):
    # -- input -------------------------------------------------------------
    prompt: str
    language: str
    max_iterations: int
    run_id: Optional[int]

    # -- product manager ---------------------------------------------------
    spec: str
    spec_json: Dict[str, Any]
    acceptance_criteria: List[str]

    # -- developer ---------------------------------------------------------
    files: List[GeneratedFile]
    code_hash: str
    seen_hashes: List[str]
    iteration: int

    # -- reviewer ----------------------------------------------------------
    verdict: str
    severity: Optional[str]
    issues: List[str]
    tests_passed: int
    tests_failed: int

    # -- outcome -----------------------------------------------------------
    status: str
    termination_reason: str
    warnings: List[str]
    errors: List[str]


def initial_state(prompt: str, max_iterations: int = 5,
                  language: str = "python",
                  run_id: Optional[int] = None) -> WorkflowState:
    return WorkflowState(
        prompt=prompt,
        language=language,
        max_iterations=max_iterations,
        run_id=run_id,
        iteration=0,
        seen_hashes=[],
        files=[],
        acceptance_criteria=[],
        issues=[],
        warnings=[],
        errors=[],
        tests_passed=0,
        tests_failed=0,
    )
