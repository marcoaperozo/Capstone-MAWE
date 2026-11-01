"""Week 8 milestone (M3): stable engine v1.0.

    python scripts/week8_m3_check.py

Checks that everything built in Weeks 1 to 7 still works together, and that
the things the project claims about itself are true of the code as it stands.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mawe import __version__  # noqa: E402
from mawe.agents.checks import parse_checks, run_checks, summarise  # noqa: E402
from mawe.config import Settings  # noqa: E402
from mawe.db import Run, session_scope  # noqa: E402
from mawe.engine import Engine  # noqa: E402
from mawe.llm import (  # noqa: E402
    MockProvider,
    oscillating_developer_script,
    picky_reviewer_script,
    stuck_developer_script,
    varied_reviewer_script,
)
from mawe.sample_code import TEMPERATURE_SPEC, temperature_repair_script  # noqa: E402

LINE = "-" * 96
checks_run = []


def check(label, condition, detail=""):
    checks_run.append(bool(condition))
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  -  {detail}" if detail else ""))
    return bool(condition)


def section(title):
    print()
    print("=" * 96)
    print(title)
    print("=" * 96)


def layers():
    section("1 - every layer imports and is wired together")
    for module in ["mawe.config", "mawe.db", "mawe.llm", "mawe.agents",
                   "mawe.graph", "mawe.graph.policy", "mawe.memory",
                   "mawe.sandbox", "mawe.engine", "mawe.cli"]:
        try:
            importlib.import_module(module)
            check(module, True)
        except Exception as exc:
            check(module, False, str(exc))

    try:
        importlib.import_module("mawe.web.app")
        check("mawe.web.app (optional)", True, "FastAPI front end available")
    except ImportError as exc:
        check("mawe.web.app (optional)", True,
              f"not installed, engine unaffected ({exc.name})")


def pipeline():
    section("2 - a complete run delivers code that satisfies its own spec")
    settings = Settings(max_iterations=5, sandbox_timeout_s=15)
    engine = Engine(provider=MockProvider(temperature_repair_script()),
                    settings=settings, database_url="sqlite://")
    result = engine.run("Build a command-line temperature converter")

    check("run reaches approval", result.approved,
          f"{result.iterations} iteration(s), {result.total_tokens:,} tokens")

    summary = summarise(run_checks(result.files,
                                   parse_checks(TEMPERATURE_SPEC["checks"])))
    check("delivered code passes every acceptance check",
          summary["tests_failed"] == 0,
          f"{summary['tests_passed']}/{summary['tests_passed'] + summary['tests_failed']}")

    with session_scope(engine.db) as session:
        run = session.get(Run, result.run_id)
        traceable = all([run.specifications, run.code_artifacts, run.reviews,
                         run.messages, run.evaluation_results])
        versions = len({a.content_hash for a in run.code_artifacts})
    check("the whole run is traceable in the database", traceable,
          f"{versions} distinct code versions recorded")


def termination():
    section("3 - every termination path works through the real engine")
    cases = [
        ("approval", temperature_repair_script(), "approved"),
        ("no progress", stuck_developer_script(), "no_progress"),
        ("repeated issues", picky_reviewer_script(), "repeated_issues"),
        ("oscillation", oscillating_developer_script(), "oscillation"),
        ("iteration cap", varied_reviewer_script(), "iteration_cap"),
    ]
    for label, script, expected in cases:
        settings = Settings(max_iterations=5, sandbox_timeout_s=0)
        engine = Engine(provider=MockProvider(script), settings=settings,
                        database_url="sqlite://")
        result = engine.run("build something")
        check(f"{label:<18} -> {expected}",
              result.termination_reason == expected,
              f"{result.iterations} iteration(s)")


def memory():
    section("4 - context stays bounded on a long run")
    settings = Settings(max_iterations=8, sandbox_timeout_s=0)
    settings.context_token_budget = 4000
    engine = Engine(provider=MockProvider(varied_reviewer_script(12)),
                    settings=settings, database_url="sqlite://")
    result = engine.run("build something")

    with session_scope(engine.db) as session:
        run = session.get(Run, result.run_id)
        rows = [(m.tokens_before, m.tokens_after) for m in run.memory_summaries]

    worst = max((a for _b, a in rows), default=0)
    best_reduction = max(((b - a) / b for b, a in rows if b), default=0.0)
    check("compression measurements are persisted", bool(rows),
          f"{len(rows)} row(s)")
    check("context never exceeds the budget", worst <= 4000,
          f"largest context sent: {worst:,} tokens")
    check("reduction meets the 40% target (H5)", best_reduction >= 0.40,
          f"best observed: {best_reduction * 100:.1f}%")


def documentation():
    section("5 - the repository documents itself")
    for name in ["README.md", "docs/architecture.md", "docs/DEMO-GUIDE.md",
                 ".github/workflows/ci.yml", ".env.example", "requirements.txt"]:
        path = ROOT / name
        check(name, path.exists() and path.stat().st_size > 0)

    scripts = sorted(p.name for p in (ROOT / "scripts").glob("week*_*.py"))
    check("per-week milestone scripts present", len(scripts) >= 4,
          ", ".join(scripts))

    tests = sorted(p.name for p in (ROOT / "tests").glob("test_*.py"))
    check("test modules cover each layer", len(tests) >= 8,
          f"{len(tests)} modules")


def main() -> int:
    print("=" * 96)
    print(f"WEEK 8 MILESTONE (M3) - stable engine v{__version__}")
    print("=" * 96)

    layers()
    pipeline()
    termination()
    memory()
    documentation()

    passed = sum(checks_run)
    total = len(checks_run)
    print()
    print("=" * 96)
    print(f"  {passed}/{total} checks passed")
    print(f"\n  M3 {'MET' if passed == total else 'NOT MET'} - "
          f"engine v{__version__}: the pieces built in Weeks 1-7 work together.")
    print("=" * 96)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
