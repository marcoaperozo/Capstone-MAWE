"""Week 10 milestone - the four-condition comparison runs, and can see a
difference.

    python scripts/week10_baseline_check.py [--quick] [--out DIR]

Phase 4's claim is comparative, so the comparison apparatus has to be
trustworthy before any model is pointed at it. The failure this guards against
is specific and expensive: run 240 real API calls, get zeros in every column,
and be unable to say whether the models did badly or the plumbing is broken.

So the sweep is driven by `bench.oracle`, a fixture whose answers are known in
advance:

  perfect     every condition is handed the reference solution
  improving   every condition is handed a defective version first and the
              reference on any retry

With `perfect`, all four conditions must score 20/20. Anything less is a bug
in the pipeline, not a finding.

With `improving`, condition A - one model, one call, no second chance - must
score strictly worse than the conditions that iterate. That is the property
that matters: if the pipeline cannot detect a difference it was built to
detect, no result it produces later means anything.

`--quick` runs a 6-task subset.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mawe.baselines import SelfRefine, SingleModel  # noqa: E402
from mawe.bench import TASKS, select  # noqa: E402
from mawe.bench.experiment import (  # noqa: E402
    CONDITION_NAMES,
    Pricing,
    metadata_for,
    run_condition,
    to_csv,
    to_json,
)
from mawe.bench.oracle import OracleProvider  # noqa: E402
from mawe.bench.seed import seed  # noqa: E402
from mawe.config import Settings  # noqa: E402
from mawe.db import make_engine  # noqa: E402
from mawe.engine import Engine  # noqa: E402

LINE = "=" * 96
QUICK_SLUGS = ["fizzbuzz", "palindrome", "sum-args", "rpn-calculator",
               "matrix-spiral", "json-query"]

#: Published rates for a mid-sized model, in dollars per million tokens. An
#: input to the report, not a fact about the code: the sweep records whichever
#: rates it used so the cost column can be recomputed when they change.
EXAMPLE_PRICING = Pricing(prompt_per_mtok=3.0, completion_per_mtok=15.0,
                          label="illustrative: $3/$15 per Mtok")

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


def conditions(quality: str, settings: Settings):
    """The four conditions, each as a factory that builds a fresh runner.

    Every condition gets its own provider instance per run and the same
    settings object, so the only thing that differs between them is the
    process being tested.
    """
    ablation = Settings(**settings.__dict__)
    ablation.summarisation_enabled = False

    return [
        ("A", lambda: SingleModel(provider=OracleProvider(quality),
                                  settings=settings,
                                  database_url="sqlite://")),
        ("B", lambda: SelfRefine(provider=OracleProvider(quality),
                                 settings=settings,
                                 database_url="sqlite://")),
        ("C", lambda: Engine(provider=OracleProvider(quality),
                             settings=settings, database_url="sqlite://")),
        ("C'", lambda: Engine(provider=OracleProvider(quality),
                              settings=ablation, database_url="sqlite://")),
    ]


def sweep(quality: str, tasks, settings: Settings, task_ids):
    return sweep_conditions(list(CONDITION_NAMES), quality, tasks, settings,
                            task_ids)


def sweep_conditions(labels, quality: str, tasks, settings: Settings,
                     task_ids):
    rows_by_condition = {}
    wanted = [(name, factory)
              for name, factory in conditions(quality, settings)
              if name in labels]
    for label, factory in wanted:
        started = time.time()
        rows = run_condition(label, factory, tasks, repetitions=1,
                             pricing=EXAMPLE_PRICING, task_ids=task_ids)
        rows_by_condition[label] = rows
        scored = [r for r in rows if not r.skipped]
        successes = sum(1 for r in scored if r.success)
        tokens = sum(r.total_tokens for r in rows)
        cost = sum(r.cost_usd for r in rows)
        iterations = sum(r.iterations for r in rows)
        errors = [r for r in rows if r.error]
        print(f"  {label:<3} {CONDITION_NAMES[label]:<26}"
              f"{successes:>3}/{len(scored):<4} tasks   "
              f"{iterations:>3} iters  {tokens:>8,} tok  ${cost:>7.4f}"
              + (f"   {len(errors)} ERRORS" if errors else ""))
        for row in errors[:3]:
            print(f"        {row.task}: {row.error[:90]}")
        if time.time() - started > 0:
            pass
    return rows_by_condition


def summarise(rows_by_condition, tasks):
    out = {}
    for label, rows in rows_by_condition.items():
        scored = [r for r in rows if not r.skipped]
        out[label] = {
            "successes": sum(1 for r in scored if r.success),
            "scored": len(scored),
            "mean_pass_rate": (sum(r.pass_rate for r in scored) / len(scored)
                               if scored else 0.0),
            "tokens": sum(r.total_tokens for r in rows),
            "cost": sum(r.cost_usd for r in rows),
            "iterations": sum(r.iterations for r in rows),
            "errors": sum(1 for r in rows if r.error),
        }
    return out


def main(argv) -> int:
    quick = "--quick" in argv
    out_dir = None
    if "--out" in argv:
        out_dir = Path(argv[argv.index("--out") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)

    tasks = select(slugs=QUICK_SLUGS) if quick else list(TASKS)
    settings = Settings(max_iterations=5, sandbox_timeout_s=10)
    db = make_engine("sqlite://")
    task_ids = seed(db)

    print(LINE)
    print("WEEK 10 MILESTONE - the four-condition comparison")
    print(LINE)
    print(f"  tasks        : {len(tasks)}"
          + ("  (--quick subset)" if quick else ""))
    print("  conditions   : A single model | B self-refinement | "
          "C engine | C' engine, no summarisation")
    print(f"  iteration cap: {settings.max_iterations}")
    print(f"  pricing      : {EXAMPLE_PRICING.label}")
    print("  provider     : bench.oracle fixture, NOT a model")

    # ---------------------------------------------------------------- 0
    section("0 - the fixture itself is valid")
    print("  The sweep below only means something if the fixture's defective")
    print("  answers are ones the hidden tests actually catch. An equivalent")
    print("  mutant would hand a condition code that passes everything, and")
    print("  the sweep would report a success where it meant to show a")
    print("  failure - which is exactly what happened before this was checked.")
    print()
    from mawe.bench.harness import score as score_files
    from mawe.bench.oracle import defective_source
    from mawe.bench.solutions import files_for as reference_files

    undetected = []
    for task in tasks:
        broken = defective_source(task)
        if broken is None:
            undetected.append(f"{task.slug} (no mutant)")
        elif score_files(reference_files(task.slug, broken), task,
                         stop_on_first_failure=True).success:
            undetected.append(f"{task.slug} (undetected)")
    check("every task has a defect the hidden tests catch", not undetected,
          f"{len(tasks)} tasks" if not undetected
          else ", ".join(undetected))

    # ---------------------------------------------------------------- 1
    section("1 - with a correct answer available, every condition scores it")
    started = time.time()
    perfect = sweep("perfect", tasks, settings, task_ids)
    stats = summarise(perfect, tasks)
    print()
    for label in ("A", "B", "C", "C'"):
        row = stats[label]
        check(f"{label} solves every task",
              row["successes"] == row["scored"] and row["scored"] > 0,
              f"{row['successes']}/{row['scored']}")
    check("no condition raised",
          all(stats[label]["errors"] == 0 for label in stats),
          "all runs completed")
    print(f"\n  elapsed: {time.time() - started:.0f}s")

    # ---------------------------------------------------------------- 2
    section("2 - with one retry needed, the comparison sees the difference")
    started = time.time()
    improving = sweep("improving", tasks, settings, task_ids)
    stats = summarise(improving, tasks)
    print()

    a, b, c, cprime = (stats["A"], stats["B"], stats["C"], stats["C'"])
    check("A, which cannot retry, fails tasks the others solve",
          a["successes"] < b["successes"] and a["successes"] < c["successes"],
          f"A {a['successes']}  B {b['successes']}  C {c['successes']}  "
          f"C' {cprime['successes']}")
    check("the iterating conditions recover fully",
          b["successes"] == b["scored"] and c["successes"] == c["scored"],
          f"B {b['successes']}/{b['scored']}, C {c['successes']}/{c['scored']}")
    check("A is the cheapest and worst, which is the trade-off being measured",
          a["tokens"] < c["tokens"],
          f"A {a['tokens']:,} tok for {a['successes']} successes; "
          f"C {c['tokens']:,} tok for {c['successes']}")

    # cost per *successful* task - the proposal's framing
    print()
    print(f"  {'condition':<30}{'successes':>10}{'tokens':>10}"
          f"{'$ / success':>14}")
    print("  " + "-" * 64)
    for label in ("A", "B", "C", "C'"):
        row = stats[label]
        per = row["cost"] / row["successes"] if row["successes"] else float("inf")
        shown = f"${per:.5f}" if row["successes"] else "n/a"
        print(f"  {label + ' ' + CONDITION_NAMES[label]:<30}"
              f"{row['successes']:>10}{row['tokens']:>10,}{shown:>14}")
    print(f"\n  elapsed: {time.time() - started:.0f}s")

    # ---------------------------------------------------------------- 3
    section("3 - the ablation changes what it should and nothing else")
    print("  C and C' were byte-identical above, and should have been: both")
    print("  runs finished at iteration 2, so there was no older iteration to")
    print("  compress. The ablation needs a longer run, so this section uses a")
    print("  fixture that needs three revisions before it gets the task right.")
    print()

    ablation_tasks = select(slugs=QUICK_SLUGS)
    long_settings = Settings(max_iterations=6, sandbox_timeout_s=10)
    long_rows = sweep_conditions(
        ["C", "C'"], "slow", ablation_tasks, long_settings, task_ids)
    stats_long = summarise(long_rows, ablation_tasks)
    c_long, cp_long = stats_long["C"], stats_long["C'"]

    print()
    check("C and C' reach the same outcomes",
          c_long["successes"] == cp_long["successes"],
          f"both {c_long['successes']}/{c_long['scored']} - summarisation "
          f"must not change correctness")
    check("the runs are long enough for compression to apply",
          c_long["iterations"] >= 3 * len(ablation_tasks),
          f"{c_long['iterations']} iterations over "
          f"{len(ablation_tasks)} tasks")
    saved = (1 - c_long["tokens"] / cp_long["tokens"]) * 100 \
        if cp_long["tokens"] else 0.0
    check("C' sends more tokens than C",
          cp_long["tokens"] > c_long["tokens"],
          f"C {c_long['tokens']:,} vs C' {cp_long['tokens']:,} "
          f"({saved:.1f}% saved at this run length)")

    # ---------------------------------------------------------------- 4
    section("4 - a sweep can be saved and re-analysed without re-running")
    all_rows = [r for rows in improving.values() for r in rows]
    target = out_dir or Path(
        __import__("tempfile").mkdtemp(prefix="mawe-week10-"))
    meta = metadata_for(settings, OracleProvider("improving"),
                        EXAMPLE_PRICING, 1)
    json_path = to_json(all_rows, target / "week10-sweep.json", meta)
    csv_path = to_csv(all_rows, target / "week10-sweep.csv")

    from mawe.bench.experiment import from_json
    reloaded = from_json(json_path)
    check("every row round-trips through JSON",
          len(reloaded) == len(all_rows)
          and [r.success for r in reloaded] == [r.success for r in all_rows],
          f"{len(reloaded)} rows")
    check("a CSV is written for the write-up", csv_path.exists(),
          str(csv_path))

    passed, total = sum(results), len(results)
    print()
    print(LINE)
    print(f"  {passed}/{total} checks passed")
    print(f"\n  M-W10 {'MET' if passed == total else 'NOT MET'} - the four "
          f"conditions run uniformly and the comparison\n  detects a quality "
          f"difference it was built to detect.")
    print("  What it does NOT show: how a real model scores. These numbers "
          "come from a\n  fixture with a known answer, and measure the "
          "apparatus, not any model.")
    print(LINE)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
