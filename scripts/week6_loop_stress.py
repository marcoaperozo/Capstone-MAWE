"""Week 6 milestone: the loop always terminates under stress.

    python scripts/week6_loop_stress.py [runs]

Part 1 shows each detector firing on a scenario built to trigger it.
Part 2 drives tens of thousands of randomised adversarial review sequences
through the policy and reports the distribution of exit reasons and the worst
iteration count observed. The claim being tested is not "it usually stops" but
"no reachable sequence exceeds the cap".
"""

from __future__ import annotations

import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mawe.config import Settings  # noqa: E402
from mawe.graph import run_workflow  # noqa: E402
from mawe.graph.policy import LoopPolicy, issue_signature  # noqa: E402
from mawe.llm import (  # noqa: E402
    MockProvider,
    oscillating_developer_script,
    picky_reviewer_script,
    stuck_developer_script,
    varied_reviewer_script,
)

SETTINGS = Settings(max_iterations=5, sandbox_timeout_s=0)
POLICY = LoopPolicy()
LINE = "-" * 96


def part_one() -> bool:
    print("=" * 96)
    print("PART 1 - each termination mechanism, on a scenario built to trigger it")
    print("=" * 96)
    print(f"{'adversarial scenario':<30}{'iters':>7}{'exit reason':>18}"
          f"   {'mechanism'}")
    print(LINE)

    cases = [
        ("developer repeats itself", stuck_developer_script(),
         "no_progress", "SHA-256 of the generated files"),
        ("same complaint every round", picky_reviewer_script(),
         "repeated_issues", "normalised issue fingerprint"),
        ("developer flip-flops", oscillating_developer_script(),
         "oscillation", "hash seen earlier in the run"),
        ("everything always different", varied_reviewer_script(),
         "iteration_cap", "hard ceiling"),
    ]

    ok = True
    for label, script, expected, mechanism in cases:
        state = run_workflow("stress", MockProvider(script), settings=SETTINGS)
        actual = state["termination_reason"]
        ok &= actual == expected
        flag = "" if actual == expected else f"  <- expected {expected}"
        print(f"{label:<30}{state['iteration']:>7}{actual:>18}"
              f"   {mechanism}{flag}")

    print(LINE)
    print(f"  all four mechanisms fire as designed: {'YES' if ok else 'NO'}")
    return ok


def simulate(rng: random.Random, policy: LoopPolicy, limit: int = 500):
    s = {"iteration": 0, "max_iterations": policy.max_iterations,
         "seen_hashes": [], "issue_history": [], "errors": []}
    for step in range(1, limit + 1):
        s["iteration"] = step
        mode = rng.choice(["new", "repeat", "cycle"])
        if mode == "repeat" and s["seen_hashes"]:
            digest = s["seen_hashes"][-1]
        elif mode == "cycle" and s["seen_hashes"]:
            digest = rng.choice(s["seen_hashes"])
        else:
            digest = f"h{rng.randrange(10_000)}"
        s["seen_hashes"] = s["seen_hashes"] + [digest]
        s["code_hash"] = digest
        s["verdict"] = rng.choices(["reject", "approve"], weights=[95, 5])[0]
        s["severity"] = rng.choice(["critical", "major", "minor", None])
        issues = [f"criterion {rng.randrange(1, 4)} fails"
                  for _ in range(rng.randrange(0, 3))]
        s["issue_history"] = s["issue_history"] + [issue_signature(issues)]
        if rng.random() < 0.01:
            s["errors"] = ["random agent failure"]
        decision = policy.decide(s)
        if decision.terminal:
            return step, decision.reason
    return limit + 1, "DID_NOT_TERMINATE"


def part_two(runs: int) -> bool:
    print()
    print("=" * 96)
    print(f"PART 2 - {runs:,} randomised adversarial sequences")
    print("=" * 96)

    configs = [
        ("default policy, cap 5", LoopPolicy(max_iterations=5)),
        ("cap 1", LoopPolicy(max_iterations=1)),
        ("cap 20", LoopPolicy(max_iterations=20)),
        ("all detectors off, cap 5",
         LoopPolicy(max_iterations=5, detect_no_progress=False,
                    detect_oscillation=False, detect_repeated_issues=False)),
    ]

    print(f"{'configuration':<30}{'runs':>9}{'terminated':>12}"
          f"{'worst iters':>13}{'cap':>6}{'mean':>8}")
    print(LINE)

    ok = True
    distributions = {}
    for label, policy in configs:
        rng = random.Random(20261101)
        counter = Counter()
        worst = 0
        total = 0
        for _ in range(runs):
            steps, reason = simulate(rng, policy)
            counter[reason] += 1
            worst = max(worst, steps)
            total += steps
        terminated = runs - counter["DID_NOT_TERMINATE"]
        within = worst <= policy.max_iterations
        ok &= (terminated == runs) and within
        distributions[label] = counter
        print(f"{label:<30}{runs:>9,}{terminated:>12,}{worst:>13}"
              f"{policy.max_iterations:>6}{total / runs:>8.2f}"
              f"{'' if within else '   <- EXCEEDED CAP'}")

    print(LINE)
    print("exit-reason distribution (default policy):")
    counter = distributions["default policy, cap 5"]
    for reason, count in counter.most_common():
        bar = "#" * int(48 * count / runs)
        print(f"  {reason:<18}{count:>8,}  {100 * count / runs:>5.1f}%  {bar}")

    print(LINE)
    print(f"  runs that failed to terminate: "
          f"{sum(c['DID_NOT_TERMINATE'] for c in distributions.values())}")
    print(f"  runs that exceeded their cap : {'0' if ok else 'SEE ABOVE'}")
    return ok


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 25_000
    started = time.time()
    results = [part_one(), part_two(runs)]
    print()
    print("=" * 96)
    print("WEEK 6 MILESTONE - loop always terminates on stress tests")
    print("=" * 96)
    print(f"  mechanisms fire correctly        : "
          f"{'PASS' if results[0] else 'FAIL'}")
    print(f"  no randomised run exceeds its cap: "
          f"{'PASS' if results[1] else 'FAIL'}")
    print(f"  elapsed                          : {time.time() - started:.2f}s")
    print(f"\n  M-W6 {'MET' if all(results) else 'NOT MET'}")
    print("=" * 96)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
