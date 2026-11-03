# MAWE — Conference abstract

**Multi-Agent AI Workflow Engine: Simulating an Autonomous Software Development Team**

Marco Perozo, Gabriel Marte, Lewdy Aquino, Alvin Almonte  
Department of Computer Science, Southwest Minnesota State University

> Generated from `findings.json`. Every figure matches what the code currently does.

---

## What an abstract is

One self-contained paragraph, normally 150–250 words, that makes sense to someone
who has not seen the poster. It answers five questions in order:

1. **What problem?**
2. **What did you build?**
3. **How did you evaluate it?**
4. **What did you find?**
5. **Why does it matter?**

It is not an introduction, and it does not describe the document. “This poster
presents our approach and discusses results” says nothing — the results themselves
say everything. Write it last, in the past tense, with no citations and no
undefined abbreviations.

---

## Full version — 244 words

*for a submission form that allows 250 words*

Most AI coding assistants are a single model answering a single prompt: one pass to understand, design, write and verify. We present MAWE, a Multi-Agent AI Workflow Engine that divides the work across three agents mirroring a software team — a Product Manager that turns a request into a specification with executable acceptance checks, a Developer that implements it, and a Code Reviewer that runs the code in a sandbox and either approves it or sends it back. The agents are orchestrated as an explicit state graph whose revision loop is bounded by five exit conditions, so it cannot run forever. We evaluate MAWE against three controls — a single model, a single model that critiques and revises its own code, and an ablation with context compression disabled — on a benchmark of 20 Python and JavaScript tasks carrying 181 hidden tests no agent sees, so scoring does not depend on the reviewing model. The benchmark is itself validated: every task is solvable, none is satisfied by a program that does nothing, and injected defects are detected 91% of the time. Two results are established by measurement. Across 100,000 randomised adversarial review sequences, no run failed to terminate and none exceeded its iteration cap; and compressing the revision history cuts prompt size by 94% at 80 iterations while leaving outcomes unchanged. Whether role separation improves correctness, and whether it justifies its token cost, requires a comparison against a live model that has not yet been run.

## Medium version — 140 words

*for a 150-word limit*

Most AI coding assistants are a single model answering a single prompt. We present MAWE, a Multi-Agent AI Workflow Engine that divides the work across three agents mirroring a software team: a Product Manager that writes a specification with executable acceptance checks, a Developer that implements it, and a Code Reviewer that runs the code in a sandbox and sends it back until it passes. We evaluate it against a single model, a self-refining single model, and an ablation, on 20 tasks with 181 hidden tests no agent sees, so scoring does not depend on the reviewing model. Across 100,000 randomised adversarial sequences, every run terminated inside its iteration cap, and compressing the revision history cut prompt size by 94% without changing outcomes. Whether role separation improves correctness, and at what cost, awaits a comparison against a live model.

## Elevator version — 69 words

*for a programme listing, or for answering “so what is it?” out loud*

MAWE divides AI code generation across three agents — a Product Manager, a Developer and a Code Reviewer that runs the code — instead of asking one model to do everything in one pass. On a 20-task benchmark with 181 hidden tests, we show the revision loop always terminates (100,000 adversarial sequences, none exceeding its cap) and that compressing the revision history cuts prompt size by 94% without changing outcomes.

---

## If you have to cut it further

Cut in this order, and stop as soon as it fits:

1. the benchmark-validation sentence (solvable / non-vacuous / 91% detection);
2. the names of the three control conditions, keeping “three controls”;
3. the description of what each agent does, keeping the three role names.

Do **not** cut the last sentence. An abstract that omits the fact that no live
model has been run would be claiming more than the work supports, and that is the
one error an examiner is certain to catch.
