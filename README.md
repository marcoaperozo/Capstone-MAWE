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
python scripts/m1_demo.py           # all three termination paths fire
python scripts/week3_spec_check.py  # PM produces valid specs on 5 prompts
python scripts/week4_dev_check.py   # generated code is written and executed
```

## Project status

| Phase | Weeks | Deliverable | Status |
|---|---|---|---|
| 1. Setup & prototyping | 1–2 | Repo, CI, database schema, two-agent pipeline on a LangGraph state graph | **done** |
| 2. Role implementation | 3–5 | Product Manager, Developer and Reviewer agents with typed hand-offs | **PM + Developer done** (Weeks 3–4), Reviewer is Week 5 |
| 3. Memory & state | 6–8 | Context summarisation, token budget | planned |
| 4. Testing & evaluation | 9–12 | Benchmark suite, single-model baseline, final report | planned |

## Layout

```
src/mawe/
  config.py          settings from .env
  db/                SQLAlchemy models + RunRepository  (11 tables)
  llm/               provider abstraction: mock, Anthropic, OpenAI
  agents/            Product Manager, Developer, Reviewer + output parsing
  graph/             LangGraph state graph and the routing rules
  sandbox/           subprocess runner for generated code
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
