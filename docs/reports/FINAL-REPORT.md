# MAWE — Multi-Agent AI Workflow Engine

## Final report

Capstone project · Department of Computer Science · Southwest Minnesota State University

Marco Perozo · Gabriel Marte · Lewdy Aquino · Alvin Almonte

Engine v1.0.0 · 427 automated tests · figures generated 2026-11-02

> Every figure in this report is generated from `docs/reports/findings.json`, which
> `scripts/week12_final_check.py` writes from live measurements. Nothing here is
> typed in by hand. Re-run that script and this document can be rebuilt.

---

## 1. What this is, and what it found

Most AI coding tools are one model and one prompt: the model has to understand the
request, design a solution, write it and check it in a single pass. MAWE splits that
across three agents — Product Manager, Developer, Code Reviewer — on a LangGraph
state graph, and loops until the code passes review.

The research question is not whether agents can write code. It is whether role
separation produces **more correct, more requirement-compliant software than a single
model**, and what that costs.

The honest summary at the end of twelve weeks:

- The **engine works** and is tested: 427 automated tests across 13 modules, green on Python 3.11, 3.12 and 3.13.
- The two hypotheses that **do not need a language model** — termination and context
  compression — are **answered by measurement**.
- The three that **do** need one — correctness, specification coverage, cost per
  success — are **not yet answered**. The instrument to answer them is built and
  validated; no sweep against a real model has been run.

That last point is the main limitation of this report, and it is stated here rather
than buried in section 7.

## 2. The experimental design

Four conditions, run over the same tasks under the same settings:

| | condition | what it is |
|---|---|---|
| A | single model | one call, no iteration, no review |
| B | self-refinement | one model that critiques and revises its own code |
| C | multi-agent engine | Product Manager → Developer → Reviewer, looping |
| C' | ablation | the engine with context summarisation switched off |

**B is the control that matters.** Without it, "multi-agent beats one call" is
indistinguishable from "more attempts beat one attempt". B iterates under the same
cap with the same model, so an advantage C shows over B is not simply persistence.

Everything outside the conditions is shared deliberately: the same provider instance,
temperature and iteration cap, the same file parser, the same token accounting at the
single call site, and the same scoring. The baselines get none of the engine's
machinery — no specification, no executable checks, no sandbox evidence, no loop
prevention — which is why B runs to its cap against a model that never settles.

**One confound is not removed, and should not be read past.** C differs from B in two
ways at once: role separation *and* sandbox-grounded review. A gain of C over B cannot
be attributed to either alone by this design. Giving B the sandbox would stop it
isolating iteration, which is the job it is there to do, so the confound is reported
rather than engineered away. Separating the two would need a fifth condition.

## 3. The benchmark, and why it can be trusted

20 tasks — 7 easy, 8 medium, 5 hard — across Python (12) and JavaScript (8),
with 181 hidden tests that no agent ever sees. Scoring is therefore independent of
the LLM reviewer: a run the Reviewer approved can still score zero, which is the
project's answer to its own stated risk that the reviewer is fallible.

A benchmark is a measuring instrument, so three properties were measured rather than
asserted:

| property | result |
|---|---|
| solvable — a reference solution per task passes every hidden test | 20/20 tasks, 181 tests |
| non-vacuous — a program that starts and does nothing | solves 0/20 tasks (5/181 individual tests, the empty-input cases) |
| discriminating — injected single defects are caught | mutation score 91.4% |

Mutation testing earned its place by finding two real defects in the suite:

1. **Every error-path test asserted "exit status 1"** — which an uncaught exception
   also produces. Deleting an input guard left the tests green, and a file of prose
   scored 3 of 7 on FizzBuzz off the error cases alone. The harness now rejects a
   traceback or a syntax error where the task asked for a message on stderr.
2. **Four tasks had untested contract boundaries** — an index exactly one past the
   end, a zero-length interval, a width of 1, a cheap route discovered after an
   expensive one.

Surviving mutants are reported rather than chased to zero. Several are equivalent
mutants with no observable effect, and closing them would mean writing tests against
the reference implementation's internals — which would overfit the benchmark to one
way of solving each task.

## 4. Results

> **These numbers come from a fixture, not a model.** The committed sweep
> (`fixture-sweep.json`, 3 repetitions per task) is driven by `bench.oracle`, whose
> answers are known in advance: the reference solution, a verified defect, or a
> defect it fixes on retry. It shows that the experiment pipeline works end to end
> and that the comparison detects a difference it was built to detect. It says
> **nothing** about any model's ability.

