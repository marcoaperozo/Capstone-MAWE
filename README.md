# MAWE — Multi-Agent AI Workflow Engine

**Simulating an Autonomous Software Development Team**

Capstone project · Department of Computer Science · Southwest Minnesota State University · Fall 2026
Marco Perozo · Gabriel Marte · Lewdy Aquino · Alvin Almonte

---

## What this is

Most AI coding tools are one model, one prompt, one answer — the model has to
understand the request, design the solution, write the code and verify it in a
single pass. MAWE splits that across three specialised agents that mirror a real
software team, and loops until the code passes review:

```
prompt ──> Product Manager ──> Developer ──> Code Reviewer ──> finalize
                                   ^              |
                                   └──────────────┘
                                 reject & iter < max & progress
```

The research question is not *"can agents write code"* but **does role separation
actually produce more correct, more requirement-compliant software than a single
model — and what does it cost in tokens and time?**

## Quick start

```bash
git clone <this repo>
cd MAWE-Capstone
pip install -r requirements.txt
pip install -e .
pytest
```

The test suite runs against a mock provider, so **no API key is needed** and it
costs nothing.

Run the pipeline end to end:

```bash
python -m mawe.cli "Build a terminal snake game"
```

Milestone checks — each one is a measured claim, not an assertion:

```bash
python scripts/m1_demo.py            # the Week 1-2 standalone prototype
python scripts/week3_spec_check.py   # PM produces valid specs on 5 prompts
python scripts/week4_dev_check.py    # generated code is written and executed
python scripts/week5_m2_check.py     # the reviewer cannot be talked out of a failure
python scripts/week6_loop_stress.py  # 100,000 adversarial runs, all terminate
python scripts/week7_memory_check.py # context stays inside the token budget
python scripts/week8_m3_check.py     # M3: every layer still works together
python scripts/week9_bench_check.py  # the 20-task benchmark is a valid instrument
python scripts/week10_baseline_check.py  # the four-condition comparison runs
python scripts/week11_experiment.py      # the full sweep, with statistics
python scripts/week12_final_check.py     # M4: the final gate, and the report's figures
```

Optional web UI:

```bash
pip install fastapi uvicorn
uvicorn mawe.web.app:app --reload
```

## Project status

| Phase | Weeks | Deliverable | Status |
|---|---|---|---|
| 1. Setup & prototyping | 1–2 | Repo, CI, database schema, two-agent pipeline on a LangGraph state graph | **done** |
| 2. Role implementation | 3–5 | Product Manager, Developer and Reviewer agents with typed hand-offs | **done** |
| 3. Memory & state | 6–8 | Loop hardening, context summarisation, integration tests, web UI | **done — engine v1.0 (M3)** |
| 4. Testing & evaluation | 9–12 | Benchmark suite, single-model baseline, final report | done — M4 |

## Layout

```
src/mawe/
  config.py          settings from .env
  db/                SQLAlchemy models + RunRepository  (11 tables)
  llm/               provider abstraction: mock, Anthropic, OpenAI
  agents/            Product Manager, Developer, Reviewer + output parsing
  graph/             LangGraph state graph and the routing rules
  graph/policy.py    the loop-prevention policy, in one testable function
  memory.py          context compression under a token budget
  sandbox/           subprocess runner for generated code
  agents/checks.py   executable acceptance checks the Reviewer runs
  bench/             Phase 4: 20 benchmark tasks, hidden tests, scoring
  baselines.py       conditions A and B: one model, with and without retries
  bench/stats.py     the statistics, in the standard library
  bench/report.py    sweeps -> tables, intervals and paired tests
  web/               optional FastAPI front end
  cli.py             command-line entry point
tests/               unit + integration, all against the mock provider
scripts/             milestone demos
docs/                architecture, poster, presentation script
```

## Using a real model

Everything runs on the mock by default. To use a real provider:

```bash
cp .env.example .env
# edit .env:
#   MAWE_PROVIDER=anthropic
#   ANTHROPIC_API_KEY=sk-ant-...
pip install anthropic
```

`.env` is gitignored. **Never commit an API key.**

## How the Reviewer avoids rubber-stamping

An acceptance criterion written in English can simply be *claimed* to pass by
a model that never ran anything. So the Product Manager also emits executable
checks — an invocation and the output it must produce — and the Reviewer runs
them in the sandbox before forming a verdict. Where the model and the
measurement disagree, the measurement wins:

- a model approval of code that failed a check is overridden to **reject**;
- a blocking reject is downgraded to **minor** once every criterion has a
  check and all of them pass, so a reviewer that objects to naming cannot
  stall the loop;
- that downgrade is **withheld** when some criteria have no check, because a
  criterion nobody tested can still be genuinely unmet.

## How the benchmark is validated

Phase 4 compares the engine against single-model baselines on 20 tasks — 7 easy,
8 medium, 5 hard, across Python and JavaScript — each with hidden tests that no
agent ever sees. Scoring is therefore independent of the LLM reviewer: a run can
be approved by the Reviewer and still score zero.

That only means something if the benchmark itself is sound, so three properties
are measured rather than asserted (`scripts/week9_bench_check.py`):

