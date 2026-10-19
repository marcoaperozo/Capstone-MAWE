# MAWE — Capstone Project Context (canonical reference)

Source files ingested (2026-09-22):
- `00_Full_Capstone_Proposal (1).docx` → full text in [docx_dump.txt](docx_dump.txt) (484 lines, all 12 sections + tables)
- `MAWE Capstone Presentation (1).pptx` → 14 slides in [pptx_dump.txt](pptx_dump.txt)
- `Capstone Proyect- Marco Perozo (1) (1).pdf` → identical (same MD5) to the original 7-slide deck; summary in [capstone-brief.md](capstone-brief.md)

## Identity
- **Full title:** Multi-Agent AI Workflow Engine: Simulating an Autonomous Software Development Team
- **Short name:** MAWE
- **Area:** AI / Software Engineering / LLM Orchestration
- **Team:** Marco Perozo (17363926, project lead — orchestration/LangGraph state graph, loop prevention, integration), Gabriel Marte (16988332 — agent design & prompt engineering, LLM API integration), Lewdy Aquino (17172025 — DB & persistence, sandbox execution, CI/CD), Alvin Almonte (17194894 — benchmark suite, evaluation scripts, metrics, stats, docs)
- **Proposal dated:** September 15, 2026. Week 1 starts Monday, Sept 21, 2026; 12 weeks → ends Dec 13, 2026.

## Core concept
User prompt → **PM agent** (structured spec + acceptance criteria) → **Dev agent** (Python/JS source files) → **Reviewer/QA agent** (runs code + tests in sandbox, emits JSON verdict/severity/issues) → loop back to Dev until approved or a safety limit hits → finalize.

Routing: `START → PM.plan → Dev.implement → Reviewer.review → [approve → finalize] | [reject ∧ iter < max ∧ progress → Dev.implement] | [reject ∧ (iter = max ∨ no progress) → finalize_with_warnings] → END`

## Six layers
Orchestration (LangGraph primary / CrewAI alt, state graph) · Agent (role prompts + tools) · Safety (iteration caps, exit conditions, fallback routing) · Memory (rolling summarization + pruning) · Persistence (SQLite dev → PostgreSQL, SQLAlchemy) · Evaluation (benchmarks vs single-model baseline)

## Research question
Does a role-based multi-agent workflow (PM → Dev → Reviewer with iteration loop) produce more correct and more requirement-compliant software than a single LLM on the same task, and at what cost in tokens and time?
Secondary: (a) how to reliably prevent infinite review/fix loops without sacrificing quality; (b) how to manage conversational memory so long runs stay within token limits.

## Stack (concrete)
Python 3.11+ · LangGraph (primary) / CrewAI · OpenAI / Anthropic / Google API SDKs · Node.js 20+ for JS targets · Docker Desktop or subprocess-with-timeout sandbox · pytest + Jest · SQLite → PostgreSQL 15+ via SQLAlchemy · FastAPI + simple HTML/React UI (optional) · python-dotenv · Python logging + LangSmith (optional) · Git/GitHub + GitHub Actions · VS Code/PyCharm · Markdown/Word/draw.io.
No GPU. Min: dual-core, 8 GB RAM, 10 GB free. Rec: quad-core, 16 GB, 20 GB SSD. Budget: USD 50–150 of API spend for the semester.

## Database schema (10 tables)
`users`, `projects`, `agents`, `benchmark_tasks`, `runs`, `messages`, `specifications`, `code_artifacts`, `reviews`, `memory_summaries`, `evaluation_results`.
Key relations: USER ──< PROJECT ──< RUN ──< {MESSAGE >── AGENT, SPECIFICATION, CODE_ARTIFACT, REVIEW, MEMORY_SUMMARY, EVALUATION_RESULT}; BENCHMARK_TASK ──< RUN.
Notable columns: `runs.mode` = multi_agent | single_model; `runs.termination_reason` = approved | iteration_cap | no_progress | error; `code_artifacts.content_hash` (SHA-256) drives no-progress loop detection; token counts per message aggregated per run for cost accounting. 3NF. Full column-level definitions in docx_dump.txt lines ~150–260.

## Loop prevention (4 mechanisms)
1. Hard iteration cap (default 5). 2. Severity threshold — only critical/major block approval. 3. No-progress detection via code hash / repeated issues. 4. Fallback routing → "finalize with warnings".

## Memory management
Keep latest spec + latest code + latest review in full context; summarize older iterations into a compact progress log stored in `memory_summaries`; persist all raw messages in the DB regardless.

## Timeline
| Phase | Weeks | Dates | Deliverable | Milestone |
|---|---|---|---|---|
| 1. Setup & Prototyping | 1–2 | Sep 21 – Oct 4 | Two-agent communication pipeline | M1 |
| 2. Role Implementation | 3–5 | Oct 5 – Oct 25 | PM/Dev/Reviewer prompts + hand-offs | M2 |
| 3. Memory & State | 6–8 | Oct 26 – Nov 15 | Summarization + loop prevention | M3 (engine v1.0) |
| 4. Testing & Evaluation | 9–12 | Nov 16 – Dec 13 | Benchmarks vs single models, final report | M4 |
Week-by-week breakdown is in docx_dump.txt (§10.2).

## Experimental evaluation
- **RQ1–RQ5 / H1–H5** — correctness, spec coverage, cost, loop termination (100% terminate, <10% by cap), summarization (≥40% context reduction, no significant pass-rate drop).
- **Benchmark:** ≥20 tasks with hidden tests — 7 easy / 8 medium / 5 hard, Python + JavaScript.
- **Conditions:** A = single model; B = single model with self-refinement; C = multi-agent engine; C′ = engine with summarization disabled (ablation). Same LLM + temperature across all. 3 repetitions → ~240 runs.
- **Metrics:** pass rate %, task success %, spec coverage %, iterations, total tokens, cost USD, latency s, termination reason, context reduction %.
- **Stats:** means + 95% CI, paired t-test or Wilcoxon signed-rank.

## Discussion highlights
Contributions: reference implementation, practical loop-prevention patterns, memory strategy, cost-per-success evidence, reusable benchmark. Key framing: not "is it better?" but "is the improvement worth the cost?" — cost per *successful* task. Condition B isolates iteration from role separation. Limitations: LLM reviewer is fallible (hidden tests decouple scoring from it), small-to-medium tasks only, model-dependent results, only ~3 repetitions, functional correctness only (not style/security/maintainability).

## ⚠️ Known gaps
- **No in-text citations and no APA reference list anywhere in the .docx or the deck**, despite the professor explicitly requiring them. Named sources currently sit as bare mentions only: LangGraph, CrewAI, AutoGen, MetaGPT, GitHub Copilot, ChatGPT, Cursor, GPT/Claude/Gemini.
- The deck's only source credits are two stock-image URLs on slide 14.
- Stack names OpenAI/Anthropic/Google generically; no specific model IDs chosen yet.
