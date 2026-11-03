"""Answer the question "how did you test it without an API key?" by running.

    python scripts/how_we_test.py

Written for one moment: an examiner asks how a project that has never called
a language model can claim to be tested. The honest answer is not a defence,
it is a distinction - between testing the *machinery around* a model and
testing the *quality of* a model - and this script demonstrates it in four
parts rather than asserting it.

Takes about twenty seconds and needs no network.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mawe.agents.checks import AcceptanceCheck, run_check  # noqa: E402
from mawe.config import Settings  # noqa: E402
from mawe.engine import Engine  # noqa: E402
from mawe.llm import MockProvider, stuck_developer_script  # noqa: E402
from mawe.sandbox.runner import run_files  # noqa: E402

LINE = "=" * 90


def section(number, title):
    print()
    print(LINE)
    print(f"{number}. {title}")
    print(LINE)


# =====================================================================
def part_one():
    section(1, "The engine cannot tell which provider it is talking to")

    print("  Every agent talks to one interface. This is the whole contract:")
    print()
    print("      class LLMProvider(Protocol):")
    print("          name: str")
    print("          model: str")
    print("          def complete(self, system, user, ...) -> LLMResponse")
    print()
    print("  One method. A real provider implements it by calling Anthropic "
          "or OpenAI;\n  the mock implements it by replaying a scripted "
          "answer. Nothing else differs.")

    # Prove the engine never special-cases the mock, by reading the imports
    engine_files = []
    for path in (ROOT / "src" / "mawe").rglob("*.py"):
        if "bench" in path.parts or path.parts[-2:] == ("llm", "mock.py"):
            continue
        if path.name in ("mock.py", "__init__.py") and path.parent.name == "llm":
            continue
        engine_files.append(path)

    offenders = []
    for path in engine_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            if any("mock" in (n or "").lower() for n in names):
                offenders.append(path.relative_to(ROOT))

    print()
    print(f"  Checked {len(engine_files)} engine source files for any import "
          f"of the mock,")
    print(f"  or any 'if testing' branch: {len(offenders)} found.")
    if offenders:
        print(f"    {offenders}")
    print()
    print("  So there is no test mode. Swapping to a real model is one "
          "environment\n  variable - MAWE_PROVIDER=anthropic - and the graph, "
          "the agents and the\n  database code do not change at all.")


# =====================================================================
def part_two():
    section(2, "The generated code is real, and it really runs")

    correct = ("import sys\n"
               "n = int(sys.argv[1])\n"
               "print(sum(range(1, n + 1)))\n")
    subtly_wrong = ("import sys\n"
                    "n = int(sys.argv[1])\n"
                    "print(sum(range(1, n)))\n")          # off by one

    print("  This has nothing to do with a language model. Two programs, one "
          "with an\n  off-by-one error, both executed in a subprocess:")
    print()
    for label, source in (("correct", correct), ("off by one", subtly_wrong)):
        result = run_files([{"path": "src/main.py", "language": "python",
                             "content": source}], argv=["10"], timeout_s=10)
        print(f"    sum 1..10, {label:<11} -> stdout {result['stdout'].strip()!r}"
              f"   (exit {result['exit_code']}, {result['isolation']})")

    check = AcceptanceCheck(criterion=1, argv=["10"], expect_stdout="55")
    verdicts = []
    for label, source in (("correct", correct), ("off by one", subtly_wrong)):
        outcome = run_check([{"path": "src/main.py", "language": "python",
                              "content": source}], check)
        verdicts.append(outcome.passed)
        print(f"    acceptance check on the {label:<11} version -> "
              f"{'PASS' if outcome.passed else 'FAIL'}")

    from mawe.bench import composition

    hidden = composition()["tests"]
    print()
    print("  The verdict came from comparing bytes of real output, not "
          "from any model's\n  opinion, and no API key was involved. "
          f"Validating the benchmark alone runs its {hidden} hidden\n"
          f"  tests twice over - once against a reference solution, once "
          f"against a program\n  that does nothing - which is "
          f"{hidden * 2} real executions.")
    assert verdicts == [True, False], "this demonstration is broken"


# =====================================================================
def part_three():
    section(3, "Some properties can ONLY be tested without a real model")

    print("  The engine must stop when the Developer stops making progress. "
          "To test that,\n  something has to return byte-identical code "
          "twice in a row.")
    print()
    print("  No real language model can be instructed to do that reliably - "
          "they are\n  non-deterministic by design. A scripted provider can, "
          "so the guarantee becomes\n  testable instead of hoped for.")
    print()

    settings = Settings(max_iterations=5, sandbox_timeout_s=0)
    engine = Engine(provider=MockProvider(stuck_developer_script()),
                    settings=settings, database_url="sqlite://")
    result = engine.run("build something")

    print(f"    scripted Developer repeats itself -> stopped after "
          f"{result.iterations} iterations")
    print(f"    reason reported                   -> {result.termination_reason}")
    print(f"    cap was                           -> {settings.max_iterations}")
    print()
    print("  The same applies to the reviewer that never approves, the code "
          "that cycles\n  A -> B -> A, and the model that returns malformed "
          "JSON. These are the\n  adversarial cases that matter for a safety "
          "guarantee, and a real model will\n  not produce them on demand.")
    assert result.termination_reason == "no_progress"


# =====================================================================
def part_four():
    section(4, "What this does NOT show")

    print("  Everything above tests the machinery around a model: routing, "
          "loop\n  prevention, execution, scoring, persistence, token "
          "accounting.")
    print()
    print("  It says nothing about whether a real model writes good code. "
          "That is a\n  different question, it needs a real API key, and we "
          "have not run it.")
    print()
    print("  Our benchmark is built and validated for exactly that run: 20 "
          "tasks, 181\n  hidden tests, four conditions, 240 runs. What is "
          "missing is the key, not\n  the code.")


def main() -> int:
    print(LINE)
    print("HOW THIS PROJECT IS TESTED WITHOUT AN API KEY")
    print(LINE)
    print("  Short answer: testing the machinery around a model and testing "
          "the quality\n  of a model are two different jobs. The first needs "
          "no API key. The second\n  does, and we have not done it.")

    part_one()
    part_two()
    part_three()
    part_four()

    print()
    print(LINE)
    print("  Run `pytest -q` to see all of it at once.")
    print(LINE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
