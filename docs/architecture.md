# MAWE Architecture

**Multi-Agent AI Workflow Engine — Simulating an Autonomous Software Development Team**
Week 1 deliverable (architecture document). Last updated: Week 4.

---

## 1. Overview

MAWE turns a short natural-language prompt into working, reviewed source code by
routing it through three specialised LLM agents that mirror a real software team:

```
prompt ──> Product Manager ──> Developer ──> Code Reviewer ──> finalize
                                   ^              |
                                   └──────────────┘
                                   reject & iter < max & progress
```

The contribution is not "use several agents" — it is making that loop
**provably terminate** and **measurably cheap**, which is what the evaluation in
Phase 4 tests.

## 2. Layers

| Layer | Module | Responsibility |
|---|---|---|
| Orchestration | `mawe.graph` | LangGraph `StateGraph`; nodes are agent steps, edges are routing rules |
| Agent | `mawe.agents` | Role prompts, output parsing, artifact contracts |
| LLM access | `mawe.llm` | Provider-agnostic `LLMProvider` protocol; mock / Anthropic / OpenAI |
| Safety | `mawe.graph.workflow` | Iteration cap, severity threshold, no-progress detection, fallback routing |
| Memory | `mawe.graph.state` | Context budget accounting; rolling summarisation (Phase 3) |
| Persistence | `mawe.db` | SQLAlchemy models + `RunRepository`; SQLite → PostgreSQL |
| Sandbox | `mawe.sandbox` | Executes generated code with time, output and import limits |

## 3. The state graph

`mawe.graph.workflow.build_graph()` returns a compiled LangGraph with four nodes:

| Node | Reads from state | Writes to state |
|---|---|---|
| `plan` | `prompt` | `spec`, `acceptance_criteria` |
| `develop` | `spec`, `review_feedback` | `files`, `code_hash` |
| `review` | `spec`, `files` | `verdict`, `severity`, `feedback`, test counts |
| `finalize` | everything | `status`, `termination_reason` |

Routing out of `review` is a single conditional edge implementing:

```
approve                                   -> finalize
reject & severity not blocking            -> finalize   (approved with notes)
reject & no progress                      -> finalize   (no_progress)
reject & iteration >= max_iterations      -> finalize   (iteration_cap)
reject & otherwise                        -> develop
```

Because routing is a pure function of the state dict, every branch is unit
testable without calling a model. See `tests/test_loop_prevention.py`.

## 4. Loop prevention

Four independent mechanisms, any one of which can end the loop:

1. **Hard iteration cap** — `settings.max_iterations`, default 5.
2. **Severity threshold** — only `critical` and `major` block approval; `minor`
   issues are recorded in the review but do not cause another cycle.
3. **No-progress detection** — the SHA-256 of the concatenated developer output
   is compared against every previous iteration. A repeat means the Developer is
   not responding to feedback, and the loop exits.
4. **Fallback routing** — exiting without approval does not fail the run; it
   routes to `finalize` and marks the result `max_iterations`, returning the best
   version produced along with a warnings report.

Every exit sets `termination_reason` to one of
`approved | iteration_cap | no_progress | error`, which is the field the Phase 4
evaluation aggregates for RQ4.

## 5. Agent contracts

Each agent has a **typed output contract** so the next node never has to parse
free text:

- **Product Manager** → `Specification { summary, language, files[], features[],
  constraints[], acceptance_criteria[] }`. Criteria are numbered and testable;
  they become the checklist the Reviewer scores against.
- **Developer** → `list[GeneratedFile { path, language, content }]`. Multi-file
  output; the developer is instructed to address every numbered review item.
- **Code Reviewer** → `Review { verdict, severity, issues[], tests_passed,
  tests_failed }`. Structured so the routing function reads fields, not prose.

Parsing is defensive: `mawe.agents.parsing` extracts fenced JSON or fenced code
blocks and raises a typed error the graph records rather than crashing.

## 6. LLM provider abstraction

```python
class LLMProvider(Protocol):
    name: str
    def complete(self, system: str, user: str, **kw) -> LLMResponse: ...
```

`LLMResponse` carries `text`, `prompt_tokens` and `completion_tokens`, so token
accounting is identical whether the backend is a real API or the mock.

`MockProvider` is **not** a stub that returns nothing — it is a scripted backend
used for deterministic, zero-cost integration tests. It is how we test properties
that a real model cannot be made to exhibit on demand, such as returning
byte-identical code twice to trigger the no-progress exit.

## 7. Database

Eleven tables; full column definitions in the proposal, section 7. Key points:

- `runs.mode` separates `multi_agent` from the `single_model` and `self_refine`
  baselines, so the Phase 4 comparison is a query, not a separate pipeline.
- `code_artifacts.content_hash` backs the no-progress exit condition.
- Token counts are stored per message and aggregated per run, which is what makes
  cost-per-successful-task computable.
- `agents.system_prompt` and `agents.version` are stored so any past run is
  reproducible against the exact prompt that produced it.

## 8. Sandbox

Generated code is never executed in the host process. `mawe.sandbox.runner`
runs it as a subprocess with a wall-clock timeout, captured stdout/stderr, a
working directory confined to a temp dir, and output truncation. Docker with no
network is the Phase 2 hardening target; the subprocess runner is the portable
fallback so CI works without a Docker daemon.

## 9. Testing strategy

| Level | What it covers | LLM |
|---|---|---|
| Unit | routing rules, loop prevention, parsing, token accounting, DB writes | none |
| Integration | full `plan → develop → review` pipeline | mock |
| End-to-end | real generation quality | real API, run manually before milestones |

CI (`.github/workflows/ci.yml`) runs unit + integration on every push. No API key
is required, so the suite is free and deterministic.

## 10. Build order

| Phase | Weeks | Deliverable | State |
|---|---|---|---|
| 1. Setup & prototyping | 1–2 | Repo, CI, schema, two-agent pipeline on the graph | done |
| 2. Role implementation | 3–5 | PM, Developer, Reviewer agents and hand-offs | PM + Dev done; Reviewer next |
| 3. Memory & state | 6–8 | Summarisation, context budget | planned |
| 4. Testing & evaluation | 9–12 | Benchmark suite, baselines, final report | planned |
