# MAWE Architecture

**Multi-Agent AI Workflow Engine — Simulating an Autonomous Software Development Team**
Week 1 deliverable (architecture document). Last updated: Week 8, engine v1.0.

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
| Memory | `mawe.memory` | Context budget accounting and structured compression |
| Persistence | `mawe.db` | SQLAlchemy models + `RunRepository`; SQLite → PostgreSQL |
| Sandbox | `mawe.sandbox` | Executes generated code with time, output and path limits |
| Checks | `mawe.agents.checks` | Executable acceptance checks the Reviewer runs |
| Web | `mawe.web` | Optional FastAPI front end over the same engine |

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

All of the policy lives in `mawe.graph.policy.LoopPolicy.decide()`, which
returns the next node *and* the termination reason together. Routing and
reporting were originally two mirrored functions; one call now produces both so
they cannot drift apart.

Five independent mechanisms, any one of which can end the loop:

1. **Hard iteration cap** — `settings.max_iterations`, default 5. The backstop
   that always holds.
2. **Severity threshold** — only `critical` and `major` block approval; `minor`
   issues are recorded but do not cause another cycle.
3. **No-progress detection** — the SHA-256 of the generated files. Two
   consecutive identical hashes mean the Developer is not responding to
   feedback, and the loop exits.
4. **Oscillation detection** — a hash seen *earlier* in the run, not just
   immediately before. Catches a Developer cycling A → B → A, which
   consecutive-repeat detection misses entirely and which otherwise burns the
   full iteration budget.
5. **Repeated-issue detection** — a normalised fingerprint of the Reviewer's
   complaints. Renumbering, reordering or re-casing the same objections does
   not read as progress.

**Fallback routing** underpins all of them: exiting without approval does not
fail the run. It routes to `finalize`, returns the best version produced, and
attaches a warnings report explaining which mechanism fired.

Every exit sets `termination_reason` to one of `approved | iteration_cap |
no_progress | oscillation | repeated_issues | error`, which is the field the
Phase 4 evaluation aggregates for RQ4.

Because `decide()` is a pure function of the run state with no I/O,
`scripts/week6_loop_stress.py` drives 100,000 randomised adversarial sequences
through it in about a second. None failed to terminate; none exceeded its cap.

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

## 6. Grounding the review in execution

A criterion written in English can be claimed to pass by a model that never ran
anything, so the specification also carries **executable checks**: an
invocation (argv, stdin) and the output it must produce (exact, substring or
regex, plus an exit code), each tied to a criterion number.

The Reviewer runs every check in the sandbox *before* asking the model, shows
it the evidence, then reconciles the two. The measurement wins:

| Situation | Outcome |
|---|---|
| Model approves, a check failed | overridden to **reject**; `critical` on a crash or timeout |
| Model rejects, all checks pass, **every** criterion is covered | downgraded to **minor** so the loop can finish |
| Model rejects, all checks pass, some criteria **uncovered** | severity **stands** — an untested criterion may genuinely be unmet |
| Model output unparseable | verdict comes from the evidence alone |

`tests_passed` / `tests_failed` always come from the sandbox, never from the
model's self-report.

The third row matters: evidence can only override where evidence exists.
Downgrading on partial coverage would quietly reintroduce the false approval
this mechanism exists to prevent.

## 7. Memory management

`mawe.memory.MemoryManager` builds the history section of the Developer prompt
under an explicit token budget:

- the latest iteration keeps its real source, because that is what is being
  edited;
- older iterations collapse into a **progress log** — one line each recording
  files, line count, code hash, verdict, severity and issues, plus a roll-up of
  complaints that keep recurring;
- over budget, the oldest entries are dropped and the prompt says how many;
- raw messages are still persisted — they are dropped from the *prompt*, not
  from the record.

Compression is **structured, not generative**. A model-written summary costs
tokens, is non-deterministic and can silently drop the detail that mattered.
The fields a later iteration needs are known in advance, so they are recorded
exactly and for free. `LLMSummariser` implements the generative alternative
behind the same interface for the Phase 4 comparison.

Measured over 80 iterations: 52,494 tokens uncompressed against 3,316
compressed — a 93.7% reduction that never exceeds the budget. Both arms are
rendered and measured, so the figure is a measurement, not an estimate.

## 8. LLM provider abstraction

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

## 9. Database

Eleven tables; full column definitions in the proposal, section 7. Key points:

- `runs.mode` separates `multi_agent` from the `single_model` and `self_refine`
  baselines, so the Phase 4 comparison is a query, not a separate pipeline.
- `code_artifacts.content_hash` backs the no-progress exit condition.
- Token counts are stored per message and aggregated per run, which is what makes
  cost-per-successful-task computable.
- `agents.system_prompt` and `agents.version` are stored so any past run is
  reproducible against the exact prompt that produced it.

## 10. Sandbox

Generated code is never executed in the host process. `mawe.sandbox.runner`
runs it as a subprocess with a wall-clock timeout, captured stdout/stderr, a
working directory confined to a temp dir, and output truncation. Docker with no
network is the Phase 2 hardening target; the subprocess runner is the portable
fallback so CI works without a Docker daemon.

## 11. Testing strategy

| Level | What it covers | LLM |
|---|---|---|
| Unit | routing rules, loop prevention, parsing, token accounting, DB writes | none |
| Integration | full `plan → develop → review` pipeline | mock |
| End-to-end | real generation quality | real API, run manually before milestones |

CI (`.github/workflows/ci.yml`) runs unit + integration on every push. No API key
is required, so the suite is free and deterministic.

## 12. Build order

| Phase | Weeks | Deliverable | State |
|---|---|---|---|
| 1. Setup & prototyping | 1–2 | Repo, CI, schema, pipeline on the graph (M1) | done |
| 2. Role implementation | 3–5 | PM, Developer, Reviewer agents and hand-offs (M2) | done |
| 3. Memory & state | 6–8 | Loop hardening, summarisation, integration, web UI (M3) | done — v1.0 |
| 4. Testing & evaluation | 9–12 | Benchmark suite, baselines, final report (M4) | next |
