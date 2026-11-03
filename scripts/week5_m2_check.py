"""Week 5 milestone (M2): the full PM -> Developer -> Reviewer pipeline.

    python scripts/week5_m2_check.py

Demonstrates the property that makes the Reviewer a real QA gate: its verdict
is grounded in executing the program, so it cannot approve code that fails an
acceptance check and cannot block the loop over style once every check passes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mawe.agents.reviewer import ReviewerAgent  # noqa: E402
from mawe.config import Settings  # noqa: E402
from mawe.graph import run_workflow  # noqa: E402
from mawe.llm import MockProvider  # noqa: E402
from mawe.sample_code import (  # noqa: E402
    TEMPERATURE_MAIN,
    TEMPERATURE_MAIN_UNROUNDED,
    TEMPERATURE_SPEC,
    temperature_repair_script,
)

SETTINGS = Settings(max_iterations=5, sandbox_timeout_s=15)
LINE = "-" * 100


def banner(text):
    print("=" * 100)
    print(text)
    print("=" * 100)


def state_for(code):
    return {
        "spec": json.dumps(TEMPERATURE_SPEC),
        "spec_json": TEMPERATURE_SPEC,
        "acceptance_criteria": TEMPERATURE_SPEC["acceptance_criteria"],
        "language": "python",
        "files": [{"path": "src/main.py", "language": "python",
                   "content": code}],
        "warnings": [],
    }


def always_approves():
    return {"reviewer": [json.dumps(
        {"verdict": "approve", "severity": "minor", "issues": [],
         "tests_passed": 3, "tests_failed": 0})]}


def always_rejects():
    return {"reviewer": [json.dumps(
        {"verdict": "reject", "severity": "major",
         "issues": ["I would prefer different variable names"],
         "tests_passed": 0, "tests_failed": 3})]}


def part_one():
    banner("PART 1 - the Reviewer's verdict comes from running the program")
    print("The model is scripted to ALWAYS approve. The sandbox decides.\n")
    print(f"{'code under review':<34}{'model said':<14}{'checks':<12}"
          f"{'final verdict':<16}{'severity':<10}")
    print(LINE)

    rows = []
    for label, code in [("v1 - forgets to round", TEMPERATURE_MAIN_UNROUNDED),
                        ("v2 - correct", TEMPERATURE_MAIN)]:
        update = ReviewerAgent(MockProvider(always_approves()),
                               SETTINGS).run(state_for(code))
        checks = f"{update['tests_passed']}/{update['tests_passed'] + update['tests_failed']}"
        print(f"{label:<34}{'approve':<14}{checks:<12}"
              f"{update['verdict']:<16}{str(update['severity']):<10}")
        rows.append((label, update))

    print()
    for label, update in rows:
        if update["verdict"] == "reject":
            print(f"  {label}: {update['issues'][0].splitlines()[0]}")
    overridden = any(u["verdict"] == "reject" for _, u in rows)
    print(f"\n  false approval prevented: {'YES' if overridden else 'NO'}")
    return overridden


def part_two():
    banner("PART 2 - a reviewer that nitpicks cannot stall the loop")
    print("The model is scripted to ALWAYS reject with 'major', on correct code.\n")
    update = ReviewerAgent(MockProvider(always_rejects()),
                           SETTINGS).run(state_for(TEMPERATURE_MAIN))
    print("  model said        : reject / major")
    print(f"  checks            : {update['tests_passed']} passed, "
          f"{update['tests_failed']} failed")
    print(f"  severity after    : {update['severity']}")
    print(f"  blocks the loop   : "
          f"{'yes' if update['severity'] in ('critical', 'major') else 'no'}")
    for w in update["warnings"]:
        print(f"  note              : {w}")
    ok = update["severity"] == "minor"
    print(f"\n  trivia-rejection loop prevented: {'YES' if ok else 'NO'}")
    return ok


def part_three():
    banner("PART 3 - M2: the full three-role pipeline, end to end")
    events = []

    def on_event(kind, payload):
        events.append((kind, payload))

    state = run_workflow("Build a command-line temperature converter",
                         MockProvider(temperature_repair_script()),
                         settings=SETTINGS, on_event=on_event)

    print(f"{'step':<12}{'detail'}")
    print(LINE)
    for kind, payload in events:
        if kind == "plan":
            print(f"{'plan':<12}specification with "
                  f"{len(payload.get('acceptance_criteria', []))} criteria and "
                  f"{len(TEMPERATURE_SPEC['checks'])} executable checks")
        elif kind == "develop":
            print(f"{'develop':<12}iteration {payload.get('iteration')}: "
                  f"{', '.join(f['path'] for f in payload.get('files', []))}")
        elif kind == "review":
            print(f"{'review':<12}{payload.get('verdict')} / "
                  f"{payload.get('severity')}  "
                  f"({payload.get('tests_passed')} checks passed, "
                  f"{payload.get('tests_failed')} failed)")
        elif kind == "finalize":
            print(f"{'finalize':<12}{payload.get('termination_reason')}")

    print(LINE)
    print(f"  status            : {state['status']}")
    print(f"  iterations        : {state['iteration']}")
    print(f"  final checks      : {state.get('tests_passed')} passed, "
          f"{state.get('tests_failed')} failed")
    ok = (state["status"] == "approved" and state["iteration"] == 2
          and state.get("tests_failed") == 0)
    print(f"\n  M2 {'MET' if ok else 'NOT MET'} - the pipeline rejected a real "
          f"defect, the Developer fixed it, and approval required passing "
          f"every check.")
    return ok


def main() -> int:
    results = [part_one(), part_two(), part_three()]
    print()
    banner("WEEK 5 SUMMARY")
    print(f"  Reviewer cannot approve failing code      : "
          f"{'PASS' if results[0] else 'FAIL'}")
    print(f"  Reviewer cannot block on trivia           : "
          f"{'PASS' if results[1] else 'FAIL'}")
    print(f"  M2 three-role pipeline end to end         : "
          f"{'PASS' if results[2] else 'FAIL'}")
    print("=" * 100)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
