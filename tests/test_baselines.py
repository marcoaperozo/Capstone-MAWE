"""Week 10: the single-model baselines and the comparison machinery.

The baselines are the control for the whole project's claim, so what matters
here is less that they work than that they are *fair* and that they are not
secretly the engine. Several tests exist only to catch that: the baselines
must not acquire a specification, executable checks, sandbox evidence or the
engine's loop prevention, because every one of those would make the comparison
flatter the engine.
"""

import json

import pytest

from mawe.baselines import SelfRefine, SingleModel, make_baseline
from mawe.bench import get, select
from mawe.bench.experiment import (
    CONDITION_NAMES,
    Pricing,
    RunRow,
    from_json,
    metadata_for,
    run_condition,
    run_one,
    to_csv,
    to_json,
)
from mawe.bench.oracle import OracleProvider, defective_variants, identify
from mawe.config import Settings
from mawe.db import Run, session_scope
from mawe.engine import Engine
from mawe.llm import (
    MockProvider,
    never_satisfied_script,
    self_refine_script,
    solo_script,
)

FAST = dict(max_iterations=5, sandbox_timeout_s=0)


def settings(**kw):
    return Settings(**{**FAST, **kw})


def baseline(cls, script, **kw):
    return cls(provider=MockProvider(script), settings=settings(**kw),
               database_url="sqlite://")


# ======================================================= condition A
def test_single_model_makes_exactly_one_call():
    provider = MockProvider(solo_script())
    runner = SingleModel(provider=provider, settings=settings(),
                         database_url="sqlite://")
    result = runner.run("Build a terminal snake game")

    assert result.iterations == 1
    assert result.termination_reason == "single_pass"
    assert provider.call_count() == 1, "A must not iterate"
    assert provider.call_count("solo") == 1
    assert result.files


def test_single_model_never_uses_the_engine_roles():
    """If A ever consulted a Product Manager or Reviewer it would not be A."""
    provider = MockProvider(solo_script())
    SingleModel(provider=provider, settings=settings(),
                database_url="sqlite://").run("build a thing")
    assert provider.call_count("product_manager") == 0
    assert provider.call_count("reviewer") == 0
    assert provider.call_count("developer") == 0


def test_single_model_has_no_specification():
    result = baseline(SingleModel, solo_script()).run("build a thing")
    assert result.acceptance_criteria == []


def test_single_model_reports_unusable_output_without_raising():
    runner = baseline(SingleModel, {"solo": ["I would rather not"]})
    result = runner.run("build a thing")
    assert result.status == "failed"
    assert result.termination_reason == "error"
    assert result.errors
    assert result.files == []


def test_single_model_persists_its_run_as_a_baseline():
    runner = baseline(SingleModel, solo_script())
    result = runner.run("build a thing")
    with session_scope(runner.db) as session:
        run = session.get(Run, result.run_id)
        assert run.mode == "single_model"
        assert run.iteration_count == 1
        assert len(run.code_artifacts) == 1
        assert run.total_tokens > 0
        assert {"tokens", "iterations", "llm_calls", "latency_s"} <= \
            {m.metric for m in run.evaluation_results}


def test_a_baseline_can_run_without_persisting():
    runner = baseline(SingleModel, solo_script())
    result = runner.run("build a thing", persist=False)
    assert result.run_id is None
    assert result.files


# ======================================================= condition B
def test_self_refine_iterates_until_it_is_satisfied():
    provider = MockProvider(self_refine_script(approve_at=2))
    runner = SelfRefine(provider=provider, settings=settings(),
                        database_url="sqlite://")
    result = runner.run("Build a terminal snake game")

    assert result.iterations == 2
    assert result.termination_reason == "approved"
    assert provider.call_count("solo") == 2
    assert provider.call_count("self_critic") == 2


def test_self_refine_stops_at_the_cap_when_never_satisfied():
    runner = baseline(SelfRefine, never_satisfied_script(), max_iterations=3)
    result = runner.run("build a thing")
    assert result.iterations == 3
    assert result.termination_reason == "iteration_cap"
    assert result.status == "max_iterations"
    assert result.files, "the best attempt is still delivered"


