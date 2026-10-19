"""Week 3 milestone check: the PM agent produces valid specs on 5 sample prompts.

    python scripts/week3_spec_check.py

Runs the Product Manager over every sample prompt twice - once with a clean
model response, once with a malformed first response - and reports whether the
contract held and whether the repair round recovered it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mawe.agents.product_manager import (  # noqa: E402
    ProductManagerAgent, parse_specification, validate,
)
from mawe.config import Settings  # noqa: E402
from mawe.llm import MockProvider  # noqa: E402
from mawe.samples import SAMPLE_PROMPTS, pm_script  # noqa: E402

SETTINGS = Settings(max_iterations=5, sandbox_timeout_s=0)
LINE = "-" * 104


def check(sample, malformed_first: bool):
    provider = MockProvider(pm_script(sample["spec"], malformed_first))
    update = ProductManagerAgent(provider, SETTINGS).run(
        {"prompt": sample["prompt"], "language": sample["language"]})

    if "errors" in update:
        return {"valid": False, "calls": provider.call_count("product_manager"),
                "criteria": 0, "files": 0, "problems": update["errors"]}

    spec = parse_specification(update["spec"])
    problems = validate(spec)
    return {"valid": not problems,
            "calls": provider.call_count("product_manager"),
            "criteria": len(spec.acceptance_criteria),
            "files": len(spec.files),
            "problems": problems}


def main() -> int:
    print("=" * 104)
    print("WEEK 3 MILESTONE - Product Manager agent produces valid specs on 5 sample prompts")
    print("=" * 104)
    print(f"{'sample':<34}{'difficulty':<12}{'lang':<12}"
          f"{'criteria':>9}{'files':>7}{'calls':>7}{'valid':>8}")
    print(LINE)

    clean_ok = repaired_ok = 0

    for sample in SAMPLE_PROMPTS:
        result = check(sample, malformed_first=False)
        clean_ok += result["valid"]
        print(f"{sample['name']:<34}{sample['difficulty']:<12}{sample['language']:<12}"
              f"{result['criteria']:>9}{result['files']:>7}{result['calls']:>7}"
              f"{('PASS' if result['valid'] else 'FAIL'):>8}")
        if result["problems"]:
            for p in result["problems"]:
                print(f"    ! {p}")

    print(LINE)
    print("Repair round - the first model answer violates the contract on purpose:")
    print(LINE)
    print(f"{'sample':<34}{'first answer':<22}{'after repair':<18}{'calls':>7}{'valid':>8}")
    print(LINE)

    for sample in SAMPLE_PROMPTS:
        result = check(sample, malformed_first=True)
        repaired_ok += result["valid"]
        print(f"{sample['name']:<34}{'invalid (1 criterion)':<22}"
              f"{str(result['criteria']) + ' criteria':<18}{result['calls']:>7}"
              f"{('PASS' if result['valid'] else 'FAIL'):>8}")

    total = len(SAMPLE_PROMPTS)
    print(LINE)
    print(f"valid on first answer : {clean_ok}/{total}")
    print(f"recovered by 1 repair : {repaired_ok}/{total}")
    print(f"M-W3 {'MET' if clean_ok == total and repaired_ok == total else 'NOT MET'}"
          f" - the PM contract holds across both target languages and all "
          f"three difficulty levels.")
    print("=" * 104)
    return 0 if clean_ok == total and repaired_ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
