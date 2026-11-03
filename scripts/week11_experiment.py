"""Week 11 - the full experiment: four conditions, 20 tasks, repetitions,
statistics.

    python scripts/week11_experiment.py                      # oracle fixture
    python scripts/week11_experiment.py --reps 3
    python scripts/week11_experiment.py --provider anthropic  # needs a key
    python scripts/week11_experiment.py --analyse results.json

This is the script that produces the numbers the final report is written
from. It does three things:

1. runs every condition over every task, `--reps` times, recording both what
   each condition claimed and what the hidden tests measured;
2. saves the raw rows, so the analysis can be redone without re-running - and
   so a published table can be traced back to the runs behind it;
3. analyses them: success rates with intervals, the paired tests that suit
   each metric, Holm correction across the comparisons, and cost per
   *successful* task.

With no `--provider` it uses the `bench.oracle` fixture, whose answers are
known in advance. That validates the whole chain end to end and measures
nothing about any model. `--provider anthropic` or `--provider openai` points
it at a real API, which costs money: the run prints an estimate and asks for
confirmation first unless `--yes` is given.

The unit of analysis is the task, not the run. Repetitions are averaged within
a task before any test, because three runs of one task are not three
independent observations and treating them as such would shrink every p-value
by a factor it has not earned.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mawe.baselines import SelfRefine, SingleModel  # noqa: E402
from mawe.bench import TASKS, select  # noqa: E402
from mawe.bench import report as reporting  # noqa: E402
from mawe.bench.experiment import (  # noqa: E402
    Pricing,
    from_json,
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

#: Rates in dollars per million tokens. Recorded in the results file so a cost
#: column can be recomputed when they change, rather than being a number
#: nobody can trace.
PRICING = {
    "mock": Pricing(0.0, 0.0, "free (fixture)"),
    "oracle": Pricing(0.0, 0.0, "free (fixture)"),
    "anthropic": Pricing(3.0, 15.0, "$3/$15 per Mtok"),
    "openai": Pricing(2.5, 10.0, "$2.50/$10 per Mtok"),
}


def build_conditions(provider_factory, settings: Settings, database_url: str):
    """The four conditions, each as a factory producing a fresh runner."""
    ablation = Settings(**{**settings.__dict__})
    ablation.summarisation_enabled = False

    return [
        ("A", lambda: SingleModel(provider=provider_factory(),
                                  settings=settings,
                                  database_url=database_url)),
        ("B", lambda: SelfRefine(provider=provider_factory(),
                                 settings=settings,
                                 database_url=database_url)),
        ("C", lambda: Engine(provider=provider_factory(), settings=settings,
                             database_url=database_url)),
        ("C'", lambda: Engine(provider=provider_factory(),
                              settings=ablation, database_url=database_url)),
    ]


def estimate_cost(tasks, reps, cap, pricing: Pricing) -> float:
    """A rough upper bound, printed before a paid run.

    Deliberately pessimistic: it assumes every iterating condition runs to the
    cap. Under-promising here is the harmless direction to be wrong in.
    """
    calls_per_iteration = {"A": 1, "B": 2, "C": 3, "C'": 3}
    tokens_per_call = 1800          # prompt + completion, generous
    total = 0
    for label, calls in calls_per_iteration.items():
        iterations = 1 if label == "A" else cap
        total += len(tasks) * reps * calls * iterations * tokens_per_call
    # split the estimate as mostly prompt, which is how these prompts run
    return pricing.cost(int(total * 0.75), int(total * 0.25))


def confirm(message: str) -> bool:
    try:
        return input(f"{message} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="oracle",
                        choices=["oracle", "mock", "anthropic", "openai"])
    parser.add_argument("--quality", default="improving",
                        choices=["perfect", "flawed", "improving", "slow"],
                        help="oracle fixture behaviour (ignored otherwise)")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--tasks", nargs="*", default=None,
                        help="limit to these task slugs")
    parser.add_argument("--difficulty", default=None,
                        choices=["easy", "medium", "hard"])
    parser.add_argument("--out", default=None,
                        help="directory for the results files")
    parser.add_argument("--analyse", default=None,
                        help="skip the sweep and analyse this results file")
    parser.add_argument("--yes", action="store_true",
                        help="do not ask before a paid run")
    args = parser.parse_args(argv)

    # ------------------------------------------------ analysis only
    if args.analyse:
        rows = from_json(args.analyse)
        import json
        with open(args.analyse, encoding="utf-8") as handle:
            metadata = json.load(handle).get("metadata", {})
        print(reporting.render(reporting.build(rows, metadata=metadata)))
        return 0

    tasks = select(difficulty=args.difficulty, slugs=args.tasks)
    if not tasks:
        print("no tasks selected", file=sys.stderr)
        return 2

    settings = Settings(max_iterations=args.max_iterations,
                        sandbox_timeout_s=10)
    pricing = PRICING[args.provider]

    if args.provider in ("oracle",):
        def provider_factory():
            return OracleProvider(args.quality)
        provider_label = f"oracle fixture ({args.quality})"
    else:
        from mawe.llm import get_provider

        def provider_factory():
            return get_provider(args.provider)
        provider_label = args.provider

    runs = len(tasks) * args.reps * 4
    print(LINE)
    print("WEEK 11 - the Phase 4 experiment")
    print(LINE)
    print(f"  provider     : {provider_label}")
    print(f"  tasks        : {len(tasks)}")
    print(f"  repetitions  : {args.reps}")
    print(f"  iteration cap: {args.max_iterations}")
    print(f"  total runs   : {runs}  (4 conditions)")
    print(f"  pricing      : {pricing.label}")

    if args.provider in ("anthropic", "openai"):
        upper = estimate_cost(tasks, args.reps, args.max_iterations, pricing)
        print(f"\n  This calls a paid API {runs} times.")
        print(f"  Pessimistic upper bound, assuming every run hits the cap: "
              f"${upper:.2f}")
        if not args.yes and not confirm("  Proceed?"):
            print("  cancelled")
            return 1
    else:
        print(f"\n  NOTE: the {args.provider} provider is a fixture with "
              f"known answers. The numbers\n  below validate the "
              f"experiment pipeline and measure no model's ability.")

    db = make_engine("sqlite://")
    task_ids = seed(db)

    # ------------------------------------------------ the sweep
    print()
    print(LINE)
    print("running")
    print(LINE)
    all_rows = []
    started = time.time()
    for label, factory in build_conditions(provider_factory, settings,
                                           "sqlite://"):
        at = time.time()
        done = {"n": 0}

        def progress(row, label=label, done=done):
            done["n"] += 1
            if done["n"] % 10 == 0 or done["n"] == len(tasks) * args.reps:
                print(f"  {label:<3} {done['n']}/{len(tasks) * args.reps}",
                      end="\r", flush=True)

        rows = run_condition(label, factory, tasks, repetitions=args.reps,
                             pricing=pricing, task_ids=task_ids,
                             on_row=progress)
        all_rows.extend(rows)
        solved = sum(1 for r in rows if r.success)
        errors = sum(1 for r in rows if r.error)
        print(f"  {label:<3} {len(rows)} runs, {solved} successful, "
              f"{sum(r.total_tokens for r in rows):,} tokens, "
              f"{time.time() - at:.0f}s"
              + (f"  ({errors} ERRORS)" if errors else ""))
        for row in [r for r in rows if r.error][:3]:
            print(f"        {row.task}: {row.error[:100]}")

    print(f"\n  {len(all_rows)} runs in {time.time() - started:.0f}s")

    # ------------------------------------------------ save
    out_dir = Path(args.out) if args.out else ROOT / "docs" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"sweep-{args.provider}-{stamp}"
    metadata = metadata_for(settings, provider_factory(), pricing, args.reps)
    metadata["tasks"] = [t.slug for t in tasks]
    metadata["fixture_quality"] = (args.quality if args.provider == "oracle"
                                   else None)
    metadata["measures_a_model"] = args.provider in ("anthropic", "openai")

    json_path = to_json(all_rows, out_dir / f"{name}.json", metadata)
    csv_path = to_csv(all_rows, out_dir / f"{name}.csv")
    print(f"  saved {json_path}")
    print(f"  saved {csv_path}")

    # ------------------------------------------------ analyse
    print()
    print(reporting.render(reporting.build(all_rows, metadata=metadata)))

    if not metadata["measures_a_model"]:
        print("  REMINDER: these numbers come from a fixture with known "
              "answers. They show the\n  experiment works; they say nothing "
              "about any model's ability.")
        print(LINE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