def test_self_refine_does_not_inherit_the_engines_loop_prevention():
    """B must burn its whole budget on a model that never settles.

    Lending it no-progress or repeated-issue detection would cut its token
    count and understate what the engine's loop policy is worth.
    """
    identical = {"solo": [json.dumps({"files": [{
        "path": "src/main.py", "language": "python",
        "content": "print('same every time')\n"}]})],
        "self_critic": [json.dumps({"done": False, "issues": ["same issue"]})]}
    runner = baseline(SelfRefine, identical, max_iterations=4)
    result = runner.run("build a thing")
    assert result.iterations == 4
    assert result.termination_reason == "iteration_cap"


def test_self_refine_never_uses_the_engine_roles():
    provider = MockProvider(self_refine_script())
    SelfRefine(provider=provider, settings=settings(),
               database_url="sqlite://").run("build a thing")
    assert provider.call_count("product_manager") == 0
    assert provider.call_count("reviewer") == 0


def test_self_refine_treats_an_unparseable_critique_as_not_done():
    """Incoherence must not be an early exit."""
    script = {"solo": [json.dumps({"files": [{"path": "src/main.py",
                                              "language": "python",
                                              "content": "print(1)\n"}]})],
              "self_critic": ["no idea honestly"]}
    runner = baseline(SelfRefine, script, max_iterations=2)
    result = runner.run("build a thing")
    assert result.termination_reason == "iteration_cap"
    assert any("unparseable" in w for w in result.warnings)


def test_self_refine_distrusts_a_contradictory_critique():
    """"done" plus a list of defects is read as not done."""
    script = {"solo": [json.dumps({"files": [{"path": "src/main.py",
                                              "language": "python",
                                              "content": "print(1)\n"}]})],
              "self_critic": [json.dumps({"done": True,
                                          "issues": ["it crashes"]})]}
    runner = baseline(SelfRefine, script, max_iterations=2)
    result = runner.run("build a thing")
    assert result.termination_reason == "iteration_cap"
    assert any("treated as not done" in w for w in result.warnings)


def test_self_refine_accepts_a_string_done_flag():
    script = {"solo": [json.dumps({"files": [{"path": "src/main.py",
                                              "language": "python",
                                              "content": "print(1)\n"}]})],
              "self_critic": [json.dumps({"done": "true", "issues": []})]}
    result = baseline(SelfRefine, script).run("build a thing")
    assert result.termination_reason == "approved"


def test_self_refine_records_every_version_and_review():
    runner = baseline(SelfRefine, never_satisfied_script(), max_iterations=3)
    result = runner.run("build a thing")
    with session_scope(runner.db) as session:
        run = session.get(Run, result.run_id)
        assert run.mode == "self_refine"
        assert len(run.code_artifacts) == 3
        assert len(run.reviews) == 3
        assert all(r.tests_passed == 0 for r in run.reviews), \
            "B has no executable checks; its reviews cite no test results"


def test_the_registry_builds_both_baselines():
    assert isinstance(make_baseline("single_model", settings=settings(),
                                    provider=MockProvider(solo_script()),
                                    database_url="sqlite://"), SingleModel)
    assert isinstance(make_baseline("self_refine", settings=settings(),
                                    provider=MockProvider(self_refine_script()),
                                    database_url="sqlite://"), SelfRefine)
    with pytest.raises(KeyError, match="self_refine"):
        make_baseline("telepathy")


# ======================================================= the oracle fixture
def test_the_oracle_identifies_a_task_from_a_baseline_prompt():
    task = get("fizzbuzz")
    assert identify(task.prompt) is task
    assert identify("something else entirely") is None


def test_the_oracle_identifies_a_task_from_a_specification():
    from mawe.bench.oracle import specification_for

    task = get("json-query")
    spec = json.dumps(specification_for(task))
    assert identify(spec) is task


