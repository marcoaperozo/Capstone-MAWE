"""Week 2 integration: the graph runs end to end and persists the run.

Everything here uses the mock provider, so the suite is deterministic and free.
"""

import pytest

from mawe.config import Settings
from mawe.engine import Engine
from mawe.graph import run_workflow
from mawe.llm import MockProvider, picky_reviewer_script, stuck_developer_script


@pytest.fixture()
def settings():
    return Settings(max_iterations=5, sandbox_timeout_s=0)


# ----------------------------------------------------------- the happy path
def test_pipeline_reaches_approval(settings):
    state = run_workflow("Build a terminal snake game",
                         MockProvider(), settings=settings)
    assert state["status"] == "approved"
    assert state["termination_reason"] == "approved"
    assert state["iteration"] == 2          # reject once, then approve
    assert [f["path"] for f in state["files"]] == ["src/main.py"]
    assert len(state["acceptance_criteria"]) == 5


def test_every_agent_is_called(settings):
    provider = MockProvider()
    run_workflow("Build a terminal snake game", provider, settings=settings)
    assert provider.call_count("product_manager") == 1
    assert provider.call_count("developer") == 2
    assert provider.call_count("reviewer") == 2


# --------------------------------------------- the two non-approval exits
def test_stuck_developer_exits_on_no_progress(settings):
    state = run_workflow("Build a terminal snake game",
                         MockProvider(stuck_developer_script()),
                         settings=settings)
    assert state["termination_reason"] == "no_progress"
    assert state["status"] == "max_iterations"
    assert state["iteration"] == 2
    assert any("no_progress" in w for w in state["warnings"])


def test_picky_reviewer_stops_at_the_cap(settings):
    state = run_workflow("Build a terminal snake game",
                         MockProvider(picky_reviewer_script()),
                         settings=settings)
    assert state["termination_reason"] == "iteration_cap"
    assert state["iteration"] == settings.max_iterations


@pytest.mark.parametrize("cap", [1, 2, 3])
def test_cap_is_respected_exactly(cap):
    settings = Settings(max_iterations=cap, sandbox_timeout_s=0)
    state = run_workflow("Build a terminal snake game",
                         MockProvider(picky_reviewer_script()),
                         settings=settings)
    assert state["iteration"] == cap
    assert state["termination_reason"] == "iteration_cap"


def test_a_finalized_run_always_returns_the_best_code(settings):
    """Exiting without approval must still hand back something runnable."""
    state = run_workflow("Build a terminal snake game",
                         MockProvider(picky_reviewer_script()),
                         settings=settings)
    assert state["files"], "finalize_with_warnings must still return files"
    assert state["files"][0]["content"].strip()


# --------------------------------------------------------------- persistence
def test_run_is_persisted_and_queryable(settings):
    engine = Engine(provider=MockProvider(), settings=settings,
                    database_url="sqlite://")
    result = engine.run("Build a terminal snake game")

    assert result.run_id is not None
    assert result.approved
    assert result.total_tokens > 0

    from mawe.db import Run, session_scope
    with session_scope(engine.db) as session:
        run = session.get(Run, result.run_id)
        assert run.status == "approved"
        assert run.termination_reason == "approved"
        assert run.iteration_count == 2
        assert len(run.specifications) == 1
        assert len(run.code_artifacts) == 2      # one per iteration
        assert len(run.reviews) == 2
        assert run.messages, "every agent exchange is stored"
        metrics = {m.metric for m in run.evaluation_results}
        assert {"iterations", "tokens", "llm_calls"} <= metrics


def test_persisted_hashes_show_the_developer_changed_the_code(settings):
    engine = Engine(provider=MockProvider(), settings=settings,
                    database_url="sqlite://")
    result = engine.run("Build a terminal snake game")

    from mawe.db import Run, session_scope
    with session_scope(engine.db) as session:
        run = session.get(Run, result.run_id)
        hashes = [a.content_hash for a in run.code_artifacts]
    assert len(set(hashes)) == len(hashes), "each iteration produced new code"


def test_stuck_run_persists_identical_hashes(settings):
    engine = Engine(provider=MockProvider(stuck_developer_script()),
                    settings=settings, database_url="sqlite://")
    result = engine.run("Build a terminal snake game")
    assert result.termination_reason == "no_progress"

    from mawe.db import Run, session_scope
    with session_scope(engine.db) as session:
        run = session.get(Run, result.run_id)
        hashes = [a.content_hash for a in run.code_artifacts]
    assert len(hashes) == 2 and hashes[0] == hashes[1]
