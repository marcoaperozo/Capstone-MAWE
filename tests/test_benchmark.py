"""Week 9: the benchmark suite and its scoring harness.

Two kinds of test live here, and the second kind matters more.

The ordinary kind checks the harness: a correct program scores, a wrong one
does not, a crashing one does not hang the sweep.

The structural kind checks the *experiment* rather than the code. If a hidden
test or a reference solution could reach a prompt, every number Phase 4
produces is worthless, and that is not something code review reliably catches
six weeks later. So it is asserted.
"""

import json

import pytest

from mawe.bench import composition, get, score, score_all, select
from mawe.bench.harness import SuiteScore
from mawe.bench.solutions import (
    SOURCES,
    degenerate_files_for,
    files_for,
)
from mawe.bench.tasks import TASKS, BenchTask, HiddenTest

PY = "python"


def files(content, path="src/main.py", language=PY):
    return [{"path": path, "language": language, "content": content}]


# ================================================= the suite's composition
def test_the_suite_matches_the_proposal():
    counts = composition()
    assert counts["tasks"] == 20
    assert (counts["easy"], counts["medium"], counts["hard"]) == (7, 8, 5)
    assert counts["python"] and counts["javascript"]
    assert counts["python"] + counts["javascript"] == 20


def test_slugs_are_unique():
    slugs = [t.slug for t in TASKS]
    assert len(slugs) == len(set(slugs))


def test_every_task_has_several_tests_and_an_error_case():
    for task in TASKS:
        assert len(task.tests) >= 3, task.slug
        names = [t.name for t in task.tests]
        assert len(names) == len(set(names)), f"{task.slug} has duplicate names"


def test_a_task_rejects_a_bad_difficulty():
    with pytest.raises(ValueError):
        BenchTask(slug="x", title="x", difficulty="trivial", language=PY,
                  prompt="x", tests=(HiddenTest("a"), HiddenTest("b"),
                                     HiddenTest("c")))


def test_a_task_needs_enough_tests():
    with pytest.raises(ValueError):
        BenchTask(slug="x", title="x", difficulty="easy", language=PY,
                  prompt="x", tests=(HiddenTest("only one"),))


def test_select_filters():
    assert all(t.difficulty == "hard" for t in select(difficulty="hard"))
    assert all(t.language == PY for t in select(language=PY))
    assert [t.slug for t in select(slugs=["fizzbuzz"])] == ["fizzbuzz"]
    assert select() == list(TASKS)


def test_get_names_the_alternatives_when_the_slug_is_wrong():
    with pytest.raises(KeyError, match="fizzbuzz"):
        get("fizz-buzz")


# ========================================= hidden tests stay hidden
def test_a_prompt_never_contains_its_own_expected_output():
    """The prompt states the output *format*; it must not leak an answer.

    Single words are excluded deliberately. A prompt has to name the words the
    program is required to print - "balanced", "unreachable", "FizzBuzz" - and
    finding one of those in the prompt is the contract being specified, not a
    test being given away. What would be a leak is an input-specific answer:
    several tokens, or several lines, that only make sense for one test's
    input.
    """
    for task in TASKS:
        for test in task.tests:
            expected = (test.expect_stdout or "").strip()
            if test.match == "regex" or len(expected.split()) < 2:
                continue
            assert expected not in task.prompt, \
                f"{task.slug}/{test.name} leaks its expected output"


def test_no_engine_module_imports_the_benchmark():
    """The one-way dependency the experiment rests on.

    `mawe.bench` may import the engine; nothing the engine uses to build a
    prompt may import `mawe.bench`, or a hidden test could reach a model.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "mawe"
    offenders = []
    for path in root.rglob("*.py"):
        if "bench" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "bench.tasks" in text or "bench.solutions" in text or \
                "from .bench" in text or "from ..bench" in text:
            offenders.append(path.name)
    assert not offenders, f"engine modules importing the benchmark: {offenders}"


# ================================================= scoring a solution
def test_a_correct_solution_scores_full_marks():
    task = get("fizzbuzz")
    result = score(files_for(task.slug), task)
    assert result.success
    assert result.pass_rate == 1.0
    assert result.tests_failed == 0
    assert "SUCCESS" in result.report()


def test_a_wrong_solution_fails_the_tests_it_should():
    task = get("fizzbuzz")
    wrong = files("import sys\nfor i in range(1, int(sys.argv[1]) + 1):\n"
                  "    print(i)\n")
    result = score(wrong, task)
    assert not result.success
    assert 0 < result.tests_passed < result.total, "partial credit"
    assert "first five" in result.failed_names


def test_a_do_nothing_program_never_succeeds():
    """If this ever passes a task, that task's tests measure nothing."""
    for task in TASKS:
        result = score(degenerate_files_for(task.slug), task)
        assert not result.success, f"{task.slug} is satisfied by a stub"


def test_a_program_that_does_not_run_scores_zero_without_raising():
    task = get("fizzbuzz")
    result = score(files("this is not python at all ((("), task)
    assert result.tests_passed == 0
    assert not result.success


def test_no_entry_point_is_a_failure_not_an_exception():
    task = get("fizzbuzz")
    result = score([{"path": "notes.txt", "language": PY, "content": "hi"}],
                   task)
    assert result.tests_passed == 0
    assert not result.success


def test_an_empty_file_list_scores_zero():
    assert not score([], get("fizzbuzz")).success


def test_a_hanging_program_is_killed_and_fails():
    task = get("word-count")
    result = score(files("while True:\n    pass\n"), task, timeout_s=2)
    assert not result.success
    assert any(o.timed_out for o in result.outcomes)