def test_the_generated_specification_leaks_no_hidden_test():
    """The fixture must not hand over an answer it is meant to be tested on."""
    from mawe.bench.oracle import specification_for

    for task in select():
        spec = json.dumps(specification_for(task))
        assert "checks" not in json.loads(spec), task.slug
        for test in task.tests:
            expected = (test.expect_stdout or "").strip()
            if len(expected.split()) < 2 or test.match == "regex":
                continue
            assert expected not in spec, f"{task.slug}/{test.name}"


def test_the_oracle_rejects_an_unknown_quality():
    with pytest.raises(ValueError, match="quality"):
        OracleProvider("flawless")


def test_the_oracle_answers_every_role():
    provider = OracleProvider("perfect")
    task = get("fizzbuzz")
    for system, role in (
        ("You are the Product Manager agent", "product_manager"),
        ("You are the Developer agent", "developer"),
        ("You are the Code Reviewer agent", "reviewer"),
        ("You are an expert programmer working alone", "solo"),
        ("You are reviewing your own code", "self_critic"),
    ):
        response = provider.complete(system, task.prompt)
        assert response.text.strip(), role
        assert response.meta["role"] == role


def test_an_unidentifiable_prompt_does_not_abort_a_sweep():
    provider = OracleProvider("perfect")
    response = provider.complete("You are an expert programmer working alone",
                                 "do something vague")
    assert json.loads(response.text)["files"]


@pytest.mark.parametrize("slug", ["fizzbuzz", "word-count", "csv-column-stats",
                                  "shortest-path", "text-justify"])
def test_the_flawed_fixture_is_detectably_flawed(slug):
    """An equivalent mutant would silently become a success in the sweep.

    This is not hypothetical: taking the first mutant produced one for two of
    the twenty tasks, and the sweep duly reported condition A succeeding on
    tasks the fixture meant it to fail.
    """
    from mawe.bench.harness import score as score_files
    from mawe.bench.oracle import defective_source
    from mawe.bench.solutions import files_for as reference_files

    task = get(slug)
    broken = defective_source(task)
    assert broken is not None, f"{slug} has no mutant at all"
    assert not score_files(reference_files(slug, broken), task).success


def test_the_defective_variants_are_distinct():
    """A repeated defect would trip the engine's no-progress exit instead of
    exercising a long run."""
    for task in select(slugs=["fizzbuzz", "word-count", "shortest-path"]):
        variants = defective_variants(task)
        assert len(variants) == len(set(variants)), task.slug
        assert all(v != "" for v in variants)


@pytest.mark.parametrize("quality,expect_success", [
    ("perfect", True),
    ("flawed", False),
])
def test_the_oracle_quality_decides_the_score(quality, expect_success):
    task = get("fizzbuzz")
    runner = SingleModel(provider=OracleProvider(quality),
                         settings=Settings(max_iterations=1,
                                           sandbox_timeout_s=10),
                         database_url="sqlite://")
    row = run_one("A", runner, task)
    assert row.success is expect_success


def test_improving_lets_an_iterating_condition_recover():
    """The property the whole fixture exists to provide."""
    task = get("fizzbuzz")
    live = Settings(max_iterations=4, sandbox_timeout_s=10)

    one_shot = run_one("A", SingleModel(provider=OracleProvider("improving"),
                                        settings=live,
                                        database_url="sqlite://"), task)
    iterating = run_one("B", SelfRefine(provider=OracleProvider("improving"),
                                        settings=live,
                                        database_url="sqlite://"), task)
    assert not one_shot.success
    assert iterating.success
    assert iterating.iterations > one_shot.iterations


# ======================================================= the runner
def test_a_row_carries_both_kinds_of_outcome():
    task = get("fizzbuzz")
    row = run_one("A", SingleModel(provider=OracleProvider("perfect"),
                                   settings=Settings(max_iterations=1,
                                                     sandbox_timeout_s=10),
                                   database_url="sqlite://"), task)
    # what the condition said
    assert row.status == "approved"
    assert row.iterations == 1
    # what the hidden tests measured, independently
    assert row.success and row.pass_rate == 1.0
    assert row.hidden_tests_passed == row.hidden_tests_total == len(task.tests)
    # and the cost
    assert row.total_tokens > 0
    assert row.llm_calls == 0 or row.llm_calls > 0
    assert row.latency_s >= 0


