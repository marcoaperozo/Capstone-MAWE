# Multi-Agent AI Workflow Engine: Simulating an Autonomous Software Development Team

Marco Perozo, Gabriel Marte, Lewdy Aquino, Alvin Almonte

Department of Computer Science, Southwest Minnesota State University

## Abstract

Most AI coding assistants are a single model answering a single prompt: one
pass to understand a request, design a solution, write the code, and check it.
This project asks whether dividing that work among specialized agents produces
more correct software.

We built MAWE, a Multi-Agent AI Workflow Engine that splits development across
three agents: a Product Manager that writes a specification with runnable
checks, a Developer that implements it, and a Code Reviewer that runs the code
in a sandbox and compares its output against that specification. Because the
Reviewer executes the program rather than reading it, it cannot approve code
that demonstrably fails.

Across 100,000 randomized adversarial sequences every run terminated within
its iteration limit, and compressing the revision history cut prompt size by
94 percent without changing outcomes. Whether role separation improves
correctness requires a comparison against a live model, which has not yet been
run.