| condition | tasks solved | success rate (95% CI) | mean pass rate | mean tokens |
|---|---|---|---|---|
| A single model | 0/20 | 0.0% [0.0%, 16.1%] | 57.4% | 575 |
| B self-refinement | 20/20 | 100.0% [83.9%, 100.0%] | 100.0% | 2,548 |
| C multi-agent engine | 20/20 | 100.0% [83.9%, 100.0%] | 100.0% | 4,093 |
| C' engine, summarisation off | 20/20 | 100.0% [83.9%, 100.0%] | 100.0% | 4,093 |

The success-rate interval is a Wilson score interval, not the textbook normal one,
which collapses to zero width at 20 of 20 and would report a 100% success rate with
no uncertainty at all from twenty observations.

### Paired comparisons

| comparison | n | p | p (Holm) | effect |
|---|---|---|---|---|
| C vs A | 20 | 0.0000 | 0.0000 \* | +1.00 large |
| C vs B | 0 | 1.0000 | 1.0000 | +0.00 negligible |
| B vs A | 20 | 0.0000 | 0.0000 \* | +1.00 large |
| C vs C' | 0 | 1.0000 | 1.0000 | +0.00 negligible |

\* significant at 0.05 after Holm correction across the four comparisons.

Two methodological points, both of which would otherwise have produced a confident
number rather than an error:

- **The unit of analysis is the task, not the run.** 20 tasks with 3 repetitions
  gives 60 rows per condition, and testing over all of them would treat three runs of
  one task as three independent observations — trebling *n* and shrinking every
  interval by about 1.7 for nothing. Repetitions are averaged within a task; they
  measure stability, which is reported separately.
- **The test follows the metric.** The proposal specified a paired t-test or Wilcoxon
  signed-rank, which is right for tokens and pass rate and wrong for the headline.
  Task success is binary, so nearly every paired difference is zero and the
  signed-rank test discards zeros: with 20 tasks and 3 disagreements it would compute
  a p-value from *n* = 3 while reading as a 20-task result. McNemar's exact test on
  the discordant pairs is the correct choice, and it makes the real sample size the
  headline instead of hiding it.

## 5. Termination (H4)

100,000 randomised adversarial review sequences across 4 policy configurations:
**0 failed to terminate** and **0 exceeded a cap**.

The loop is bounded by five independent mechanisms, unified into a single policy
function so that routing and reason-reporting cannot drift apart:

| mechanism | fires when |
|---|---|
| iteration cap | the configured maximum is reached |
| no progress | two consecutive iterations produce byte-identical code |
| oscillation | code returns to a version already seen (A→B→A), which consecutive-repeat detection misses |
| repeated issues | the same complaint is refiled, compared by normalised fingerprint |
| error | an agent fails irrecoverably |

Exit reasons under the default policy on adversarial input:

| reason | share |
|---|---|
| approved | 81.2% |
| no_progress | 16.4% |
| error | 1.6% |
| oscillation | 0.8% |
| iteration_cap | 0.0% |
| repeated_issues | 0.0% |

Cap exits by configuration — the detectors are what keep this low:

| configuration | exits by cap |
|---|---|
| default, cap 5 | 0.0% |
| cap 1 | 47.0% |
| cap 20 | 0.0% |
| detectors off, cap 5 | 2.2% |

**The second clause of H4 is pointed the right way but not settled.** Under the default
policy the cap accounts for 0.0% of exits, well inside the 10% the hypothesis allows,
because the other detectors catch runs first. With the detectors disabled the cap
becomes the only thing stopping a run, which is what the configuration is there to
show. But adversarial random input is not a language model, and the clause is a claim
about real runs — so it needs a sweep against a model to confirm.

## 6. Context compression (H5)

Target: at least 40% reduction without changing outcomes. Measured: **93.7%** at 80 iterations,
never exceeding the 4,000-token budget (largest context actually sent: 3,316).

| iterations | uncompressed | compressed | reduction |
|---|---|---|---|
| 1 | 637 | 637 | 0.0% |
| 2 | 1,293 | 688 | 46.8% |
| 5 | 3,260 | 787 | 75.9% |
| 10 | 6,539 | 954 | 85.4% |
| 20 | 13,104 | 1,291 | 90.1% |
| 40 | 26,234 | 1,966 | 92.5% |
| 80 | 52,494 | 3,316 | 93.7% |

