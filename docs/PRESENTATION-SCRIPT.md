# MAWE Poster — Presentation Script

**Marco Perozo · Poster Production Demonstration · Tuesday, September 22, 2026**

Target: **3 minutes** of talking, then questions.
Have open: the poster PDF full screen, and VS Code behind it with the terminal ready.

---

## 0 · Opening (15 seconds)

> "Good morning. Our project is the **Multi-Agent AI Workflow Engine** — MAWE.
> The one-line version: you give it a plain-English idea, and a team of AI agents
> plans it, builds it, reviews it, and fixes it until it works.
> I'll walk the poster left to right."

*Don't say more here. Get to the poster.*

---

## 1 · Introduction & Problem Statement (35 seconds)

> "Everybody uses AI to write code now — Copilot, ChatGPT. But almost all of it is
> **one model, one prompt, one answer**. That model has to understand the request,
> design the solution, write the code, and check it — all in a single pass.
>
> That breaks down on anything real, for three reasons.
> One, it's too much for one pass.
> Two, **real software isn't built alone** — you have a product manager who clarifies,
> a developer who builds, QA who verifies. One prompt collapses all three and you lose
> the checks and balances.
> Three, there's **no iteration** — if the first answer is wrong, *you* have to catch it."

Point at the blue Research Question box:

> "So our question is: does splitting those roles actually produce better code —
> and what does it cost in tokens and time?"

---

## 2 · System Architecture & Methodology (45 seconds)

Point at the diagram, top to bottom:

> "Here's the pipeline. A prompt comes in — 'build a snake game'.
> The **PM agent** turns it into a structured spec with acceptance criteria.
> The **Developer agent** writes the actual Python or JavaScript against that spec.
> The **Reviewer agent** runs the code and its tests inside a Docker sandbox."

Point at the **red arrow**:

> "And this is the important part. If the reviewer rejects it, the code goes
> **back to the developer** — and around again. That loop is what makes it self-correct.
> That's what a single prompt can't do."

> "Underneath, we model the whole thing as a **state graph** — nodes are agent steps,
> edges are routing rules. That makes the control flow explicit and testable
> instead of hidden inside a prompt."

---

## 3 · Loop Prevention (30 seconds — this is your strongest CS content)

> "That loop is also the obvious way this thing fails. A reviewer that keeps rejecting
> for trivial reasons will run forever and burn your whole API budget.
> So we engineered **four** exits:
>
> One, a **hard iteration cap** — default five.
> Two, a **severity threshold** — only critical and major issues block approval;
> minor ones get reported but don't stop the build.
> Three, **no-progress detection** — we SHA-256 hash the developer's output, so if it
> hands back identical code, we know the loop is stuck and we exit.
> Four, **fallback routing** — if we exit without approval, we finalize the best version
> with a warnings report instead of just failing."

---

## 4 · Database Design (20 seconds)

> "Everything is persisted. Ten tables — every message between agents, every version of
> the code, every review, every token count. So any run is fully traceable from the
> original prompt to the final metrics, and we can query it later for the evaluation."

---

## 5 · Preliminary Results (40 seconds — what Dr. Hezy asked for)

> "We're at the end of **Week 1 of 12**, and **M1 is met** — the engine runs end to end.
>
> We validated it against a **scripted mock LLM** instead of a real API. That's
> deliberate, and it's in our proposal's testing strategy: it makes the tests
> deterministic and free, and it lets us prove things about the engine we genuinely
> could not prove otherwise."

Point at the results table:

> "Three scenarios, and each one forces a different exit path.
> The **happy path** — reject, reject, then approve on a minor issue — two iterations.
> A **stuck developer** returning identical code — caught by the hash, exits at two.
> A **reviewer that never approves** — runs to the cap and stops at five.
>
> Three out of three terminated. No hangs. Twenty messages, nine code artifacts
> and eight reviews written to SQLite."

Point at the empty table below it:

> "This one is intentionally blank. Those are the **real-LLM quality benchmarks** —
> twenty tasks with hidden tests, four conditions including a single-model baseline.
> That's Phase 4, Weeks 9 through 12. I'm not going to put numbers there until we
> have measured them."

---

## 6 · Close (15 seconds)

> "So: engine running and provably terminating in Week 1; the three agent roles
> get built out in Weeks 3 to 5; memory management Weeks 6 to 8; and the
> comparison against single-model generation in Weeks 9 to 12.
>
> Happy to take questions."

---

# Likely questions — and your answers

**"Why a mock LLM? Why not a real one?"**
> "Two reasons. Cost — we have a 50-to-150-dollar budget for the whole semester, and
> we'd rather spend it on the Phase 4 benchmarks than on development.
> But mainly: I can't make a real model return **byte-identical code on demand**,
> which is exactly what I need to prove the no-progress detector fires. The mock is
> how you test termination guarantees. Real models come in for quality measurement."

**"So these numbers don't say anything about code quality."**
> "Correct, and the poster says that explicitly. These measure the **engine** —
> orchestration, loop prevention, persistence. Quality is Phase 4."

**"Can I see it run?"**
> Switch to VS Code. `python mawe_prototype.py --db`
> "One second. Those are the exact numbers on the poster."

**"What if the multi-agent version turns out to be no better than a single model?"**
> "That's still a valid result and we'll report it honestly. The interesting number
> isn't pass rate alone, it's **cost per successful task** — if we turn a 50% success
> rate into 85% for twice the tokens, that's still cheaper per working program.
> We also run a self-refinement baseline that isolates whether it's the *iteration*
> that helps or the *role separation*."

**"Why LangGraph and not CrewAI?"**
> "LangGraph models the workflow as an explicit state graph, so routing is testable.
> We kept the orchestration layer thin, so switching is feasible if we need to."

**"Who's doing what?"**
> "I lead the orchestration and loop prevention. Gabriel does agent design and prompt
> engineering. Lewdy has the database, sandbox and CI. Alvin owns the benchmark suite
> and the statistical analysis."

---

# Before you walk in

- [ ] Run `python mawe_prototype.py --db` once so the output is already in your scroll-back
- [ ] Poster PDF open and full screen
- [ ] Know these four numbers cold: **2 / 2 / 5 iterations, 3 of 3 terminated**
- [ ] Know the three exit reasons: **approved, no_progress, iteration_cap**

**If you only get one minute:** problem → the three roles and the red arrow → "M1 is met,
here are the termination numbers, quality benchmarks are Phase 4."