- **solvable** — a reference solution for every task passes all 181 hidden tests;
- **non-vacuous** — a program that starts and does nothing succeeds on 0 of 20
  tasks, passing only the 5 empty-input cases it genuinely satisfies;
- **discriminating** — single defects injected into the reference solutions are
  caught 91.4% of the time (mutation score, survivors itemised).

Mutation testing found two real weaknesses while it was being built. Error-path
tests all asserted "exit status 1", which an uncaught exception also produces,
so deleting an input guard left the tests green — the harness now rejects a
traceback where the task asked for an error message. The same pass found
untested boundaries in four tasks, which is why the suite has 181 tests and not
169.

## The four conditions

The research question is comparative, so the engine is measured against
controls rather than on its own:

| | condition | what it is |
|---|---|---|
| A | single model | one call, no iteration, no review |
| B | self-refinement | one model that critiques and revises its own code |
| C | multi-agent engine | Product Manager, Developer, Reviewer |
| C' | ablation | the engine with context summarisation switched off |

B is the control that matters. Without it, "multi-agent beats one call" could
just be "more attempts beat one attempt". B iterates with the same cap and the
same model, so any advantage C shows over B is not simply persistence.

One confound is worth stating plainly: C differs from B in **two** ways, role
separation and sandbox-grounded review, so a gain over B cannot be attributed
to either one by this design alone. Giving B the sandbox would stop it
isolating iteration, so the confound is reported rather than removed.

Everything outside the conditions is shared deliberately — same provider, same
temperature, same iteration cap, same file parser, same token accounting, same
hidden-test scoring. The baselines get none of the engine's machinery: no
specification, no executable checks, no sandbox evidence, and no loop
prevention, so B burns its whole budget on a model that never settles.

`scripts/week10_baseline_check.py` validates the comparison against a fixture
whose answers are known in advance, which is the only way to tell "the models
did badly" from "the plumbing is broken" before spending on real API calls.

## How the results are analysed

Two choices here are methodological rather than technical, and both are easy
to get wrong in a way that produces a confident number instead of an error.

**The unit of analysis is the task, not the run.** A sweep of 20 tasks with 3
repetitions produces 60 rows per condition, and running the paired tests over
all 60 would treat three runs of one task as three independent observations.
That trebles n and shrinks every interval by about 1.7 for free. Repetitions
are averaged within a task first; they measure *stability*, which is reported
separately, and a task counts as solved when it succeeded in more than half of
its repetitions.

**The test follows the metric.** The proposal says "paired t-test or Wilcoxon
signed-rank", which is right for tokens and pass rate and wrong for the
headline. Task success is binary, so nearly every paired difference is zero,
and the signed-rank test discards zeros — with 20 tasks and 3 disagreements it
computes a p-value from n = 3 while looking like a 20-task result. For paired
binary outcomes the correct test is McNemar's, exactly, on the discordant
pairs, and that is what the report uses. It also makes the real sample size
visible instead of implied.

Several comparisons come out of one sweep (C vs A, C vs B, B vs A, C vs C'), so
p-values are Holm-corrected. Effect sizes are reported alongside, because at
n = 20 a significant difference can still be a tiny one.

The statistics are implemented in the standard library and checked against
SciPy in `tests/test_stats.py` on any machine that has it — so CI stays light
and the implementations are verified rather than assumed.

## Where the project ended up

| | hypothesis | verdict |
|---|---|---|
| H4 | every run terminates; under 10% exit by cap | **supported** |
| H5 | summarisation cuts context ≥40% without changing outcomes | **supported** |
| H1 | role separation produces more correct software | **not yet testable** |
| H2 | role separation produces better spec coverage | **not yet testable** |
| H3 | the improvement is worth its cost per success | **not yet testable** |

H1–H3 need a real API key. The instrument that answers them is built and
validated — the benchmark, the baselines, the scoring, the statistics — but no
sweep against a model has been run, and the Anthropic and OpenAI adapters have
never executed against a live API. That is the project's main limitation and
the first thing [`docs/reports/FINAL-REPORT.md`](docs/reports/FINAL-REPORT.md)
says.

Every figure in the report and its deck is generated from
`docs/reports/findings.json`, which `scripts/week12_final_check.py` writes from
live measurements. Nothing is typed in. That rule exists because a Week 8 deck
once claimed 273 passing tests when the suite had 255: the figure had been
copied from a terminal and the suite moved underneath it.

## Why a mock provider

It is not a shortcut around real testing — it is how we test properties a real
model cannot be made to exhibit on demand. Proving the no-progress exit fires
requires the Developer to return byte-identical code twice; no real LLM can be
instructed to do that reliably. The mock makes termination guarantees testable,
deterministic and free. Model *quality* is measured separately in Phase 4
against real APIs with hidden tests.

## Documentation

- [`docs/DEMO-GUIDE.md`](docs/DEMO-GUIDE.md) — **how to demo this**: what to run, in what order, and what each command proves
- [`docs/architecture.md`](docs/architecture.md) — layers, state graph, agent contracts, loop prevention
- [`docs/MAWE-CONTEXT.md`](docs/MAWE-CONTEXT.md) — full proposal content
- [`docs/poster/`](docs/poster) — URC conference poster (48×36)
- [`docs/reports/FINAL-REPORT.md`](docs/reports/FINAL-REPORT.md) — the final report, generated from measured figures