def test_a_condition_that_raises_becomes_a_failed_row():
    """One bad run must not cost the other 239."""
    class Exploding:
        def run(self, prompt, **kw):
            raise RuntimeError("boom")

    row = run_one("A", Exploding(), get("fizzbuzz"))
    assert "boom" in row.error
    assert not row.success
    assert row.hidden_tests_total == 0


def test_run_condition_covers_every_task_and_repetition():
    tasks = select(slugs=["fizzbuzz", "palindrome"])
    rows = run_condition(
        "A", lambda: SingleModel(provider=OracleProvider("perfect"),
                                 settings=Settings(max_iterations=1,
                                                   sandbox_timeout_s=10),
                                 database_url="sqlite://"),
        tasks, repetitions=2)
    assert len(rows) == 4
    assert {r.repetition for r in rows} == {1, 2}
    assert {r.task for r in rows} == {"fizzbuzz", "palindrome"}
    assert all(r.success for r in rows)


def test_each_run_gets_a_fresh_runner():
    """Sharing one runner would let a fixture's per-task state leak."""
    built = []

    def factory():
        runner = SingleModel(provider=OracleProvider("perfect"),
                             settings=Settings(max_iterations=1,
                                               sandbox_timeout_s=0),
                             database_url="sqlite://")
        built.append(runner)
        return runner

    run_condition("A", factory, select(slugs=["fizzbuzz", "palindrome"]))
    assert len(built) == 2
    assert built[0] is not built[1]


def test_the_engine_also_runs_through_the_uniform_runner():
    task = get("fizzbuzz")
    row = run_one("C", Engine(provider=OracleProvider("perfect"),
                              settings=Settings(max_iterations=3,
                                                sandbox_timeout_s=10),
                              database_url="sqlite://"), task)
    assert row.success
    assert row.condition == "C"
    assert not row.error


def test_condition_labels_are_documented():
    assert set(CONDITION_NAMES) == {"A", "B", "C", "C'"}


# ======================================================= cost and storage
def test_pricing_is_computed_from_measured_tokens():
    pricing = Pricing(prompt_per_mtok=3.0, completion_per_mtok=15.0)
    assert pricing.cost(1_000_000, 0) == pytest.approx(3.0)
    assert pricing.cost(0, 1_000_000) == pytest.approx(15.0)
    assert pricing.cost(0, 0) == 0.0


def test_the_free_pricing_costs_nothing():
    from mawe.bench.experiment import FREE

    assert FREE.cost(10_000, 10_000) == 0.0
    assert "mock" in FREE.label


def test_rows_round_trip_through_json(tmp_path):
    rows = [RunRow(condition="A", task="fizzbuzz", difficulty="easy",
                   language="python", repetition=1, success=True,
                   pass_rate=1.0, prompt_tokens=10, completion_tokens=5)]
    path = to_json(rows, tmp_path / "s.json", {"model": "oracle-1"})
    back = from_json(path)
    assert len(back) == 1
    assert back[0].task == "fizzbuzz"
    assert back[0].success
    assert back[0].total_tokens == 15

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["metadata"]["model"] == "oracle-1"


def test_a_csv_is_written_with_a_header(tmp_path):
    rows = [RunRow(condition="A", task="fizzbuzz", difficulty="easy",
                   language="python", repetition=1)]
    path = to_csv(rows, tmp_path / "s.csv")
    text = path.read_text(encoding="utf-8")
    assert "condition" in text.splitlines()[0]
    assert "fizzbuzz" in text


def test_an_empty_sweep_still_writes_a_file(tmp_path):
    assert to_csv([], tmp_path / "empty.csv").exists()


def test_metadata_records_what_produced_the_numbers():
    meta = metadata_for(settings(), OracleProvider("perfect"),
                        Pricing(1.0, 2.0, "test"), repetitions=3)
    assert meta["provider"] == "oracle"
    assert meta["model"] == "oracle-1"
    assert meta["repetitions"] == 3
    assert meta["pricing"]["label"] == "test"
    assert meta["max_iterations"] == 5
    assert meta["recorded_at"]
