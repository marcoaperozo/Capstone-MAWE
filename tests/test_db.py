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


# ------------------------------------------------------ schema compatibility
def test_incompatible_existing_database_fails_fast(tmp_path):
    """create_all() silently skips a table that already exists, so an
    incompatible file would otherwise blow up at the first INSERT with an
    opaque SQL error. This happened for real: the standalone demo in scripts/
    keeps a simpler `runs` table, and pointing both at the default mawe.db
    produced 'table runs has no column named project_id'."""
    import sqlite3

    from mawe.db import SchemaMismatchError, make_engine

    path = tmp_path / "foreign.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, prompt TEXT)")
    con.commit()
    con.close()

    with pytest.raises(SchemaMismatchError) as exc:
        make_engine(f"sqlite:///{path}")

    message = str(exc.value)
    assert "runs" in message
    assert "project_id" in message
    assert "--db" in message, "the error should say how to recover"


def test_compatible_existing_database_is_reused(tmp_path):
    """Reopening a database this schema created must keep working."""
    from mawe.db import make_engine

    url = f"sqlite:///{tmp_path / 'reuse.db'}"
    first = make_engine(url)
    with session_scope(first) as s:
        RunRepository(s).start_run(None, max_iterations=5)

    second = make_engine(url)          # must not raise
    with session_scope(second) as s:
        assert s.query(Run).count() == 1


def test_demo_script_uses_its_own_database_file():
    """Regression guard for the collision above."""
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "scripts" / "m1_demo.py"
    text = source.read_text(encoding="utf-8")
    match = re.search(r'^DB_PATH\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "m1_demo.py should declare DB_PATH"
    assert match.group(1) != "mawe.db", (
        "the standalone demo must not share the engine's default database")
