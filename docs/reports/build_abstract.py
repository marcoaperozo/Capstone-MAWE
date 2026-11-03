"""Generate the conference abstract from the measured figures.

    python scripts/week12_final_check.py      # produces findings.json
    python docs/reports/build_abstract.py     # produces ABSTRACT.md

An abstract is a single self-contained paragraph, usually 150-250 words, that
a reader can understand without the poster in front of them. Conference
committees read it to decide whether to accept the work, and attendees read it
to decide whether to stop at the poster. It answers five questions in order:

    1. What problem?
    2. What did you build?
    3. How did you evaluate it?
    4. What did you find?
    5. Why does it matter?

It is not an introduction and not a summary of the paper's structure. "This
poster describes our approach and presents results" says nothing; the results
themselves say everything.

Three versions are written here because submission forms ask for different
lengths. Every number comes from `findings.json`, so none of them can drift
away from what the code actually does.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FINDINGS = HERE / "findings.json"
OUTPUT = HERE / "ABSTRACT.md"


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.–-]*", text))


def build(F: dict) -> str:
    B, TERM, C = F["benchmark"], F["termination"], F["compression"]
    reduction = C["best_reduction"] * 100
    mutation = B["mutation_score"] * 100

    full = (
        "Most AI coding assistants are a single model answering a single "
        "prompt: one pass to understand, design, write and verify. We present "
        "MAWE, a Multi-Agent AI Workflow Engine "
        "that divides the work across three agents mirroring a software team "
        "— a Product Manager that turns a request into a specification "
        "with executable acceptance checks, a Developer that implements it, "
        "and a Code Reviewer that runs the code in a sandbox and either "
        "approves it or sends it back. The agents are orchestrated as an "
        "explicit state graph whose revision loop is bounded by five exit "
        "conditions, so it cannot run forever. "
        f"We evaluate MAWE against three controls — a single model, a "
        f"single model that critiques and revises its own code, and an "
        f"ablation with context compression disabled — on a benchmark of "
        f"{B['tasks']} Python and JavaScript tasks carrying "
        f"{B['hidden_tests']} hidden tests no agent sees, so scoring does not "
        f"depend on the reviewing model. The "
        f"benchmark is itself validated: every task is solvable, none is "
        f"satisfied by a program that does nothing, and injected defects are "
        f"detected {mutation:.0f}% of the time. "
        f"Two results are established by measurement. Across "
        f"{TERM['runs']:,} randomised adversarial review sequences, no run "
        f"failed to terminate and none exceeded its iteration cap; and "
        f"compressing the revision history cuts prompt size by "
        f"{reduction:.0f}% at 80 iterations while leaving outcomes "
        f"unchanged. Whether role separation improves correctness, and "
        f"whether it justifies its token cost, requires a comparison against "
        f"a live model that has not yet been run."
    )

    medium = (
        "Most AI coding assistants are a single model answering a single "
        "prompt. We present MAWE, a Multi-Agent AI Workflow Engine that "
        "divides the work across three agents mirroring a software team: a "
        "Product Manager that writes a specification with executable "
        "acceptance checks, a Developer that implements it, and a Code "
        "Reviewer that runs the code in a sandbox and sends it back until it "
        "passes. "
        f"We evaluate it against a single model, a self-refining single "
        f"model, and an ablation, on {B['tasks']} tasks with "
        f"{B['hidden_tests']} hidden tests no agent sees, so scoring does "
        f"not depend on the reviewing model. Across {TERM['runs']:,} "
        f"randomised adversarial sequences, every run terminated inside its "
        f"iteration cap, and compressing the revision history cut prompt "
        f"size by {reduction:.0f}% without changing outcomes. Whether role "
        f"separation improves correctness, and at what cost, awaits a "
        f"comparison against a live model."
    )

    short = (
        "MAWE divides AI code generation across three agents — a Product "
        "Manager, a Developer and a Code Reviewer that runs the code — "
        f"instead of asking one model to do everything in one pass. On a "
        f"{B['tasks']}-task benchmark with {B['hidden_tests']} hidden tests, "
        f"we show the revision loop always terminates "
        f"({TERM['runs']:,} adversarial sequences, none exceeding its cap) "
        f"and that compressing the revision history cuts prompt size by "
        f"{reduction:.0f}% without changing outcomes."
    )

    out = []
    w = out.append
    w("# MAWE — Conference abstract")
    w("")
    w("**Multi-Agent AI Workflow Engine: Simulating an Autonomous Software "
      "Development Team**")
    w("")
    w("Marco Perozo, Gabriel Marte, Lewdy Aquino, Alvin Almonte  ")
    w("Department of Computer Science, Southwest Minnesota State University")
    w("")
    w("> Generated from `findings.json`. Every figure matches what the code "
      "currently does.")
    w("")
    w("---")
    w("")
    w("## What an abstract is")
    w("")
    w("One self-contained paragraph, normally 150–250 words, that makes "
      "sense to someone")
    w("who has not seen the poster. It answers five questions in order:")
    w("")
    w("1. **What problem?**")
    w("2. **What did you build?**")
    w("3. **How did you evaluate it?**")
    w("4. **What did you find?**")
    w("5. **Why does it matter?**")
    w("")
    w("It is not an introduction, and it does not describe the document. "
      "“This poster")
    w("presents our approach and discusses results” says nothing — "
      "the results themselves")
    w("say everything. Write it last, in the past tense, with no citations "
      "and no")
    w("undefined abbreviations.")
    w("")
    w("---")
    w("")

    for title, text, note in (
        ("Full version", full,
         "for a submission form that allows 250 words"),
        ("Medium version", medium,
         "for a 150-word limit"),
        ("Elevator version", short,
         "for a programme listing, or for answering “so what is it?” "
         "out loud"),
    ):
        w(f"## {title} — {words(text)} words")
        w("")
        w(f"*{note}*")
        w("")
        w(text)
        w("")

    w("---")
    w("")
    w("## If you have to cut it further")
    w("")
    w("Cut in this order, and stop as soon as it fits:")
    w("")
    w("1. the benchmark-validation sentence (solvable / non-vacuous / "
      f"{mutation:.0f}% detection);")
    w("2. the names of the three control conditions, keeping “three "
      "controls”;")
    w("3. the description of what each agent does, keeping the three role "
      "names.")
    w("")
    w("Do **not** cut the last sentence. An abstract that omits the fact "
      "that no live")
    w("model has been run would be claiming more than the work supports, "
      "and that is the")
    w("one error an examiner is certain to catch.")
    w("")
    return "\n".join(out)


def main() -> int:
    if not FINDINGS.exists():
        print(f"{FINDINGS} is missing. Run scripts/week12_final_check.py "
              f"first.", file=sys.stderr)
        return 2
    findings = json.loads(FINDINGS.read_text(encoding="utf-8"))
    OUTPUT.write_text(build(findings), encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
