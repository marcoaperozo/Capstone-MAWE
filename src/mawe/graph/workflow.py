"""The LangGraph state graph and its routing rules.

    START -> plan -> develop -> review -> [approve           -> finalize]
                       ^                  [reject, retryable -> develop ]
                       |                  [reject, exhausted -> finalize]
                       └──────────────────┘

`route_after_review` is a pure function of the state, so every branch of the
loop-prevention logic is tested without calling a model
(see tests/test_loop_prevention.py).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, List, Optional

from langgraph.graph import END, START, StateGraph

from ..config import Settings, settings as default_settings
from ..llm.base import LLMProvider
from .state import WorkflowState, initial_state

# ---------------------------------------------------------------- constants

APPROVED = "approved"
ITERATION_CAP = "iteration_cap"
NO_PROGRESS = "no_progress"
ERROR = "error"


def hash_files(files: List[dict]) -> str:
    """Stable hash over all generated files, used for no-progress detection."""
    digest = hashlib.sha256()
    for f in sorted(files, key=lambda x: x["path"]):
        digest.update(f["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(f["content"].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


# ------------------------------------------------------------------ routing

def route_after_review(state: WorkflowState,
                       blocking: tuple = ("critical", "major")) -> str:
    """Return the next node: either 'develop' or 'finalize'.

    This is the whole of the loop-prevention policy, in one place.
    """
    # mechanism 4 (fallback): an agent error never hangs the graph
    if state.get("errors"):
        return "finalize"

    verdict = state.get("verdict", "reject")
    severity = state.get("severity")

    # approved outright
    if verdict == "approve":
        return "finalize"

    # mechanism 2: severity threshold - minor issues do not block
    if severity not in blocking:
        return "finalize"

    # mechanism 3: no-progress detection
    seen = state.get("seen_hashes", [])
    current = state.get("code_hash")
    if current and seen.count(current) > 1:
        return "finalize"

    # mechanism 1: hard iteration cap
    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return "finalize"

    return "develop"


def termination_reason(state: WorkflowState,
                       blocking: tuple = ("critical", "major")) -> str:
    """Why the loop stopped.  Mirrors route_after_review's decision order."""
    if state.get("errors"):
        return ERROR
    if state.get("verdict") == "approve":
        return APPROVED
    if state.get("severity") not in blocking:
        return APPROVED
    seen = state.get("seen_hashes", [])
    current = state.get("code_hash")
    if current and seen.count(current) > 1:
        return NO_PROGRESS
    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return ITERATION_CAP
    return ERROR


# -------------------------------------------------------------- graph build

@dataclass
class EngineContext:
    """Everything the nodes need, injected once at build time."""

    provider: LLMProvider
    settings: Settings
    on_event: Optional[Callable[[str, dict], None]] = None

    def emit(self, kind: str, payload: dict) -> None:
        if self.on_event:
            self.on_event(kind, payload)


def build_graph(ctx: EngineContext):
    """Compile the LangGraph state machine."""
    from ..agents.developer import DeveloperAgent
    from ..agents.product_manager import ProductManagerAgent
    from ..agents.reviewer import ReviewerAgent

    pm = ProductManagerAgent(ctx.provider, ctx.settings)
    dev = DeveloperAgent(ctx.provider, ctx.settings)
    reviewer = ReviewerAgent(ctx.provider, ctx.settings)

    def plan(state: WorkflowState) -> dict:
        update = pm.run(state)
        ctx.emit("plan", update)
        return update

    def develop(state: WorkflowState) -> dict:
        update = dev.run(state)
        ctx.emit("develop", update)
        return update

    def review(state: WorkflowState) -> dict:
        update = reviewer.run(state)
        ctx.emit("review", update)
        return update

    def finalize(state: WorkflowState) -> dict:
        reason = termination_reason(state, tuple(ctx.settings.blocking_severities))
        status = "approved" if reason == APPROVED else (
            "failed" if reason == ERROR else "max_iterations")
        warnings = list(state.get("warnings", []))
        if reason != APPROVED:
            warnings.append(
                f"finalized without approval ({reason}); returning the best "
                f"version produced after {state.get('iteration', 0)} iteration(s)")
        update = {"status": status, "termination_reason": reason,
                  "warnings": warnings}
        ctx.emit("finalize", update)
        return update

    graph = StateGraph(WorkflowState)
    graph.add_node("plan", plan)
    graph.add_node("develop", develop)
    graph.add_node("review", review)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "develop")
    graph.add_edge("develop", "review")
    graph.add_conditional_edges(
        "review",
        lambda s: route_after_review(s, tuple(ctx.settings.blocking_severities)),
        {"develop": "develop", "finalize": "finalize"},
    )
    graph.add_edge("finalize", END)

    # recursion_limit is LangGraph's own backstop; our own caps fire first.
    return graph.compile()


def run_workflow(prompt: str, provider: LLMProvider,
                 settings: Optional[Settings] = None,
                 max_iterations: Optional[int] = None,
                 language: str = "python",
                 run_id: Optional[int] = None,
                 on_event: Optional[Callable[[str, dict], None]] = None
                 ) -> WorkflowState:
    """Convenience wrapper: build the graph and execute one run."""
    cfg = settings or default_settings
    cap = max_iterations or cfg.max_iterations
    ctx = EngineContext(provider=provider, settings=cfg, on_event=on_event)
    app = build_graph(ctx)
    state = initial_state(prompt, max_iterations=cap, language=language,
                          run_id=run_id)
    # generous recursion limit: our iteration cap is the real bound
    return app.invoke(state, {"recursion_limit": 4 * cap + 10})
