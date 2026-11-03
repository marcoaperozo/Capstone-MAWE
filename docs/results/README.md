# Phase 4 results

Each sweep writes a `.json` (every run, plus the metadata that produced it) and
a `.csv` (the same rows, for a spreadsheet). The analysis is re-runnable from
the JSON without touching an API:

```bash
python scripts/week11_experiment.py --analyse docs/results/fixture-sweep.json
```

## What is here

| file | provider | measures a model? |
|---|---|---|
| `fixture-sweep.json` | `bench.oracle` fixture | **no** |

`fixture-sweep.json` is 240 runs — 4 conditions x 20 tasks x 3 repetitions —
against a fixture whose answers are known in advance. It exists to show that
the experiment pipeline works end to end and that the comparison detects a
difference it was built to detect. Every row's `metadata.measures_a_model` is
`false`, and the numbers say **nothing** about any model's ability.

A real sweep needs an API key and is run with `--provider anthropic`. Its
results file will carry `measures_a_model: true`, the model id, and the pricing
used for the cost column.

## Reading a row

Each row records two independent things, and the distinction is the point:

- what the condition *claimed* — `status`, `termination_reason`, `iterations`;
- what the hidden tests *measured* — `pass_rate`, `success`.

A run can be `approved` by the engine's own Reviewer and still have
`success: false`. That is the benchmark doing its job.
