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

### A. Prove the whole thing works — 114 tests, ~8 seconds

```bash
pytest -q
```

This is the strongest single thing you can show. No API key, no network, no
cost. If he wants detail:

```bash
pytest -v
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
| Safety | `graph/workflow.py` | Four independent termination mechanisms | working, exhaustively tested |
| Agents | `mawe/agents/` | PM, Developer, Reviewer with typed output contracts | PM + Dev complete; Reviewer thin |
| LLM access | `mawe/llm/` | Provider protocol + mock, Anthropic, OpenAI | mock complete; real adapters written, untested against live APIs |
| Persistence | `mawe/db/` | 11 SQLAlchemy tables, SQLite → PostgreSQL | working |
| Sandbox | `mawe/sandbox/` | Subprocess execution with timeout and path containment | working; Docker is Phase 2 |
| Memory | — | Context summarisation | **not built — Weeks 6–8** |
| Evaluation | — | Benchmark suite, baselines | **not built — Weeks 9–12** |

### The four termination mechanisms

1. **Hard iteration cap** — default 5, configurable.
2. **Severity threshold** — only `critical` and `major` block approval. A
   reviewer that nitpicks formatting cannot stall the loop.
3. **No-progress detection** — SHA-256 of the Developer's output. If the same
   code comes back twice, the Developer is not responding to feedback and the
   loop exits.
4. **Fallback routing** — exiting without approval does not fail the run; it
   finalizes the best version with a warnings report.

`tests/test_loop_prevention.py` sweeps 8 iteration counts × 4 severities ×
2 verdicts × repeated/changed code and asserts that no reachable state loops
forever.

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

**"How do I know you wrote this and not an AI?"**

> Fair question, and the honest answer is that it was written with AI
> assistance — which is noted in the commit trailers. What matters for the
> capstone is that the design decisions are defensible: why four termination
> mechanisms instead of one, why hash-based progress detection, why the mock,
> why severity gates approval. Be ready to explain any of those from the
> architecture doc.

---

## 6. If something breaks during the demo

```bash
pip install -r requirements.txt
pip install -e .
pytest -q
```

If `python -m mawe.cli` says "No module named mawe", you skipped
`pip install -e .`.

Fallback: `docs/poster/MAWE-URC-Poster-with-results.pdf` plus
`git log --oneline` tells the whole story without running anything.
