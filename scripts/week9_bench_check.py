"""Week 9 milestone - the benchmark suite is a valid measuring instrument.

    python scripts/week9_bench_check.py [--quick]

Phase 4 asks whether role separation produces more correct software than a
single model. Every number that answers it comes out of this benchmark, so the
benchmark has to be checked before it is trusted. Three things are measured
here, not asserted:

1. **Solvable.** Every task's reference solution passes every one of its own
   hidden tests. A task that fails this is a broken instrument, and in a sweep
   it would look like a finding: "all four conditions scored badly".

2. **Not vacuous.** A program that starts cleanly and does nothing scores zero
   tasks. If a stub could succeed anywhere, that task measures nothing.

3. **Discriminating.** Single defects are injected into the reference
   solutions and the hidden tests have to notice. The mutation score is the
   fraction caught. Surviving mutants are listed rather than hidden, because
   some are equivalent mutants - a textual change with no observable effect -
   which is a known limit of the method rather than a hole in the tests.

`--quick` skips the mutation sweep, which is the slow part.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mawe.bench import TASKS, composition, score  # noqa: E402
from mawe.bench import mutation  # noqa: E402
from mawe.bench.seed import seed  # noqa: E402
from mawe.bench.solutions import (  # noqa: E402
    degenerate_files_for,
    files_for,
)
from mawe.db import make_engine  # noqa: E402
from mawe.sandbox.runner import interpreter_available  # noqa: E402

LINE = "=" * 96
MUTANTS_PER_TASK = 10

results = []


def check(label, condition, detail=""):
    results.append(bool(condition))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}"
          + (f"  -  {detail}" if detail else ""))
    return bool(condition)


def section(title):
    print()
    print(LINE)
    print(title)
    print(LINE)


# ---------------------------------------------------------------- 1
def suite_shape():
    section("1 - the suite matches the experimental design")
    counts = composition()
    check("20 tasks", counts["tasks"] == 20, f"{counts['tasks']} tasks")
    check("7 easy / 8 medium / 5 hard",
          (counts["easy"], counts["medium"], counts["hard"]) == (7, 8, 5),
          f"{counts['easy']}/{counts['medium']}/{counts['hard']}")
    check("two languages", counts["python"] > 0 and counts["javascript"] > 0,
          f"{counts['python']} python, {counts['javascript']} javascript")
    check("hidden tests present", counts["tests"] >= 100,
          f"{counts['tests']} hidden tests, "
          f"{counts['tests'] / counts['tasks']:.1f} per task")

    if not interpreter_available("javascript"):
        print("\n  NOTE: node is not installed, so the 8 JavaScript tasks "
              "will be skipped below.")


# ---------------------------------------------------------------- 2
def solvable():
    section("2 - every task is solvable: the reference passes its own tests")
    print(f"  {'task':<24}{'difficulty':<11}{'lang':<12}{'hidden tests':>13}")
    print("  " + "-" * 60)

    failures, skipped, total_tests = [], [], 0
    for task in TASKS:
        result = score(files_for(task.slug), task)
        if result.skipped:
            skipped.append(task.slug)
            print(f"  {task.slug:<24}{task.difficulty:<11}"
                  f"{task.language:<12}{'skipped':>13}")
            continue
        total_tests += result.total
        mark = f"{result.tests_passed}/{result.total}"
        print(f"  {task.slug:<24}{task.difficulty:<11}"
              f"{task.language:<12}{mark:>13}")
        if not result.success:
            failures.append(result)

    print()
    check("every reference solution passes every hidden test", not failures,
          f"{total_tests} tests across {len(TASKS) - len(skipped)} tasks")
    for result in failures:
        for outcome in result.outcomes:
            if not outcome.passed:
                print(f"         {result.task.slug}: {outcome.line()[:110]}")


# ---------------------------------------------------------------- 3
def not_vacuous():
    section("3 - the tests are not vacuous: a do-nothing program scores zero")
    successes, passed, total = [], 0, 0
    for task in TASKS:
        result = score(degenerate_files_for(task.slug), task)
        if result.skipped:
            continue
        passed += result.tests_passed
        total += result.total
        if result.success:
            successes.append(task.slug)

    check("no task is satisfied by a stub", not successes,
          f"0/{len(TASKS)} tasks" if not successes
          else f"satisfied: {successes}")
    check("a stub passes almost no individual tests",
          total and passed / total < 0.05,
          f"{passed}/{total} tests ({passed / total * 100:.1f}%) - "
          f"the empty-input cases, which a stub genuinely satisfies")


# ---------------------------------------------------------------- 4
def discriminating(quick: bool):
    section("4 - the tests discriminate: injected defects are caught")
    if quick:
        print("  skipped (--quick)")
        return

    started = time.time()
    print(f"  injecting up to {MUTANTS_PER_TASK} single-edit defects per task, "
          f"discarding any that do not parse\n")
    print(f"  {'task':<24}{'killed':>9}{'score':>9}   survivors")
    print("  " + "-" * 78)

    rows = []
    for task in TASKS:
        if not interpreter_available(task.language):
            continue
        row = mutation.run_task(task, limit=MUTANTS_PER_TASK)
        rows.append(row)
        survivors = ", ".join(m.operator for m in row.survived) or "-"
        shown = f"{row.killed}/{row.total}"
        print(f"  {task.slug:<24}{shown:>9}{row.score * 100:8.0f}%   "
              f"{survivors[:40]}")

    overall = mutation.overall(rows)
    unmeasured = [r.task.slug for r in rows if r.total == 0]
    print()
    check("the hidden tests catch most injected defects",
          overall["mutation_score"] >= 0.80,
          f"mutation score {overall['mutation_score'] * 100:.1f}% "
          f"({int(overall['killed'])}/{int(overall['mutants'])} killed)")
    check("every task was mutated", not unmeasured,
          "all tasks mutated" if not unmeasured else
          f"no mutable operators in: {', '.join(unmeasured)} - "
          f"strength rests on section 3 for these")
    print(f"\n  elapsed: {time.time() - started:.0f}s")


# ---------------------------------------------------------------- 5
def persisted():
    section("5 - the suite is reproducible from the database")
    engine = make_engine("sqlite://")
    ids = seed(engine)
    check("every task seeds into benchmark_tasks", len(ids) == len(TASKS),
          f"{len(ids)} rows")
    again = seed(engine)
    check("seeding is idempotent", again == ids,
          "re-running updates in place rather than duplicating")


def main(argv) -> int:
    quick = "--quick" in argv
    print(LINE)
    print("WEEK 9 MILESTONE - the Phase 4 benchmark suite")
    print(LINE)

    suite_shape()
    solvable()
    not_vacuous()
    discriminating(quick)
    persisted()

    passed, total = sum(results), len(results)
    print()
    print(LINE)
    print(f"  {passed}/{total} checks passed")
    print(f"\n  M-W9 {'MET' if passed == total else 'NOT MET'} - the benchmark "
          f"is solvable, non-vacuous and discriminating.")
    print("  What it does NOT yet show: how any model scores on it. That needs "
          "a real\n  provider and is Weeks 10-12.")
    print(LINE)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
