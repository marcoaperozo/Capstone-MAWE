"""Week 12 milestone (M4) - the final gate, and the source of the report's
numbers.

    python scripts/week12_final_check.py [--quick] [--no-write]

This script does two jobs that are deliberately the same job.

It is the **M4 gate**: everything built across twelve weeks still works, and
each hypothesis gets a verdict - supported, unsupported, or not yet testable -
against a measurement rather than an opinion.

It is also the **single source of the report's figures**. Every number it
computes is written to `docs/reports/findings.json`, and the final report and
deck are generated from that file rather than typed from a terminal. This is
not tidiness. Earlier in the project a progress deck claimed 273 passing tests
when the suite had 255, because the figure was copied by hand and the suite
moved underneath it. A report whose numbers are generated cannot drift from
the code it describes; one whose numbers are typed will.

`--quick` skips the mutation sweep and the 100,000-run stress test, which are
the slow parts. The written figures then carry `"quick": true` so nothing
downstream mistakes a partial run for a full one.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mawe import __version__  # noqa: E402
from mawe.bench import TASKS, composition, score  # noqa: E402
from mawe.bench import mutation, report as reporting  # noqa: E402
from mawe.bench.experiment import from_json  # noqa: E402
from mawe.bench.oracle import OracleProvider  # noqa: E402
from mawe.bench.solutions import (  # noqa: E402
    degenerate_files_for,
    files_for,
)
from mawe.config import Settings  # noqa: E402
from mawe.engine import Engine  # noqa: E402
from mawe.graph.policy import LoopPolicy, issue_signature  # noqa: E402
from mawe.memory import MemoryManager  # noqa: E402

LINE = "=" * 96
FINDINGS = ROOT / "docs" / "reports" / "findings.json"
SWEEP = ROOT / "docs" / "results" / "fixture-sweep.json"
STRESS_RUNS = 25_000          # per configuration; 4 configurations

results = []
findings: dict = {}


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


# =========================================================== 1 the engine
def engine_still_works():
    section("1 - the engine built in weeks 1-8 still runs end to end")
    settings = Settings(max_iterations=5, sandbox_timeout_s=10)
    task = TASKS[0]
    engine = Engine(provider=OracleProvider("improving"), settings=settings,
                    database_url="sqlite://")
    result = engine.run(task.prompt, language=task.language)

    check("a full run reaches approval", result.approved,
          f"{result.iterations} iteration(s), {result.total_tokens:,} tokens")
    measured = score(result.files, task)
    check("the delivered code passes the task's hidden tests",
          measured.success,
          f"{measured.tests_passed}/{measured.total}")
    findings["engine_version"] = __version__


def test_suite():
    section("2 - the test suite")
    try:
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=ROOT, capture_output=True, text=True, timeout=600)
    except (subprocess.SubprocessError, OSError) as exc:
        check("the suite can be collected", False, str(exc))
        return

    per_module = {}
    for raw in (done.stdout or "").replace("\r", "").splitlines():
        if raw.startswith("tests/") and ": " in raw:
            name, _, count = raw.partition(": ")
            if count.strip().isdigit():
                per_module[name] = int(count.strip())

    total = sum(per_module.values())
    check("tests are collected", total > 0, f"{total} tests in "
          f"{len(per_module)} modules")
    findings["tests"] = {"total": total, "modules": len(per_module),
                         "per_module": per_module}
    for name, count in sorted(per_module.items()):
        print(f"         {name:<34}{count:>5}")


# =========================================================== 3 benchmark
def benchmark_validity(quick: bool):
    section("3 - the benchmark is a valid instrument (H-bench)")
    counts = composition()
    check("20 tasks, 7/8/5 by difficulty",
          counts["tasks"] == 20
          and (counts["easy"], counts["medium"], counts["hard"]) == (7, 8, 5),
          f"{counts['tasks']} tasks, {counts['tests']} hidden tests")

    solvable, total_tests = 0, 0
    for task in TASKS:
        measured = score(files_for(task.slug), task)
        if measured.skipped:
            continue
        total_tests += measured.total
        solvable += 1 if measured.success else 0
    check("every reference solution passes every hidden test",
          solvable == len(TASKS),
          f"{solvable}/{len(TASKS)} tasks, {total_tests} tests")

    stub_tasks, stub_passed, stub_total = 0, 0, 0
    for task in TASKS:
        measured = score(degenerate_files_for(task.slug), task)
        if measured.skipped:
            continue
        stub_tasks += 1 if measured.success else 0
        stub_passed += measured.tests_passed
        stub_total += measured.total
    check("a do-nothing program solves nothing", stub_tasks == 0,
          f"{stub_passed}/{stub_total} individual tests "
          f"({stub_passed / stub_total * 100:.1f}%) - the empty-input cases")

    mutation_score = None
    if quick:
        print("  (mutation sweep skipped: --quick)")
    else:
        rows = mutation.run_all(TASKS, limit=10)
        overall = mutation.overall(rows)
        mutation_score = overall["mutation_score"]
        unmeasured = [r.task.slug for r in rows if r.total == 0]
        check("injected defects are caught", mutation_score >= 0.80,
              f"mutation score {mutation_score * 100:.1f}% "
              f"({int(overall['killed'])}/{int(overall['mutants'])})")
        check("every task was mutated", not unmeasured,
              "all tasks" if not unmeasured else str(unmeasured))

    findings["benchmark"] = {
        "tasks": counts["tasks"],
        "hidden_tests": counts["tests"],
        "easy": counts["easy"], "medium": counts["medium"],
        "hard": counts["hard"],
        "python": counts["python"], "javascript": counts["javascript"],
        "references_passing": solvable,
        "stub_tasks_solved": stub_tasks,
        "stub_tests_passed": stub_passed,
        "stub_tests_total": stub_total,
        "mutation_score": mutation_score,
    }


# =========================================================== 4 H4
def termination(quick: bool):
    section("4 - H4: every run terminates, and inside its cap")

    def simulate(rng, policy, limit=500):
        state = {"iteration": 0, "max_iterations": policy.max_iterations,
                 "seen_hashes": [], "issue_history": [], "errors": []}
        for step in range(1, limit + 1):
            state["iteration"] = step
            mode = rng.choice(["new", "repeat", "cycle"])
            if mode == "repeat" and state["seen_hashes"]:
                digest = state["seen_hashes"][-1]
            elif mode == "cycle" and state["seen_hashes"]:
                digest = rng.choice(state["seen_hashes"])
            else:
                digest = f"h{rng.randrange(10_000)}"
            state["seen_hashes"] = state["seen_hashes"] + [digest]
            state["code_hash"] = digest
            state["verdict"] = rng.choices(["reject", "approve"],
                                           weights=[95, 5])[0]
            state["severity"] = rng.choice(["critical", "major", "minor",
                                            None])
            issues = [f"criterion {rng.randrange(1, 4)} fails"
                      for _ in range(rng.randrange(0, 3))]
            state["issue_history"] = state["issue_history"] + [
                issue_signature(issues)]
            if rng.random() < 0.01:
                state["errors"] = ["random agent failure"]
            decision = policy.decide(state)
            if decision.terminal:
                return step, decision.reason
        return limit + 1, "DID_NOT_TERMINATE"

    runs = 2_000 if quick else STRESS_RUNS
    configs = [
        ("default, cap 5", LoopPolicy(max_iterations=5)),
        ("cap 1", LoopPolicy(max_iterations=1)),
        ("cap 20", LoopPolicy(max_iterations=20)),
        ("detectors off, cap 5",
         LoopPolicy(max_iterations=5, detect_no_progress=False,
                    detect_oscillation=False, detect_repeated_issues=False)),
    ]

    print(f"  {'configuration':<26}{'runs':>9}{'terminated':>12}"
          f"{'worst':>8}{'cap':>6}")
    print("  " + "-" * 62)
    failures = 0
    over_cap = 0
    total_runs = 0
    cap_exits = 0
    default_counter = Counter()
    per_config = {}
    for label, policy in configs:
        rng = random.Random(20261101)
        counter = Counter()
        worst = 0
        for _ in range(runs):
            steps, reason = simulate(rng, policy)
            counter[reason] += 1
            worst = max(worst, steps)
        failures += counter["DID_NOT_TERMINATE"]
        over_cap += 0 if worst <= policy.max_iterations else 1
        total_runs += runs
        cap_exits += counter["iteration_cap"]
        per_config[label] = {
            "runs": runs,
            "cap_share": counter["iteration_cap"] / runs,
            "worst": worst,
            "cap": policy.max_iterations,
        }
        if label == "default, cap 5":
            default_counter = counter
        print(f"  {label:<26}{runs:>9,}"
              f"{runs - counter['DID_NOT_TERMINATE']:>12,}{worst:>8}"
              f"{policy.max_iterations:>6}"
              f"   cap exits {counter['iteration_cap'] / runs * 100:5.1f}%")

    check("every randomised run terminates", failures == 0,
          f"{total_runs:,} runs, {failures} non-terminating")
    check("no run exceeds its cap", over_cap == 0,
          f"{len(configs)} configurations")

    cap_share = cap_exits / total_runs
    print()
    print("  exit reasons under the default policy:")
    for reason, count in default_counter.most_common():
        print(f"    {reason:<18}{count:>8,}  {count / runs * 100:>5.1f}%")

    findings["termination"] = {
        "runs": total_runs,
        "non_terminating": failures,
        "over_cap": over_cap,
        # averaged over every configuration, including one with the
        # detectors disabled and one with a cap of 1, where the cap is
        # *supposed* to be what stops the run
        "cap_exit_share": cap_share,
        "default_cap_share": per_config["default, cap 5"]["cap_share"],
        "per_configuration": per_config,
        "configurations": len(configs),
        "default_distribution": dict(default_counter),
    }


# =========================================================== 5 H5
def compression():
    section("5 - H5: context stays bounded, and the outcome does not change")
    budget = 4000
    manager = MemoryManager(token_budget=budget, keep_full=1, enabled=True)
    naive = MemoryManager(token_budget=budget, keep_full=1, enabled=False)

    from mawe.memory import IterationRecord

    # Byte-identical to the fixture in scripts/week7_memory_check.py. Two
    # scripts measuring the same mechanism with slightly different synthetic
    # input would report two different reductions for it, and the project
    # would then quote whichever one the reader happened to find.
    body = "\n".join(f"    line {i} of a generated implementation"
                     for i in range(60))
    files = [{"path": "src/main.py", "language": "python", "content": body}]

    def history(n):
        return [IterationRecord(
            iteration=i, code_hash=f"{i:064x}", files=["src/main.py"],
            total_lines=60, file_bodies=files, verdict="reject",
            severity="major",
            issues=[f"criterion {1 + (i % 4)} fails on input {i}"],
            tests_passed=3, tests_failed=1) for i in range(1, n + 1)]

    print(f"  {'iterations':>11}{'uncompressed':>15}{'compressed':>13}"
          f"{'reduction':>12}{'over budget':>14}")
    print("  " + "-" * 65)
    ladder = {}
    worst_sent = 0
    for n in (1, 2, 5, 10, 20, 40, 80):
        _, stats_on = manager.build_history(history(n), files)
        _, stats_off = naive.build_history(history(n), files)
        reduction = (1 - stats_on.tokens_compressed /
                     stats_off.tokens_uncompressed) \
            if stats_off.tokens_uncompressed else 0.0
        worst_sent = max(worst_sent, stats_on.tokens_compressed)
        ladder[n] = {"uncompressed": stats_off.tokens_uncompressed,
                     "compressed": stats_on.tokens_compressed,
                     "reduction": reduction}
        print(f"  {n:>11}{stats_off.tokens_uncompressed:>15,}"
              f"{stats_on.tokens_compressed:>13,}{reduction * 100:>11.1f}%"
              f"{('no' if stats_on.tokens_compressed <= budget else 'YES'):>14}")

    best = ladder[80]["reduction"]
    check("reduction meets the 40% target at scale", best >= 0.40,
          f"{best * 100:.1f}% at 80 iterations")
    check("the context never exceeds the budget", worst_sent <= budget,
          f"largest context sent: {worst_sent:,} of {budget:,}")

    findings["compression"] = {"budget": budget, "ladder": ladder,
                               "best_reduction": best,
                               "largest_context": worst_sent}


# =========================================================== 6 the sweep
def comparison():
    section("6 - the four-condition comparison")
    if not SWEEP.exists():
        check("a saved sweep is available", False, f"{SWEEP} is missing")
        return

    rows = from_json(SWEEP)
    with open(SWEEP, encoding="utf-8") as handle:
        metadata = json.load(handle).get("metadata", {})
    built = reporting.build(rows, metadata=metadata)

    measures_model = bool(metadata.get("measures_a_model"))
    print(f"  source     : {SWEEP.name}")
    print(f"  provider   : {metadata.get('provider')} / "
          f"{metadata.get('model')}")
    print(f"  measures a model: {'yes' if measures_model else 'NO (fixture)'}")
    print()
    print(f"  {'condition':<30}{'solved':>10}{'pass rate':>12}"
          f"{'tokens':>12}")
    print("  " + "-" * 64)

    per_condition = {}
    for label in ("A", "B", "C", "C'"):
        item = built.conditions.get(label)
        if item is None:
            continue
        print(f"  {label + ' ' + item.name:<30}"
              f"{f'{item.solved}/{item.tasks}':>10}"
              f"{item.pass_rate.value * 100:>11.1f}%"
              f"{item.tokens.value:>12,.0f}")
        per_condition[label] = {
            "solved": item.solved, "tasks": item.tasks,
            "success_rate": item.success_rate.value,
            "success_ci": [item.success_rate.low, item.success_rate.high],
            "pass_rate": item.pass_rate.value,
            "tokens": item.tokens.value,
            "iterations": item.iterations.value,
            "cost_per_success": item.cost_per_success,
            "unstable_tasks": item.unstable_tasks,
        }

    check("every condition ran on every task",
          all(v["tasks"] == 20 for v in per_condition.values())
          and len(per_condition) == 4,
          f"{len(per_condition)} conditions x 20 tasks")
    check("no condition errored",
          all(item.errors == 0 for item in built.conditions.values()),
          "all runs completed")

    comparisons = []
    for item in built.success_comparisons:
        comparisons.append({
            "left": item.left, "right": item.right, "metric": "success",
            "n": item.test.n, "p": item.test.p_value,
            "p_adjusted": item.adjusted_p, "reject": item.reject,
            "effect": item.effect, "effect_label": item.effect_label,
            "detail": item.test.detail,
        })

    findings["comparison"] = {
        "source": SWEEP.name,
        "measures_a_model": measures_model,
        "provider": metadata.get("provider"),
        "model": metadata.get("model"),
        "repetitions": built.repetitions,
        "conditions": per_condition,
        "success_comparisons": comparisons,
    }


# =========================================================== 7 scorecard
HYPOTHESES = {
    "H1": "role separation produces more correct software than one model",
    "H2": "role separation produces better specification coverage",
    "H3": "the improvement is worth its cost per successful task",
    "H4": "every run terminates, and under 10% exit by hitting the cap",
    "H5": "summarisation cuts context by >=40% without changing outcomes",
}


def scorecard():
    section("7 - the hypothesis scorecard")
    verdicts = {}

    # H4 - answered by the stress test, which needs no model
    stress = findings.get("termination", {})
    h4_terminates = stress.get("non_terminating") == 0 and \
        stress.get("over_cap") == 0
    verdicts["H4"] = {
        "verdict": "supported" if h4_terminates else "unsupported",
        "evidence": (f"{stress.get('runs', 0):,} randomised adversarial "
                     f"sequences, {stress.get('non_terminating')} failed to "
                     f"terminate, {stress.get('over_cap')} exceeded a cap"),
        "caveat": (
            "the <10% cap-exit clause is about real runs. Under the default "
            f"policy the cap accounts for "
            f"{stress.get('default_cap_share', 0) * 100:.1f}% of exits "
            f"because the detectors catch runs earlier, which is consistent "
            f"with the clause; but adversarial random input is not a model, "
            f"so the clause is not settled by this"),
        "needs_a_model": False,
    }

    # H5 - answered, and the ablation confirms the outcome is unchanged
    comp = findings.get("compression", {})
    sweep = findings.get("comparison", {}).get("conditions", {})
    same_outcome = ("C" in sweep and "C'" in sweep
                    and sweep["C"]["solved"] == sweep["C'"]["solved"])
    h5 = comp.get("best_reduction", 0) >= 0.40 and same_outcome
    verdicts["H5"] = {
        "verdict": "supported" if h5 else "unsupported",
        "evidence": (f"{comp.get('best_reduction', 0) * 100:.1f}% reduction "
                     f"at 80 iterations, never over budget; C and C' solve "
                     f"the same tasks"),
        "caveat": ("the reduction is measured on the engine's own prompts, "
                   "which is where it applies; 'no pass-rate drop' is "
                   "confirmed against the fixture, not against a model"),
        "needs_a_model": False,
    }

    # H1, H2, H3 - the instrument is ready; the measurement is not
    measures_model = findings.get("comparison", {}).get("measures_a_model")
    for key in ("H1", "H2", "H3"):
        verdicts[key] = {
            "verdict": "measured" if measures_model else "not yet testable",
            "evidence": ("the comparison runs, and detects a quality "
                         "difference it was built to detect; no sweep "
                         "against a real model has been run"),
            "caveat": ("needs an API key: the committed sweep is a fixture "
                       "with known answers and measures the apparatus, not "
                       "a model"),
            "needs_a_model": True,
        }
    # H2 has a second, independent gap worth naming
    verdicts["H2"]["caveat"] += ("; specification coverage also has no "
                                 "metric yet - the benchmark scores "
                                 "behaviour, not whether a spec was complete")

    for key in ("H1", "H2", "H3", "H4", "H5"):
        item = verdicts[key]
        mark = {"supported": "SUPPORTED", "unsupported": "UNSUPPORTED",
                "measured": "MEASURED",
                "not yet testable": "NOT YET TESTABLE"}[item["verdict"]]
        print(f"  {key}  {mark:<18}{HYPOTHESES[key]}")
        print(f"        evidence: {item['evidence']}")
        if item["caveat"]:
            print(f"        caveat  : {item['caveat']}")
        print()

    answered = sum(1 for v in verdicts.values()
                   if v["verdict"] in ("supported", "measured"))
    check("the hypotheses that need no model are answered",
          verdicts["H4"]["verdict"] == "supported"
          and verdicts["H5"]["verdict"] == "supported",
          "H4 and H5 supported by measurement")
    check("the hypotheses that need a model say so plainly",
          all(verdicts[k]["needs_a_model"] for k in ("H1", "H2", "H3")),
          "H1, H2 and H3 are labelled not yet testable")

    findings["hypotheses"] = verdicts
    findings["answered"] = answered


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    started = time.time()
    print(LINE)
    print(f"WEEK 12 MILESTONE (M4) - final check, engine v{__version__}")
    print(LINE)
    if args.quick:
        print("  --quick: the mutation sweep and the full stress test are "
              "reduced.")

    engine_still_works()
    test_suite()
    benchmark_validity(args.quick)
    termination(args.quick)
    compression()
    comparison()
    scorecard()

    findings["quick"] = args.quick
    findings["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    findings["elapsed_s"] = round(time.time() - started, 1)

    if not args.no_write:
        FINDINGS.parent.mkdir(parents=True, exist_ok=True)
        FINDINGS.write_text(json.dumps(findings, indent=2), encoding="utf-8")
        print(f"\n  figures written to {FINDINGS.relative_to(ROOT)}")
        if args.quick:
            print("  (marked quick: true, so a partial run cannot be "
                  "mistaken for a full one)")

    passed, total = sum(results), len(results)
    print()
    print(LINE)
    print(f"  {passed}/{total} checks passed in {time.time() - started:.0f}s")
    print(f"\n  M4 {'MET' if passed == total else 'NOT MET'} - the system "
          f"works, the instrument is validated, and\n  each hypothesis has a "
          f"verdict backed by a measurement or an honest gap.")
    print(LINE)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
