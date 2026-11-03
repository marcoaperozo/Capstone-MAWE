"""Phase 4 benchmark suite and scoring harness.

Weeks 9 to 12.  Kept in its own package because nothing in the engine may
depend on it: the tasks' hidden tests must never be reachable from a prompt.
"""

from .harness import SuiteScore, TaskScore, TestOutcome, score, score_all
from .tasks import TASKS, BenchTask, HiddenTest, composition, get, select

__all__ = [
    "TASKS", "BenchTask", "HiddenTest", "composition", "get", "select",
    "SuiteScore", "TaskScore", "TestOutcome", "score", "score_all",
]
