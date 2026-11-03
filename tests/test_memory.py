"""Week 7: context compression keeps long runs inside a token budget."""

import pytest

from mawe.config import Settings
from mawe.graph import run_workflow
from mawe.llm import MockProvider, varied_reviewer_script
from mawe.memory import (
    IterationRecord,
    LLMSummariser,
    MemoryManager,
    StructuredSummariser,
)


def files(n_lines=40, path="src/main.py"):
    body = "\n".join(f"line {i} of generated code" for i in range(n_lines))
    return [{"path": path, "language": "python", "content": body}]


def record(i, issues=("criterion 4 fails",), n_lines=40):
    return IterationRecord(
        iteration=i,
        code_hash=f"hash{i:04d}" + "0" * 50,
        files=["src/main.py"],
        total_lines=n_lines,
        file_bodies=files(n_lines),
        verdict="reject",
        severity="major",
        issues=list(issues),
        tests_passed=3,
        tests_failed=1,
    )


def history(n, **kw):
    return [record(i, **kw) for i in range(1, n + 1)]


# ------------------------------------------------------------- recording
def test_record_captures_the_iteration():
    state = {
        "iteration": 3, "code_hash": "abc123", "files": files(12),
        "verdict": "reject", "severity": "major",
        "issues": ["criterion 2 fails"], "tests_passed": 4, "tests_failed": 1,
    }
    r = MemoryManager.record_from_state(state)
    assert r.iteration == 3
    assert r.files == ["src/main.py"]
    assert r.total_lines == 12
    assert r.file_bodies[0]["content"].startswith("line 0")
    assert r.tests_failed == 1


def test_one_line_is_compact_but_keeps_the_essentials():
    line = record(2).one_line()
    assert "iteration 2" in line
    assert "criterion 4 fails" in line
    assert "reject/major" in line
    assert len(line) < 300


def test_one_line_truncates_a_long_issue_list():
    line = record(1, issues=[f"issue number {i}" for i in range(9)]).one_line()
    assert "+7 more" in line


# ------------------------------------------------------------ summarising
def test_structured_summary_mentions_every_iteration():
    summary = StructuredSummariser().summarise(history(4))
    for i in range(1, 5):
        assert f"iteration {i}" in summary


def test_structured_summary_flags_recurring_issues():
    summary = StructuredSummariser().summarise(history(3))
    assert "recurring, still unresolved" in summary


def test_structured_summary_of_nothing_is_empty():
    assert StructuredSummariser().summarise([]) == ""


def test_llm_summariser_uses_the_provider():
    provider = MockProvider({"summariser": ["a short prose summary"]})
    summariser = LLMSummariser(provider)
    assert summariser.summarise(history(3)) == "a short prose summary"
    assert summariser.tokens_spent > 0


# -------------------------------------------------------- the compression
def test_compression_disabled_sends_everything():
    manager = MemoryManager(enabled=False)
    section, stats = manager.build_history(history(5), files())
    assert stats.reduction == 0.0
    assert stats.tokens_compressed == stats.tokens_uncompressed
    assert "iteration 1" in section and "iteration 4" in section


def test_compression_enabled_shrinks_the_context():
    manager = MemoryManager(enabled=True)
    _section, stats = manager.build_history(history(5), files())
    assert stats.tokens_compressed < stats.tokens_uncompressed
    assert stats.reduction > 0.4, "H5 expects at least a 40% reduction"


def test_the_latest_version_is_always_kept_in_full():
    manager = MemoryManager(enabled=True, keep_full=1)
    section, _ = manager.build_history(history(6), files(n_lines=30))
    assert "latest version only" in section
    assert "line 29 of generated code" in section, "the current source is intact"


def test_older_versions_are_collapsed_not_replayed():
    manager = MemoryManager(enabled=True)
    section, _ = manager.build_history(history(6), files())
    assert "PROGRESS LOG" in section
    assert section.count("--- iteration") == 0


def test_keep_full_is_configurable():
    one = MemoryManager(enabled=True, keep_full=1)
    _s1, stats1 = one.build_history(history(8), files())
    three = MemoryManager(enabled=True, keep_full=3)
    _s3, stats3 = three.build_history(history(8), files())
    assert stats1.iterations_compressed > stats3.iterations_compressed


def test_single_iteration_needs_no_compression():
    manager = MemoryManager(enabled=True)
    section, stats = manager.build_history(history(1), files())
    assert stats.iterations_compressed == 0
    assert "YOUR PREVIOUS FILES" in section


def test_no_history_at_all_is_handled():
    manager = MemoryManager(enabled=True)
    section, stats = manager.build_history([], [])
    assert section == ""
    assert stats.reduction == 0.0


# ------------------------------------------------------------- the budget
def test_a_tight_budget_drops_the_oldest_entries():
    manager = MemoryManager(enabled=True, token_budget=160)
    section, stats = manager.build_history(history(30), files(n_lines=5))
    assert "omitted to stay within" in section
    assert stats.tokens_compressed <= manager.token_budget * 1.4


def test_context_stays_bounded_as_iterations_grow():
    """The property that matters: context must not grow linearly for ever."""
    manager = MemoryManager(enabled=True, token_budget=600)
    sizes = []
    for n in (2, 5, 10, 20, 40, 80):
        _s, stats = manager.build_history(history(n), files(n_lines=20))
        sizes.append(stats.tokens_compressed)

    assert sizes[-1] <= manager.token_budget * 1.4, sizes
    # doubling the iterations must not double the context
    assert sizes[-1] < sizes[-2] * 1.6, sizes


def test_reduction_improves_with_run_length():
    manager = MemoryManager(enabled=True, token_budget=4000)
    short = manager.build_history(history(3), files())[1].reduction
    long = manager.build_history(history(20), files())[1].reduction
    assert long > short


# --------------------------------------------------------- integration
@pytest.mark.parametrize("enabled,expect_reduction", [(False, False), (True, True)])
def test_end_to_end_ablation(enabled, expect_reduction):
    settings = Settings(max_iterations=8, sandbox_timeout_s=0)
    settings.summarisation_enabled = enabled
    state = run_workflow("build something",
                         MockProvider(varied_reviewer_script(12)),
                         settings=settings)
    before = state["context_tokens_before"]
    after = state["context_tokens_after"]
    assert before > 0
    if expect_reduction:
        assert after < before
        assert (1 - after / before) > 0.4
    else:
        assert after == before


def test_history_accumulates_through_the_graph():
    settings = Settings(max_iterations=5, sandbox_timeout_s=0)
    state = run_workflow("build something",
                         MockProvider(varied_reviewer_script(10)),
                         settings=settings)
    assert len(state["history"]) == state["iteration"]
    assert [r.iteration for r in state["history"]] == \
           list(range(1, state["iteration"] + 1))


def test_memory_summaries_are_persisted():
    from mawe.db import Run, session_scope
    from mawe.engine import Engine

    settings = Settings(max_iterations=6, sandbox_timeout_s=0)
    engine = Engine(provider=MockProvider(varied_reviewer_script(10)),
                    settings=settings, database_url="sqlite://")
    result = engine.run("build something")

    with session_scope(engine.db) as session:
        run = session.get(Run, result.run_id)
        summaries = run.memory_summaries
    assert summaries, "compression measurements should be recorded"
    assert any(s.tokens_before >= s.tokens_after for s in summaries)
