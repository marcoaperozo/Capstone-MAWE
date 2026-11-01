"""Week 7 milestone: long runs stay inside the token budget.

    python scripts/week7_memory_check.py

Part 1 shows how context grows with run length, with compression on and off.
Part 2 runs the engine end to end under both settings - this is the ablation
the Phase 4 evaluation calls condition C'.

The hypothesis under test is H5 from the proposal: summarisation reduces
context tokens by at least 40% without losing information the Developer needs.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mawe.config import Settings  # noqa: E402
from mawe.graph import run_workflow  # noqa: E402
from mawe.llm import MockProvider, varied_reviewer_script  # noqa: E402
from mawe.memory import IterationRecord, MemoryManager  # noqa: E402

BUDGET = 4000
LINE = "-" * 96
TARGET_REDUCTION = 0.40


def synthetic_files(n_lines=60, path="src/main.py"):
    body = "\n".join(f"    line {i} of a generated implementation"
                     for i in range(n_lines))
    return [{"path": path, "language": "python", "content": body}]


def synthetic_history(n, n_lines=60):
    return [
        IterationRecord(
            iteration=i,
            code_hash=f"{i:064x}",
            files=["src/main.py"],
            total_lines=n_lines,
            file_bodies=synthetic_files(n_lines),
            verdict="reject",
            severity="major",
            issues=[f"criterion {1 + (i % 4)} fails on input {i}"],
            tests_passed=3,
            tests_failed=1,
        )
        for i in range(1, n + 1)
    ]


def part_one() -> bool:
    print("=" * 96)
    print("PART 1 - context size as a run gets longer")
    print("=" * 96)
    print(f"budget {BUDGET:,} tokens, latest iteration always kept in full\n")
    print(f"{'iterations':>11}{'uncompressed':>15}{'compressed':>13}"
          f"{'reduction':>11}{'over budget?':>15}")
    print(LINE)

    off = MemoryManager(enabled=False, token_budget=BUDGET)
    on = MemoryManager(enabled=True, token_budget=BUDGET)

    rows = []
    for n in (1, 2, 3, 5, 10, 20, 40, 80):
        history = synthetic_history(n)
        latest = synthetic_files()
        _s_off, stats_off = off.build_history(history, latest)
        _s_on, stats_on = on.build_history(history, latest)
        over = "YES" if stats_on.tokens_compressed > BUDGET else "no"
        print(f"{n:>11}{stats_off.tokens_uncompressed:>15,}"
              f"{stats_on.tokens_compressed:>13,}"
              f"{stats_on.reduction * 100:>10.1f}%{over:>15}")
        rows.append((n, stats_off.tokens_uncompressed,
                     stats_on.tokens_compressed, stats_on.reduction))

    print(LINE)
    worst = max(r[2] for r in rows)
    naive_at_80 = rows[-1][1]
    bounded = worst <= BUDGET
    print(f"  uncompressed at 80 iterations : {naive_at_80:,} tokens")
    print(f"  compressed  at 80 iterations  : {rows[-1][2]:,} tokens "
          f"({rows[-1][3] * 100:.1f}% smaller)")
    print(f"  largest context ever sent     : {worst:,} tokens "
          f"(budget {BUDGET:,})")
    print(f"\n  context stays within budget   : {'YES' if bounded else 'NO'}")
    return bounded


def part_two() -> bool:
    print()
    print("=" * 96)
    print("PART 2 - end-to-end ablation (Phase 4 condition C')")
    print("=" * 96)
    print(f"{'condition':<34}{'iterations':>12}{'context sent':>15}"
          f"{'reduction':>12}{'outcome':>14}")
    print(LINE)

    results = {}
    for label, enabled in (("C  - summarisation enabled", True),
                           ("C' - summarisation disabled", False)):
        settings = Settings(max_iterations=8, sandbox_timeout_s=0)
        settings.context_token_budget = BUDGET
        settings.summarisation_enabled = enabled
        state = run_workflow("Build a terminal snake game",
                             MockProvider(varied_reviewer_script(12)),
                             settings=settings)
        before = state["context_tokens_before"]
        after = state["context_tokens_after"]
        reduction = (1 - after / before) if before else 0.0
        results[enabled] = (state, before, after, reduction)
        print(f"{label:<34}{state['iteration']:>12}{after:>15,}"
              f"{reduction * 100:>11.1f}%{state['termination_reason']:>14}")

    print(LINE)
    on_state, _b, on_after, on_reduction = results[True]
    off_state, _b2, off_after, _r2 = results[False]

    same_outcome = (on_state["termination_reason"]
                    == off_state["termination_reason"]
                    and on_state["iteration"] == off_state["iteration"])

    print(f"  tokens sent, compression off  : {off_after:,}")
    print(f"  tokens sent, compression on   : {on_after:,}")
    print(f"  reduction                     : {on_reduction * 100:.1f}% "
          f"(H5 target: {TARGET_REDUCTION * 100:.0f}%)")
    print(f"  same termination and iteration count under both: "
          f"{'YES' if same_outcome else 'NO'}")

    ok = on_reduction >= TARGET_REDUCTION and same_outcome
    print(f"\n  H5 supported on the mock harness: {'YES' if ok else 'NO'}")
    print("  (a real-model confirmation of 'no quality drop' is Phase 4 work;")
    print("   this shows the mechanism works and costs what we claim)")
    return ok


def main() -> int:
    results = [part_one(), part_two()]
    print()
    print("=" * 96)
    print("WEEK 7 MILESTONE - long runs stay under the token budget")
    print("=" * 96)
    print(f"  context bounded as iterations grow : "
          f"{'PASS' if results[0] else 'FAIL'}")
    print(f"  >= 40% reduction, outcome unchanged: "
          f"{'PASS' if results[1] else 'FAIL'}")
    print(f"\n  M-W7 {'MET' if all(results) else 'NOT MET'}")
    print("=" * 96)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
