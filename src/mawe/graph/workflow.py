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
from .policy import (
    APPROVED,
    ERROR,
    # re-exported: `graph/__init__` and tests/test_loop_prevention.py import
    # these from here, so they are part of this module's surface even though
    # nothing below uses them
    ITERATION_CAP,  # noqa: F401
    NO_PROGRESS,  # noqa: F401
    LoopPolicy,
)
from .state import WorkflowState, initial_state


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

def _policy(blocking) -> LoopPolicy:
    if isinstance(blocking, LoopPolicy):
        return blocking
    return LoopPolicy(blocking_severities=tuple(blocking))


def route_after_review(state: WorkflowState,
                       blocking=("critical", "major")) -> str:
    """Next node: 'develop' or 'finalize'.

    Kept as a free function because it is the single most-tested piece of the
    engine; it now delegates to LoopPolicy so the route and the reason cannot
    drift apart.
    """
    policy = _policy(blocking)
    if isinstance(blocking, LoopPolicy):
        policy = blocking
    else:
        policy = LoopPolicy(max_iterations=state.get("max_iterations", 5),
                            blocking_severities=tuple(blocking))
    return policy.decide(state).route


def termination_reason(state: WorkflowState,
                       blocking=("critical", "major")) -> str:
    """Why the loop stopped. Returns ERROR if called mid-loop."""
    if isinstance(blocking, LoopPolicy):
        policy = blocking
    else:
        policy = LoopPolicy(max_iterations=state.get("max_iterations", 5),
                            blocking_severities=tuple(blocking))
    decision = policy.decide(state)
    return decision.reason or ERROR


# -------------------------------------------------------------- graph build

@dataclass
class EngineContext:
    """Everything the nodes need, injected once at build time."""

    provider: LLMProvider
    settings: Settings
    on_event: Optional[Callable[[str, dict], None]] = None
    policy: Optional[LoopPolicy] = None

    def __post_init__(self):
        if self.policy is None:
            self.policy = LoopPolicy.from_settings(self.settings)

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
        from ..memory import MemoryManager

        update = reviewer.run(state)
        # the completed iteration is only fully known once the review lands:
        # the files came from develop, the verdict from here
        record = MemoryManager.record_from_state({**state, **update})
        update["history"] = list(state.get("history", [])) + [record]
        # The review event carries the iteration it belongs to. Subscribers
        # used to infer it from the run's code artifacts, which was wrong:
        # the repository sets `run_id` directly rather than appending to the
        # relationship, so an already-loaded collection is stale and every
        # review after the first was filed against iteration 1. The number
        # is known here, so it is sent rather than guessed. It is attached to
        # a copy because `update` is the graph's state delta, and putting
        # `iteration` in it would overwrite the counter the Developer owns.
        ctx.emit("review", {**update, "iteration": state.get("iteration", 0)})
        return update

    def finalize(state: WorkflowState) -> dict:
        decision = ctx.policy.decide(state)
        reason = decision.reason or ERROR
        status = "approved" if reason == APPROVED else (
            "failed" if reason == ERROR else "max_iterations")
        warnings = list(state.get("warnings", []))
        if reason != APPROVED:
            warnings.append(
                f"finalized without approval ({reason}): {decision.detail}. "
                f"Returning the best of {state.get('iteration', 0)} "
                f"iteration(s).")
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
        lambda s: ctx.policy.decide(s).route,
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
