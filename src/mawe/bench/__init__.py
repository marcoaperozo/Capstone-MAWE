"""Phase 4 benchmark suite, baselines fixture and experiment runner.

Kept in its own package because nothing in the engine may depend on it: the
tasks' hidden tests must never be reachable from a prompt, and
`tests/test_benchmark.py` asserts that one-way dependency.
"""

from .experiment import (
    CONDITION_NAMES,
    CONDITIONS,
    Pricing,
    RunRow,
    run_condition,
    run_one,
)
from .harness import SuiteScore, TaskScore, TestOutcome, score, score_all
from .tasks import TASKS, BenchTask, HiddenTest, composition, get, select

__all__ = [
    "TASKS", "BenchTask", "HiddenTest", "composition", "get", "select",
    "SuiteScore", "TaskScore", "TestOutcome", "score", "score_all",
    "CONDITIONS", "CONDITION_NAMES", "Pricing", "RunRow",
    "run_one", "run_condition",
]
