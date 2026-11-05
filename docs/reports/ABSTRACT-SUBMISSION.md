# Multi-Agent AI Workflow Engine: Simulating an Autonomous Software Development Team

Marco Perozo, Gabriel Marte, Lewdy Aquino, Alvin Almonte

Department of Computer Science, Southwest Minnesota State University

## Abstract

Most AI coding assistants work as a single model answering a single prompt:
one pass to understand the request, design a solution, write the code, and
check its own work. This project asks whether dividing that work among
specialized agents produces more correct software, and at what cost.

We built MAWE, a Multi-Agent AI Workflow Engine that splits development across
three agents. A Product Manager turns a plain-language request into a
specification with acceptance criteria and runnable checks. A Developer writes
the code. A Code Reviewer runs that code in a sandbox and compares its output
against the specification before approving it or sending it back. Because the Reviewer executes the
program instead of reading it, a model cannot approve code that demonstrably
fails.

Two problems follow. Because two agents can disagree indefinitely, the loop
has five independent exit conditions; across 100,000 randomized adversarial
sequences, every run terminated within its iteration limit. Because the
conversation grows with every revision, older iterations are compressed into a
structured log, cutting prompt size by 94 percent at 80 iterations without
changing the outcome.

For comparison against simpler approaches, we built a benchmark of 20 Python
and JavaScript tasks with 181 hidden tests the agents never see, so scoring
does not depend on the reviewing model. The benchmark was validated rather
than assumed: every task is solvable, none can be passed by a program that
does nothing, and introduced defects are caught 91 percent of the time.

Whether role separation improves correctness, and whether any improvement
justifies its cost, requires a comparison against a live language model that
has not yet been run.
