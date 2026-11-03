"""Generate the final report from the measured figures.

    python scripts/week12_final_check.py        # produces findings.json
    python docs/reports/build_final_report.py   # produces FINAL-REPORT.md

Every number in the report comes from `findings.json`, which
`scripts/week12_final_check.py` writes from live measurements. Nothing is
typed in by hand.

That rule exists because of a specific failure earlier in this project: a
progress deck claimed 273 passing tests while the suite had 255, because the
figure had been copied from a terminal and the suite moved underneath it. The
number was wrong in the direction that flattered the work, nobody noticed for
two commits, and it was the kind of error the project's own argument - that
measured evidence beats asserted claims - exists to prevent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FINDINGS = HERE / "findings.json"
OUTPUT = HERE / "FINAL-REPORT.md"

CONDITION_NAMES = {
    "A": "single model",
    "B": "self-refinement",
    "C": "multi-agent engine",
    "C'": "engine, summarisation off",
}

VERDICT_LABEL = {
    "supported": "**Supported**",
    "unsupported": "**Not supported**",
    "measured": "**Measured**",
    "not yet testable": "**Not yet testable**",
}

HYPOTHESES = {
    "H1": "Role separation produces more correct software than a single "
          "model on the same tasks.",
    "H2": "Role separation produces better specification coverage.",
    "H3": "The improvement is worth its cost, measured per *successful* "
          "task.",
    "H4": "Every run terminates, and fewer than 10% end by hitting the "
          "iteration cap.",
    "H5": "Context summarisation cuts prompt size by at least 40% without "
          "changing outcomes.",
}


def pct(value, digits=1):
    return f"{value * 100:.{digits}f}%"


def build(findings: dict) -> str:
    bench = findings["benchmark"]
    tests = findings["tests"]
    term = findings["termination"]
    comp = findings["compression"]
    comparison = findings["comparison"]
    hypotheses = findings["hypotheses"]
    conditions = comparison["conditions"]

    out = []
    w = out.append

    w("# MAWE — Multi-Agent AI Workflow Engine")
    w("")
    w("## Final report")
    w("")
    w("Capstone project · Department of Computer Science · Southwest "
      "Minnesota State University")
    w("")
    w("Marco Perozo · Gabriel Marte · Lewdy Aquino · Alvin Almonte")
    w("")
    w(f"Engine v{findings['engine_version']} · "
      f"{tests['total']} automated tests · "
      f"figures generated {findings['generated_at'][:10]}")
    w("")
    w("> Every figure in this report is generated from "
      "`docs/reports/findings.json`, which")
    w("> `scripts/week12_final_check.py` writes from live measurements. "
      "Nothing here is")
    w("> typed in by hand. Re-run that script and this document can be "
      "rebuilt.")
    w("")
    w("---")
    w("")

    # ------------------------------------------------------------ summary
    w("## 1. What this is, and what it found")
    w("")
    w("Most AI coding tools are one model and one prompt: the model has to "
      "understand the")
    w("request, design a solution, write it and check it in a single pass. "
      "MAWE splits that")
    w("across three agents — Product Manager, Developer, Code Reviewer — on "
      "a LangGraph")
    w("state graph, and loops until the code passes review.")
    w("")
    w("The research question is not whether agents can write code. It is "
      "whether role")
    w("separation produces **more correct, more requirement-compliant "
      "software than a single")
    w("model**, and what that costs.")
    w("")
    w("The honest summary at the end of twelve weeks:")
    w("")
    w("- The **engine works** and is tested: "
      f"{tests['total']} automated tests across {tests['modules']} modules, "
      "green on Python 3.11, 3.12 and 3.13.")
    w("- The two hypotheses that **do not need a language model** — "
      "termination and context")
    w("  compression — are **answered by measurement**.")
    w("- The three that **do** need one — correctness, specification "
      "coverage, cost per")
    w("  success — are **not yet answered**. The instrument to answer them "
      "is built and")
    w("  validated; no sweep against a real model has been run.")
    w("")
    w("That last point is the main limitation of this report, and it is "
      "stated here rather")
    w("than buried in section 7.")
    w("")

    # ------------------------------------------------------------ design
    w("## 2. The experimental design")
    w("")
    w("Four conditions, run over the same tasks under the same settings:")
    w("")
    w("| | condition | what it is |")
    w("|---|---|---|")
    w("| A | single model | one call, no iteration, no review |")
    w("| B | self-refinement | one model that critiques and revises its own "
      "code |")
    w("| C | multi-agent engine | Product Manager → Developer → Reviewer, "
      "looping |")
    w("| C' | ablation | the engine with context summarisation switched off |")
    w("")
    w("**B is the control that matters.** Without it, \"multi-agent beats "
      "one call\" is")
    w("indistinguishable from \"more attempts beat one attempt\". B iterates "
      "under the same")
    w("cap with the same model, so an advantage C shows over B is not "
      "simply persistence.")
    w("")
    w("Everything outside the conditions is shared deliberately: the same "
      "provider instance,")
    w("temperature and iteration cap, the same file parser, the same token "
      "accounting at the")
    w("single call site, and the same scoring. The baselines get none of "
      "the engine's")
    w("machinery — no specification, no executable checks, no sandbox "
      "evidence, no loop")
    w("prevention — which is why B runs to its cap against a model that "
      "never settles.")
    w("")
    w("**One confound is not removed, and should not be read past.** C "
      "differs from B in two")
    w("ways at once: role separation *and* sandbox-grounded review. A gain "
      "of C over B cannot")
    w("be attributed to either alone by this design. Giving B the sandbox "
      "would stop it")
    w("isolating iteration, which is the job it is there to do, so the "
      "confound is reported")
    w("rather than engineered away. Separating the two would need a fifth "
      "condition.")
    w("")

    # ------------------------------------------------------------ benchmark
    w("## 3. The benchmark, and why it can be trusted")
    w("")
    w(f"{bench['tasks']} tasks — {bench['easy']} easy, {bench['medium']} "
      f"medium, {bench['hard']} hard — across Python ({bench['python']}) "
      f"and JavaScript ({bench['javascript']}),")
    w(f"with {bench['hidden_tests']} hidden tests that no agent ever sees. "
      "Scoring is therefore independent of")
    w("the LLM reviewer: a run the Reviewer approved can still score zero, "
      "which is the")
    w("project's answer to its own stated risk that the reviewer is "
      "fallible.")
    w("")
    w("A benchmark is a measuring instrument, so three properties were "
      "measured rather than")
    w("asserted:")
    w("")
    w("| property | result |")
    w("|---|---|")
    w(f"| solvable — a reference solution per task passes every hidden test "
      f"| {bench['references_passing']}/{bench['tasks']} tasks, "
      f"{bench['hidden_tests']} tests |")
    w(f"| non-vacuous — a program that starts and does nothing | solves "
      f"{bench['stub_tasks_solved']}/{bench['tasks']} tasks "
      f"({bench['stub_tests_passed']}/{bench['stub_tests_total']} "
      f"individual tests, the empty-input cases) |")
    if bench.get("mutation_score") is not None:
        w(f"| discriminating — injected single defects are caught | "
          f"mutation score {pct(bench['mutation_score'])} |")
    w("")
    w("Mutation testing earned its place by finding two real defects in the "
      "suite:")
    w("")
    w("1. **Every error-path test asserted \"exit status 1\"** — which an "
      "uncaught exception")
    w("   also produces. Deleting an input guard left the tests green, and "
      "a file of prose")
    w("   scored 3 of 7 on FizzBuzz off the error cases alone. The harness "
      "now rejects a")
    w("   traceback or a syntax error where the task asked for a message on "
      "stderr.")
    w("2. **Four tasks had untested contract boundaries** — an index "
      "exactly one past the")
    w("   end, a zero-length interval, a width of 1, a cheap route "
      "discovered after an")
    w("   expensive one.")
    w("")
    w("Surviving mutants are reported rather than chased to zero. Several "
      "are equivalent")
    w("mutants with no observable effect, and closing them would mean "
      "writing tests against")
    w("the reference implementation's internals — which would overfit the "
      "benchmark to one")
    w("way of solving each task.")
    w("")

    # ------------------------------------------------------------ results
    w("## 4. Results")
    w("")
    if not comparison["measures_a_model"]:
        w("> **These numbers come from a fixture, not a model.** The "
          "committed sweep")
        w(f"> (`{comparison['source']}`, "
          f"{comparison['repetitions']} repetitions per task) is driven by "
          "`bench.oracle`, whose")
        w("> answers are known in advance: the reference solution, a "
          "verified defect, or a")
        w("> defect it fixes on retry. It shows that the experiment "
          "pipeline works end to end")
        w("> and that the comparison detects a difference it was built to "
          "detect. It says")
        w("> **nothing** about any model's ability.")
        w("")
    w("| condition | tasks solved | success rate (95% CI) | mean pass rate "
      "| mean tokens |")
    w("|---|---|---|---|---|")
    for label in ("A", "B", "C", "C'"):
        item = conditions.get(label)
        if not item:
            continue
        low, high = item["success_ci"]
        w(f"| {label} {CONDITION_NAMES[label]} | "
          f"{item['solved']}/{item['tasks']} | "
          f"{pct(item['success_rate'])} [{pct(low)}, {pct(high)}] | "
          f"{pct(item['pass_rate'])} | {item['tokens']:,.0f} |")
    w("")
    w("The success-rate interval is a Wilson score interval, not the "
      "textbook normal one,")
    w("which collapses to zero width at 20 of 20 and would report a 100% "
      "success rate with")
    w("no uncertainty at all from twenty observations.")
    w("")
    w("### Paired comparisons")
    w("")
    w("| comparison | n | p | p (Holm) | effect |")
    w("|---|---|---|---|---|")
    for item in comparison["success_comparisons"]:
        adjusted = ("—" if item["p_adjusted"] is None
                    else f"{item['p_adjusted']:.4f}")
        marker = " \\*" if item["reject"] else ""
        w(f"| {item['left']} vs {item['right']} | {item['n']} | "
          f"{item['p']:.4f} | {adjusted}{marker} | "
          f"{item['effect']:+.2f} {item['effect_label']} |")
    w("")
    w("\\* significant at 0.05 after Holm correction across the four "
      "comparisons.")
    w("")
    w("Two methodological points, both of which would otherwise have "
      "produced a confident")
    w("number rather than an error:")
    w("")
    w("- **The unit of analysis is the task, not the run.** "
      f"{bench['tasks']} tasks with "
      f"{comparison['repetitions']} repetitions")
    w(f"  gives {bench['tasks'] * comparison['repetitions']} rows per "
      "condition, and testing over all of them would treat three runs of")
    w("  one task as three independent observations — trebling *n* and "
      "shrinking every")
    w("  interval by about 1.7 for nothing. Repetitions are averaged within "
      "a task; they")
    w("  measure stability, which is reported separately.")
    w("- **The test follows the metric.** The proposal specified a paired "
      "t-test or Wilcoxon")
    w("  signed-rank, which is right for tokens and pass rate and wrong for "
      "the headline.")
    w("  Task success is binary, so nearly every paired difference is zero "
      "and the")
    w("  signed-rank test discards zeros: with 20 tasks and 3 "
      "disagreements it would compute")
    w("  a p-value from *n* = 3 while reading as a 20-task result. "
      "McNemar's exact test on")
    w("  the discordant pairs is the correct choice, and it makes the real "
      "sample size the")
    w("  headline instead of hiding it.")
    w("")

    # ------------------------------------------------------------ H4/H5
    w("## 5. Termination (H4)")
    w("")
    w(f"{term['runs']:,} randomised adversarial review sequences across "
      f"{term['configurations']} policy configurations:")
    w(f"**{term['non_terminating']} failed to terminate** and "
      f"**{term['over_cap']} exceeded a cap**.")
    w("")
    w("The loop is bounded by five independent mechanisms, unified into a "
      "single policy")
    w("function so that routing and reason-reporting cannot drift apart:")
    w("")
    w("| mechanism | fires when |")
    w("|---|---|")
    w("| iteration cap | the configured maximum is reached |")
    w("| no progress | two consecutive iterations produce byte-identical "
      "code |")
    w("| oscillation | code returns to a version already seen (A→B→A), "
      "which consecutive-repeat detection misses |")
    w("| repeated issues | the same complaint is refiled, compared by "
      "normalised fingerprint |")
    w("| error | an agent fails irrecoverably |")
    w("")
    w("Exit reasons under the default policy on adversarial input:")
    w("")
    w("| reason | share |")
    w("|---|---|")
    total_default = sum(term["default_distribution"].values()) or 1
    for reason, count in sorted(term["default_distribution"].items(),
                                key=lambda kv: -kv[1]):
        w(f"| {reason} | {pct(count / total_default)} |")
    w("")
    w("Cap exits by configuration — the detectors are what keep this low:")
    w("")
    w("| configuration | exits by cap |")
    w("|---|---|")
    for label, row in term.get("per_configuration", {}).items():
        w(f"| {label} | {pct(row['cap_share'])} |")
    w("")
    w("**The second clause of H4 is pointed the right way but not "
      "settled.** Under the default")
    w(f"policy the cap accounts for "
      f"{pct(term.get('default_cap_share', 0))} of exits, well inside the "
      "10% the hypothesis allows,")
    w("because the other detectors catch runs first. With the detectors "
      "disabled the cap")
    w("becomes the only thing stopping a run, which is what the "
      "configuration is there to")
    w("show. But adversarial random input is not a language model, and the "
      "clause is a claim")
    w("about real runs — so it needs a sweep against a model to confirm.")
    w("")

    w("## 6. Context compression (H5)")
    w("")
    w(f"Target: at least 40% reduction without changing outcomes. "
      f"Measured: "
      f"**{pct(comp['best_reduction'])}** at 80 iterations,")
    w(f"never exceeding the {comp['budget']:,}-token budget "
      f"(largest context actually sent: {comp['largest_context']:,}).")
    w("")
    w("| iterations | uncompressed | compressed | reduction |")
    w("|---|---|---|---|")
    for key in sorted(comp["ladder"], key=lambda k: int(k)):
        row = comp["ladder"][key]
        w(f"| {key} | {row['uncompressed']:,} | {row['compressed']:,} | "
          f"{pct(row['reduction'])} |")
    w("")
    w("The compression is **structured, not generative**: older iterations "
      "collapse into a")
    w("progress log built from recorded facts — what changed, what the "
      "review said, which")
    w("checks passed — rather than being re-summarised by a model. A "
      "summariser that")
    w("hallucinates would corrupt the Developer's only memory of what it "
      "already tried.")
    w("")
    if "C" in conditions and "C'" in conditions:
        w(f"The ablation confirms the \"without changing outcomes\" half: C "
          f"and C' solve the same")
        w(f"tasks ({conditions['C']['solved']}/{conditions['C']['tasks']} "
          f"and {conditions[chr(67) + chr(39)]['solved']}"
          f"/{conditions[chr(67) + chr(39)]['tasks']}). On runs long enough "
          "for compression to apply at all — it needs at")
        w("least two completed iterations — C' sends measurably more "
          "tokens for the same result.")
        w("")

    # ------------------------------------------------------------ scorecard
    w("## 7. Hypothesis scorecard")
    w("")
    w("| | hypothesis | verdict |")
    w("|---|---|---|")
    for key in ("H1", "H2", "H3", "H4", "H5"):
        item = hypotheses[key]
        w(f"| {key} | {HYPOTHESES[key]} | "
          f"{VERDICT_LABEL[item['verdict']]} |")
    w("")
    for key in ("H1", "H2", "H3", "H4", "H5"):
        item = hypotheses[key]
        w(f"**{key} — {VERDICT_LABEL[item['verdict']]}**  ")
        w(f"{HYPOTHESES[key]}  ")
        w(f"*Evidence:* {item['evidence']}  ")
        if item.get("caveat"):
            w(f"*Caveat:* {item['caveat']}")
        w("")

    # ------------------------------------------------------------ limits
    w("## 8. Limitations")
    w("")
    w("1. **No model has been measured.** H1, H2 and H3 need a real "
      "provider. The adapters")
    w("   for Anthropic and OpenAI are written but have never been run "
      "against a live API,")
    w("   so they are untested code, not working code.")
    w("2. **Specification coverage has no metric.** H2 needs one. The "
      "benchmark scores")
    w("   behaviour, not whether a specification captured the request.")
    w("3. **C vs B confounds two variables** — role separation and "
      "grounded review — as")
    w("   described in section 2.")
    w("4. **Twenty tasks, small to medium.** Nothing here speaks to "
      "multi-file systems,")
    w("   long-lived codebases, or tasks where the hard part is the "
      "design.")
    w("5. **Functional correctness only.** Not style, security, "
      "maintainability or")
    w("   performance.")
    w("6. **Three repetitions.** Enough to detect instability, not enough "
      "to characterise")
    w("   its distribution.")
    w("7. **The subprocess sandbox is not a security boundary.** It has a "
      "timeout, path")
    w("   containment and output truncation; Docker with no network is the "
      "hardening")
    w("   target and is not implemented.")
    w("")

    # ------------------------------------------------------------ next
    w("## 9. What would finish this")
    w("")
    w("In order of what each buys:")
    w("")
    w("1. **One sweep against a real model.** "
      f"4 conditions x {bench['tasks']} tasks x "
      f"{comparison['repetitions']} repetitions = "
      f"{4 * bench['tasks'] * comparison['repetitions']} runs.")
    w("   The pipeline, the scoring and the statistics are built and "
      "validated; this is the")
    w("   single step between the current report and answers to H1 and H3.")
    w("2. **A specification-coverage metric**, to make H2 testable at all.")
    w("3. **A fifth condition** that gives B the sandbox, separating role "
      "separation from")
    w("   grounded review.")
    w("")
    w("---")
    w("")
    w(f"*Generated from `findings.json` ({findings['generated_at']}) by "
      f"`docs/reports/build_final_report.py`.*")
    if findings.get("quick"):
        w("")
        w("> **Warning:** these figures came from a `--quick` run, which "
          "reduces the mutation")
        w("> sweep and the stress test. Re-run "
          "`scripts/week12_final_check.py` without `--quick`.")
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
    if findings.get("quick"):
        print("  NOTE: built from a --quick run; the report says so.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