The compression is **structured, not generative**: older iterations collapse into a
progress log built from recorded facts — what changed, what the review said, which
checks passed — rather than being re-summarised by a model. A summariser that
hallucinates would corrupt the Developer's only memory of what it already tried.

The ablation confirms the "without changing outcomes" half: C and C' solve the same
tasks (20/20 and 20/20). On runs long enough for compression to apply at all — it needs at
least two completed iterations — C' sends measurably more tokens for the same result.

## 7. Hypothesis scorecard

| | hypothesis | verdict |
|---|---|---|
| H1 | Role separation produces more correct software than a single model on the same tasks. | **Not yet testable** |
| H2 | Role separation produces better specification coverage. | **Not yet testable** |
| H3 | The improvement is worth its cost, measured per *successful* task. | **Not yet testable** |
| H4 | Every run terminates, and fewer than 10% end by hitting the iteration cap. | **Supported** |
| H5 | Context summarisation cuts prompt size by at least 40% without changing outcomes. | **Supported** |

**H1 — **Not yet testable****  
Role separation produces more correct software than a single model on the same tasks.  
*Evidence:* the comparison runs, and detects a quality difference it was built to detect; no sweep against a real model has been run  
*Caveat:* needs an API key: the committed sweep is a fixture with known answers and measures the apparatus, not a model

**H2 — **Not yet testable****  
Role separation produces better specification coverage.  
*Evidence:* the comparison runs, and detects a quality difference it was built to detect; no sweep against a real model has been run  
*Caveat:* needs an API key: the committed sweep is a fixture with known answers and measures the apparatus, not a model; specification coverage also has no metric yet - the benchmark scores behaviour, not whether a spec was complete

**H3 — **Not yet testable****  
The improvement is worth its cost, measured per *successful* task.  
*Evidence:* the comparison runs, and detects a quality difference it was built to detect; no sweep against a real model has been run  
*Caveat:* needs an API key: the committed sweep is a fixture with known answers and measures the apparatus, not a model

**H4 — **Supported****  
Every run terminates, and fewer than 10% end by hitting the iteration cap.  
*Evidence:* 100,000 randomised adversarial sequences, 0 failed to terminate, 0 exceeded a cap  
*Caveat:* the <10% cap-exit clause is about real runs. Under the default policy the cap accounts for 0.0% of exits because the detectors catch runs earlier, which is consistent with the clause; but adversarial random input is not a model, so the clause is not settled by this

**H5 — **Supported****  
Context summarisation cuts prompt size by at least 40% without changing outcomes.  
*Evidence:* 93.7% reduction at 80 iterations, never over budget; C and C' solve the same tasks  
*Caveat:* the reduction is measured on the engine's own prompts, which is where it applies; 'no pass-rate drop' is confirmed against the fixture, not against a model

## 8. Limitations

1. **No model has been measured.** H1, H2 and H3 need a real provider. The adapters
   for Anthropic and OpenAI are written but have never been run against a live API,
   so they are untested code, not working code.
2. **Specification coverage has no metric.** H2 needs one. The benchmark scores
   behaviour, not whether a specification captured the request.
3. **C vs B confounds two variables** — role separation and grounded review — as
   described in section 2.
4. **Twenty tasks, small to medium.** Nothing here speaks to multi-file systems,
   long-lived codebases, or tasks where the hard part is the design.
5. **Functional correctness only.** Not style, security, maintainability or
   performance.
6. **Three repetitions.** Enough to detect instability, not enough to characterise
   its distribution.
7. **The subprocess sandbox is not a security boundary.** It has a timeout, path
   containment and output truncation; Docker with no network is the hardening
   target and is not implemented.

## 9. What would finish this

In order of what each buys:

1. **One sweep against a real model.** 4 conditions x 20 tasks x 3 repetitions = 240 runs.
   The pipeline, the scoring and the statistics are built and validated; this is the
   single step between the current report and answers to H1 and H3.
2. **A specification-coverage metric**, to make H2 testable at all.
3. **A fifth condition** that gives B the sandbox, separating role separation from
   grounded review.

---

*Generated from `findings.json` (2026-11-02T23:17:20) by `docs/reports/build_final_report.py`.*