def test_a_crash_does_not_count_as_reporting_an_error():
    """Both a clean rejection and an uncaught exception exit 1.

    Mutation testing found that this made every error-path test in the suite
    accept a crash, so the harness distinguishes them.
    """
    task = get("fizzbuzz")
    crashing = files("import sys\nn = int(sys.argv[1])\n"
                     "for i in range(1, n + 1):\n    print(i)\n")
    result = score(crashing, task)
    failed = {o.test.name: o for o in result.outcomes if not o.passed}
    assert "missing argument" in failed
    assert "crashed" in failed["missing argument"].reason


def test_metrics_are_reported_for_the_database():
    result = score(files_for("fizzbuzz"), get("fizzbuzz"))
    metrics = result.as_metrics()
    assert metrics["task_success"] == 1.0
    assert metrics["pass_rate"] == 1.0
    assert metrics["hidden_tests_passed"] == metrics["hidden_tests_total"]


def test_stop_on_first_failure_short_circuits():
    task = get("fizzbuzz")
    full = score(files("print(1)\n"), task)
    quick = score(files("print(1)\n"), task, stop_on_first_failure=True)
    assert len(quick.outcomes) < len(full.outcomes)
    assert not quick.success


# ================================================= scoring a whole suite
def test_score_all_aggregates_and_skips_missing_solutions():
    tasks = select(slugs=["fizzbuzz", "palindrome"])
    suite = score_all({"fizzbuzz": files_for("fizzbuzz")}, tasks)
    assert suite.successes == 1
    assert len(suite.scored) == 1, "the unsolved task is skipped, not scored"
    assert suite.task_success_rate == 1.0


def test_suite_rates_are_zero_when_nothing_was_scored():
    empty = SuiteScore()
    assert empty.task_success_rate == 0.0
    assert empty.mean_pass_rate == 0.0
    assert empty.by_difficulty() == {}


def test_by_difficulty_splits_the_results():
    tasks = select(slugs=["fizzbuzz", "rpn-calculator"])
    suite = score_all({t.slug: files_for(t.slug) for t in tasks}, tasks)
    split = suite.by_difficulty()
    assert split["easy"]["successes"] == 1.0
    assert split["medium"]["successes"] == 1.0
    assert "hard" not in split


# ================================================= reference solutions
def test_there_is_a_reference_for_every_task():
    assert set(SOURCES) == {t.slug for t in TASKS}


@pytest.mark.parametrize("slug", [t.slug for t in TASKS])
def test_the_reference_solution_passes_every_hidden_test(slug):
    """A task whose own reference fails is a broken measuring instrument."""
    result = score(files_for(slug), get(slug))
    if result.skipped:
        pytest.skip(result.skipped)
    assert result.success, result.report()


def test_the_reference_is_written_to_the_expected_entry_point():
    for task in TASKS:
        assert files_for(task.slug)[0]["path"] == task.entry_path


# ================================================= mutation testing
def test_mutants_are_syntactically_valid_and_different():
    from mawe.bench.mutation import mutants_for

    task = get("fizzbuzz")
    mutants = mutants_for(task, limit=5)
    assert mutants
    for mutant in mutants:
        assert mutant.source != SOURCES[task.slug]
        compile(mutant.source, "<mutant>", "exec")   # raises if invalid


def test_mutation_skips_string_literals_and_comments():
    from mawe.bench.mutation import _strip_strings, mutants_for

    source = SOURCES["fizzbuzz"]
    spans = _strip_strings(source, PY)
    assert spans, "the reference does contain string literals"
    for mutant in mutants_for(get("fizzbuzz")):
        assert not any(start <= mutant.position < end for start, end in spans)


def test_a_mutant_of_a_well_tested_task_is_killed():
    from mawe.bench.mutation import run_task

    result = run_task(get("fizzbuzz"), limit=4)
    assert result.total == 4
    assert result.killed == result.total, \
        f"survivors: {[m.label for m in result.survived]}"
    assert result.score == 1.0


def test_the_limit_spreads_across_operators():
    from mawe.bench.mutation import mutants_for

    chosen = mutants_for(get("meeting-free-slots"), limit=6)
    assert len(chosen) == 6
    assert len({m.operator for m in chosen}) > 1, \
        "a cap must not collapse the sample onto one operator"


def test_overall_handles_an_empty_run():
    from mawe.bench.mutation import overall

    assert overall([])["mutation_score"] == 0.0


# ================================================= persistence
def test_the_suite_seeds_into_the_database(tmp_path):
    from mawe.bench.seed import seed, task_ids
    from mawe.db import BenchmarkTask, make_engine, session_scope

    engine = make_engine(f"sqlite:///{tmp_path / 'bench.db'}")
    ids = seed(engine)
    assert len(ids) == 20

    with session_scope(engine) as session:
        rows = session.query(BenchmarkTask).all()
        assert len(rows) == 20
        row = next(r for r in rows if r.name == "fizzbuzz")
        assert row.difficulty == "easy"
        assert row.language == PY
        assert row.prompt == get("fizzbuzz").prompt
        stored = json.loads(row.hidden_tests)
        assert len(stored) == len(get("fizzbuzz").tests)
        assert stored[0]["expect_stdout"]

    assert task_ids(engine) == ids


def test_seeding_twice_updates_rather_than_duplicates(tmp_path):
    from mawe.bench.seed import seed
    from mawe.db import BenchmarkTask, make_engine, session_scope

    engine = make_engine(f"sqlite:///{tmp_path / 'bench.db'}")
    first = seed(engine)
    second = seed(engine)
    assert first == second

    with session_scope(engine) as session:
        assert session.query(BenchmarkTask).count() == 20
