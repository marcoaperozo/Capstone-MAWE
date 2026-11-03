# MAWE — How it works, and how to demo it

A guide for showing the project to Dr. Hezy. Everything here is a command you
can run live; nothing requires an API key or costs money.

---

## 1. The 30-second version

MAWE takes a plain-English prompt and turns it into reviewed source code by
routing it through three AI agents that mirror a real software team.

```
prompt ──> Product Manager ──> Developer ──> Code Reviewer ──> finalize
                                   ^              |
                                   └──────────────┘
                              reject & iter < max & progress
```

The hard part is not "use several agents." It is making that loop **provably
terminate** and **measurably cheap**. That is what the code does and what the
tests prove.

---

## 2. What to run, in order

### A. Prove the whole thing works — the full suite, about a minute

```bash
python -m pytest -q
```

This is the strongest single thing you can show. No API key, no network, no
cost. The count it prints is the count; this guide deliberately does not
repeat it, because a hand-maintained number drifts from the suite and this
one already did, three times. The current figure lives in
[`docs/reports/FINAL-REPORT.md`](reports/FINAL-REPORT.md), which is generated
from measurements.

If he wants detail:

```bash
python -m pytest -v
```

### B. Watch the pipeline run live

```bash
python -m mawe.cli "Build a terminal snake game" --verbose
```

You will see the spec written, the Developer produce a file, the Reviewer
reject it with a specific criterion number, the Developer fix it, and the
Reviewer approve. That is the loop doing its job.

### C. Prove the loop always terminates — the CS contribution

```bash
python scripts/m1_demo.py --db
```

Three scenarios, three different exit paths:

| Scenario | Iterations | Why it stopped |
|---|---|---|
| Reject, reject, approve | 2 | `approved` |
| Developer returns identical code | 2 | `no_progress` — caught by SHA-256 hash |
| Reviewer never approves | 5 | `iteration_cap` |

### D. Prove the generated code actually runs

```bash
python scripts/week4_dev_check.py
```

Writes the generated files into a sandbox, executes them, compares stdout
against expected output. 10/10 pass, including a 3-file expression parser
whose cross-module imports resolve.

### E. Prove the PM produces usable specs

```bash
python scripts/week3_spec_check.py
```

5 sample prompts across Python and JavaScript, three difficulty levels.
5/5 valid; 5/5 recovered when the first model answer deliberately breaks the
contract.

### F. Prove the benchmark is worth trusting — Phase 4

```bash
python scripts/week9_bench_check.py
```

This is the strongest thing to show after the test suite, because it is the
project grading its own measuring instrument. 20 tasks with 181 hidden tests
that no agent ever sees, and three properties measured rather than claimed:
every task is solvable (a reference solution passes all of its hidden tests),
no task is satisfied by a program that does nothing, and injected defects are
caught 91.4% of the time.

Takes about two minutes — the mutation sweep is the slow part. Add `--quick`
to skip it.

### G. Prove the comparison can detect a difference

```bash
python scripts/week11_experiment.py --tasks fizzbuzz palindrome json-query
```

Runs all four conditions — A single model, B self-refinement, C the engine,
C' the ablation — and prints the comparison table with confidence intervals
and paired tests.

**Say this out loud when showing it:** the provider is a fixture with known
answers, not a model. It shows the pipeline works end to end. It says nothing
about any model's ability, and the script prints that reminder itself.

### H. The final report

```bash
python scripts/week12_final_check.py
```

The M4 gate. Re-measures everything and writes `docs/reports/findings.json`,
which the final report and deck are generated from. Finishes with the
hypothesis scorecard: H4 and H5 supported, H1–H3 marked *not yet testable*
because no model has been run.

---

## 3. How to see progress

### Git history — the week-by-week record

```bash
git log --oneline
git log --stat
```

Each commit is one week's deliverable with the milestone result in the message.

### The database — every run is traceable

```bash
python -m mawe.cli "Build a todo CLI" --db sqlite:///demo.db
python scripts/m1_demo.py --db
```

Every agent message, every version of the code, every review and every token
count is stored. That is what makes the Phase 4 cost analysis possible.

### CI — green checkmark on GitHub

Every push runs the full suite on Python 3.11, 3.12 and 3.13, plus all three
milestone checks. The Actions tab is the proof that it works on a machine
that is not yours.

---

## 4. What is actually built

