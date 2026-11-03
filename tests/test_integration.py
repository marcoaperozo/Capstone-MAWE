"""Week 8: end-to-end integration against the mocked LLM, plus the web API.

These tests exercise the whole stack - graph, agents, sandbox, memory,
persistence and HTTP - rather than any one layer. They are what "stable
engine v1.0" means in practice: the pieces built in Weeks 1 to 7 still work
together.
"""


import pytest

from mawe.config import Settings
from mawe.db import Run, session_scope
from mawe.engine import Engine
from mawe.llm import (
    MockProvider,
    oscillating_developer_script,
    picky_reviewer_script,
    stuck_developer_script,
    varied_reviewer_script,
)
from mawe.sample_code import TEMPERATURE_SPEC, temperature_repair_script


def engine_for(script, **kw):
    settings = Settings(max_iterations=kw.pop("max_iterations", 5),
                        sandbox_timeout_s=kw.pop("sandbox_timeout_s", 0))
    for key, value in kw.items():
        setattr(settings, key, value)
    return Engine(provider=MockProvider(script), settings=settings,
                  database_url="sqlite://")


# ============================================= the whole pipeline, end to end
def test_a_complete_run_produces_runnable_reviewed_code():
    engine = engine_for(temperature_repair_script(), sandbox_timeout_s=15)
    result = engine.run("Build a command-line temperature converter")

    assert result.approved
    assert result.iterations == 2
    assert [f["path"] for f in result.files] == ["src/main.py"]
    assert result.total_tokens > 0

    # and the delivered code genuinely satisfies the spec
    from mawe.agents.checks import parse_checks, run_checks, summarise
    summary = summarise(run_checks(result.files,
                                   parse_checks(TEMPERATURE_SPEC["checks"])))
    assert summary["tests_failed"] == 0


def test_every_layer_leaves_a_trace_in_the_database():
    engine = engine_for(temperature_repair_script(), sandbox_timeout_s=15)
    result = engine.run("Build a command-line temperature converter")

    with session_scope(engine.db) as session:
        run = session.get(Run, result.run_id)
        assert run.status == "approved"
        assert run.project.prompt.startswith("Build a command-line")
        assert len(run.specifications) == 1
        assert len(run.code_artifacts) == 2          # one per iteration
        assert len(run.reviews) == 2
        assert run.messages
        assert run.total_tokens > 0
        metrics = {m.metric for m in run.evaluation_results}
        assert {"iterations", "tokens", "llm_calls"} <= metrics
        # the two code versions really are different
        hashes = [a.content_hash for a in run.code_artifacts]
        assert len(set(hashes)) == 2


@pytest.mark.parametrize("script,expected", [
    (temperature_repair_script(), "approved"),
    (stuck_developer_script(), "no_progress"),
    (picky_reviewer_script(), "repeated_issues"),
    (oscillating_developer_script(), "oscillation"),
    (varied_reviewer_script(), "iteration_cap"),
])
def test_every_termination_path_survives_the_full_stack(script, expected):
    """Each exit must work through the real engine, not just the policy."""
    engine = engine_for(script, sandbox_timeout_s=0)
    result = engine.run("build something")
    assert result.termination_reason == expected
    assert result.run_id is not None

    with session_scope(engine.db) as session:
        run = session.get(Run, result.run_id)
        assert run.termination_reason == expected
        assert run.finished_at is not None


def test_a_run_that_fails_still_returns_the_best_code():
    engine = engine_for(varied_reviewer_script(), sandbox_timeout_s=0)
    result = engine.run("build something")
    assert not result.approved
    assert result.files, "finalize_with_warnings must still deliver something"
    assert result.warnings


def test_two_runs_share_a_database_without_interfering():
    engine = engine_for(temperature_repair_script(), sandbox_timeout_s=0)
    first = engine.run("first idea")
    second = engine.run("second idea")

    assert first.run_id != second.run_id
    with session_scope(engine.db) as session:
        assert session.query(Run).count() == 2
        assert session.get(Run, first.run_id).project.prompt == "first idea"
        assert session.get(Run, second.run_id).project.prompt == "second idea"


def test_memory_compression_is_active_in_a_real_run():
    engine = engine_for(varied_reviewer_script(12), max_iterations=8,
                        sandbox_timeout_s=0)
    result = engine.run("build something")

    with session_scope(engine.db) as session:
        run = session.get(Run, result.run_id)
        summaries = run.memory_summaries
    assert summaries
    compressed = [s for s in summaries if s.tokens_after < s.tokens_before]
    assert compressed, "later iterations should have been compressed"


# ============================================================== the CLI
def test_cli_runs_end_to_end(tmp_path, capsys):
    from mawe.cli import main

    db = tmp_path / "cli.db"
    code = main(["Build a terminal snake game", "--no-sandbox",
                 "--db", f"sqlite:///{db}", "--provider", "mock"])
    out = capsys.readouterr().out

    assert code == 0
    assert "status             : approved" in out
    assert "run id" in out
    assert db.exists()


def test_cli_writes_the_generated_files(tmp_path, capsys):
    from mawe.cli import main

    out_dir = tmp_path / "generated"
    main(["Build a terminal snake game", "--no-sandbox",
          "--db", f"sqlite:///{tmp_path / 'c.db'}", "--out", str(out_dir)])

    produced = list(out_dir.rglob("*.py"))
    assert produced, "the --out directory should contain the generated source"
    assert produced[0].read_text(encoding="utf-8").strip()


def test_cli_reports_an_unusable_provider_cleanly(capsys, monkeypatch):
    from mawe.cli import main

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    code = main(["build something", "--provider", "anthropic"])
    assert code == 2
    assert "error:" in capsys.readouterr().err


# ============================================================== the web API
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MAWE_DATABASE_URL", f"sqlite:///{tmp_path / 'web.db'}")
    monkeypatch.setenv("MAWE_PROVIDER", "mock")
    monkeypatch.setenv("MAWE_SANDBOX_TIMEOUT", "0")

    import importlib

    from fastapi.testclient import TestClient

    from mawe.web import app as app_module
    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_health_endpoint(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"


def test_index_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Multi-Agent AI Workflow Engine" in response.text


def test_api_creates_and_lists_a_run(client):
    created = client.post("/api/runs",
                          json={"prompt": "Build a terminal snake game",
                                "language": "python"})
    assert created.status_code == 200
    body = created.json()
    assert body["status"] in ("approved", "max_iterations")
    assert body["files"]
    assert body["acceptance_criteria"]

    listed = client.get("/api/runs").json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]
    assert listed[0]["prompt"] == "Build a terminal snake game"


def test_api_exposes_the_full_history_of_a_run(client):
    run_id = client.post("/api/runs",
                         json={"prompt": "Build a snake game"}).json()["id"]
    detail = client.get(f"/api/runs/{run_id}").json()

    assert detail["id"] == run_id
    assert detail["specification"]
    assert detail["code_artifacts"]
    assert detail["reviews"]
    assert detail["code_artifacts"][0]["content"].strip()


def test_api_rejects_a_bad_request(client):
    assert client.post("/api/runs", json={"prompt": "x"}).status_code == 422
    assert client.post("/api/runs", json={"prompt": "build a thing",
                                          "language": "cobol"}).status_code == 422


def test_api_404s_on_an_unknown_run(client):
    assert client.get("/api/runs/4242").status_code == 404


def test_api_respects_the_iteration_cap(client):
    body = client.post("/api/runs", json={"prompt": "Build a snake game",
                                          "max_iterations": 1}).json()
    assert body["iterations"] <= 1
