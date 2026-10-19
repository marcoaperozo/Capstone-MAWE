"""Command-line entry point.

    python -m mawe.cli "Build a terminal snake game"
    python -m mawe.cli "..." --max-iterations 3 --out ./generated --verbose
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from .config import Settings
from .engine import Engine
from .llm import get_provider
from .llm.base import ProviderError

BAR = "=" * 78


def _write_output(files, out_dir: str) -> None:
    for f in files:
        target = os.path.join(out_dir, f["path"])
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(f["content"])
    print(f"\nwrote {len(files)} file(s) to {os.path.abspath(out_dir)}")


def _make_event_printer(verbose: bool):
    def on_event(kind: str, payload: dict) -> None:
        if kind == "plan":
            criteria = payload.get("acceptance_criteria", [])
            print(f"  [plan]      specification written, "
                  f"{len(criteria)} acceptance criteria")
            if verbose:
                for i, c in enumerate(criteria, 1):
                    print(f"              {i}. {c}")
        elif kind == "develop":
            files = payload.get("files", [])
            it = payload.get("iteration", "?")
            paths = ", ".join(f["path"] for f in files) or "(none)"
            print(f"  [develop]   iteration {it}: {paths}")
        elif kind == "review":
            verdict = payload.get("verdict")
            severity = payload.get("severity")
            issues = payload.get("issues", [])
            mark = "PASS" if verdict == "approve" else "FAIL"
            print(f"  [review]    {mark}  severity={severity}  "
                  f"tests {payload.get('tests_passed', 0)} passed / "
                  f"{payload.get('tests_failed', 0)} failed")
            for i, issue in enumerate(issues, 1):
                print(f"              {i}. {issue}")
        elif kind == "finalize":
            print(f"  [finalize]  {payload.get('termination_reason')}")
    return on_event


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mawe",
        description="Multi-Agent AI Workflow Engine: turn a prompt into "
                    "reviewed source code.")
    parser.add_argument("prompt", help="what to build, in plain language")
    parser.add_argument("--language", default="python",
                        choices=["python", "javascript"])
    parser.add_argument("--max-iterations", type=int, default=None,
                        help="hard cap on review/fix cycles (default 5)")
    parser.add_argument("--provider", default=None,
                        choices=["mock", "anthropic", "openai"],
                        help="overrides MAWE_PROVIDER")
    parser.add_argument("--model", default=None)
    parser.add_argument("--db", default=None, help="SQLAlchemy database URL")
    parser.add_argument("--out", default=None,
                        help="directory to write the generated files into")
    parser.add_argument("--no-sandbox", action="store_true",
                        help="skip executing the generated code")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings()
    if args.max_iterations:
        settings.max_iterations = args.max_iterations
    if args.no_sandbox:
        settings.sandbox_timeout_s = 0

    try:
        provider = get_provider(args.provider, args.model)
    except ProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(BAR)
    print(f"MAWE  provider={provider.name}  model={provider.model}  "
          f"max_iterations={settings.max_iterations}")
    print(f"prompt: {args.prompt!r}")
    print(BAR)

    database_url = args.db or settings.database_url
    engine = Engine(provider=provider, settings=settings,
                    database_url=database_url)
    result = engine.run(args.prompt, language=args.language,
                        on_event=_make_event_printer(args.verbose))

    print(BAR)
    print(f"status             : {result.status}")
    print(f"termination reason : {result.termination_reason}")
    print(f"iterations         : {result.iterations}")
    print(f"tokens             : {result.total_tokens:,} "
          f"({result.prompt_tokens:,} in / {result.completion_tokens:,} out)")
    print(f"files              : {', '.join(f['path'] for f in result.files) or '(none)'}")
    if result.run_id is not None:
        print(f"run id             : {result.run_id}  (stored in {database_url})")
    for warning in result.warnings:
        print(f"warning            : {warning}")
    for error in result.errors:
        print(f"error              : {error}")
    print(BAR)

    if args.out and result.files:
        _write_output(result.files, args.out)

    return 0 if result.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