| Layer | Module | What it does | State |
|---|---|---|---|
| Orchestration | `mawe/graph/` | LangGraph state machine; nodes are agent steps, edges are routing rules | working |
| Safety | `graph/policy.py` | Six exits, routed and reported by one policy function | working, exhaustively tested |
| Agents | `mawe/agents/` | PM, Developer, Reviewer with typed output contracts | all three complete; the Reviewer is grounded in sandbox execution |
| LLM access | `mawe/llm/` | Provider protocol + mock, Anthropic, OpenAI | mock complete; real adapters written, **never run against a live API** |
| Persistence | `mawe/db/` | 11 SQLAlchemy tables, SQLite → PostgreSQL | working |
| Sandbox | `mawe/sandbox/` | Subprocess execution with timeout and path containment | working; Docker never implemented |
| Memory | `mawe/memory.py` | Context summarisation under a token budget | working — 93.7% reduction at 80 iterations |
| Benchmark | `mawe/bench/` | 20 tasks, hidden tests, scoring, experiment runner | working; validated against its own references |
| Baselines | `mawe/baselines.py` | Conditions A and B for the comparison | working |
| Analysis | `bench/stats.py`, `bench/report.py` | Intervals, paired tests, comparison tables | working; checked against SciPy |

### The six ways a run ends

Approval, plus the five mechanisms that bound the loop when approval
never comes.

Every run exits with exactly one reason, and `graph/policy.py` decides the
route and the reason in the same function so the two cannot disagree.

1. **Approved** — the review passed.
2. **Iteration cap** — the configured maximum, default 5.
3. **No progress** — SHA-256 of the Developer's output matches the previous
   iteration, so the Developer is not responding to feedback.
4. **Oscillation** — the code returns to a version already seen (A→B→A),
   which consecutive-repeat detection alone does not catch.
5. **Repeated issues** — the reviewer refiles the same complaint, compared by
   a normalised fingerprint rather than by exact string.
6. **Error** — an agent failed irrecoverably.

Two more mechanisms shape the loop without ending it. The **severity
threshold** means only `critical` and `major` block approval, so a reviewer
that nitpicks formatting cannot stall the run; and **fallback routing** means
exiting without approval still delivers the best version with a warnings
report rather than failing.

`tests/test_loop_prevention.py` and `tests/test_loop_policy.py` cover these
exhaustively, and `scripts/week6_loop_stress.py` drives 100,000 randomised
adversarial sequences through the policy — none fail to terminate and none
exceed their cap.

---

## 5. Questions he will ask

**"Why a mock LLM instead of a real one?"**

> Two reasons. Cost — we have a $50–150 budget for the whole semester and we'd
> rather spend it on the Phase 4 benchmarks than on development. But mainly:
> I cannot make a real model return byte-identical code on demand, and that is
> exactly what is needed to prove the no-progress detector fires. The mock is
> how you test a termination guarantee. Real models come in for measuring
> *quality*, which is a different question and a different phase.

**"So none of this says anything about whether the code is good?"**

> Correct, and we say so in the README. What is proven right now is that the
> engine orchestrates correctly, always terminates, persists everything and
> produces runnable multi-file output. Whether multi-agent beats single-model
> on code quality is RQ1, measured in Weeks 9–12 against hidden tests.

**"Show me it running on a real model."**

> Not yet — no API key. The adapters are written (`llm/anthropic_provider.py`,
> `llm/openai_provider.py`) behind the same `LLMProvider` protocol the mock
> implements, so it is a config change, not a code change:
> `MAWE_PROVIDER=anthropic` plus a key in `.env`.
> Be honest that the adapters have not been exercised against a live API yet.

**"What's left?"**

> Week 5 finishes the Reviewer so it runs tests against the acceptance criteria
> rather than reporting what the model claims. Weeks 6–8 are memory management.
> Weeks 9–12 are the benchmark and the comparison.

**"Walk me through a design decision."**

> Be ready to explain any of these from the architecture doc: why four
> termination mechanisms instead of one, why progress is detected by hashing
> the generated files rather than by comparing text, why severity gates
> approval instead of the verdict alone, and why the loop-prevention policy
> lives in one pure function instead of being spread across the agents.

---

## 6. If something breaks during the demo

```bash
pip install -r requirements.txt
pip install -e .
python -m pytest -q
```

If `python -m mawe.cli` says "No module named mawe", you skipped
`pip install -e .`.

Fallback: `docs/poster/MAWE-URC-Poster-with-results.pdf` plus
`git log --oneline` tells the whole story without running anything.
