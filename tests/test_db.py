"""Week 1: the persistence layer records a traceable run."""

import pytest
from sqlalchemy import select

from mawe.db import Run, make_engine, session_scope, sha256
from mawe.db.repository import RunRepository


@pytest.fixture()
def engine():
    return make_engine("sqlite://")  # in-memory


def test_schema_creates_every_table(engine):
    expected = {
        "users", "projects", "agents", "benchmark_tasks", "runs", "messages",
        "specifications", "code_artifacts", "reviews", "memory_summaries",
        "evaluation_results",
    }
    from mawe.db import Base
    assert expected <= set(Base.metadata.tables)


def test_full_run_is_traceable(engine):
    with session_scope(engine) as s:
        repo = RunRepository(s)
        project = repo.create_project("Build a snake game")
        run = repo.start_run(project, max_iterations=5)

        repo.add_message(run, 0, "product_manager", "spec text", 10, 40)
        repo.add_specification(run, "spec text", "1) runs 2) scores")
        repo.add_code_artifact(run, 1, "src/main.py", "print('hi')")
        repo.add_review(run, 1, "reject", "major", "criterion 2 fails")
        repo.add_code_artifact(run, 2, "src/main.py", "print('hello')")
        repo.add_review(run, 2, "approve", "minor", "all criteria pass")
        repo.finish_run(run, "approved", "approved", iterations=2)
        run_id = run.id

    with session_scope(engine) as s:
        run = s.get(Run, run_id)
        assert run.status == "approved"
        assert run.termination_reason == "approved"
        assert run.iteration_count == 2
        assert run.total_tokens == 50
        assert len(run.code_artifacts) == 2
        assert len(run.reviews) == 2
        # the whole history is reachable from the run, which is the point
        assert run.specifications[0].acceptance_criteria.startswith("1)")


def test_content_hash_detects_identical_code(engine):
    with session_scope(engine) as s:
        repo = RunRepository(s)
        run = repo.start_run(None, max_iterations=5)
        a = repo.add_code_artifact(run, 1, "src/main.py", "same")
        b = repo.add_code_artifact(run, 2, "src/main.py", "same")
        c = repo.add_code_artifact(run, 3, "src/main.py", "different")

    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash
    assert a.content_hash == sha256("same")


def test_token_totals_accumulate_across_messages(engine):
    with session_scope(engine) as s:
        repo = RunRepository(s)
        run = repo.start_run(None, max_iterations=5)
        repo.add_message(run, 0, "product_manager", "a", 100, 200)
        repo.add_message(run, 1, "developer", "b", 300, 400)
        assert run.total_prompt_tokens == 400
        assert run.total_completion_tokens == 600
        assert run.total_tokens == 1000
