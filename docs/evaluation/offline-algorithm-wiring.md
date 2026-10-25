# Offline algorithm development wiring

This is a development integration check, not a formal comparison, frozen
baseline specification or held-out evaluation entry. Paid model, RAG, generic
agent, human-submission and strong-rule registrations are deliberately absent.
Their formal interfaces and admission remain separate work.

`app.evaluation.algorithm_ladder_baseline` connects the existing greedy,
diversity-greedy, GRASP, local search, annealing, beam and native CP-SAT
implementations to the current `BaselineResponse` and shared
`pure_llm_baseline.score`. It does not replace the shared scorer or planning
objective implementation. Its grouping is recipe-ID-only and its ranking is a
synthetic ordered grid: neither is a frozen near-duplicate or quality judgment.

## Synthetic input and output

Inputs use the existing developer scenario envelope understood by
`multidish_runner.rule_constraints/build_problem`. Additionally, `recipe_steps`
maps each candidate recipe ID to its actual instruction strings. This is
developer packet information, not a new formal test-set contract. Missing steps
fail explicitly; they are never invented. All ingredients must have known,
positive gram quantities: unsupported lines are not silently omitted.
Dish servings use `dish_servings`; role IDs belong to dishes and all dishes in
the same slot are grouped in one meal.

The shared scorer's strict/adjusted outcomes and unverified dimensions are
retained unchanged. Missing or skipped validation is counted as unscored, not
success. A search timeout, unproven status or rejected solution is a failed
development attempt, never a proof of infeasibility. Native multi-worker CP-SAT
is not advertised as deterministic.

## Running an integration check

Use only a synthetic/developer input path and a **new**, nonexistent output
directory:

```bash
cd backend
uv run python -m app.evaluation.baseline_comparison \
  --episodes /path/to/synthetic-developer-input.json \
  --output-dir /path/to/new-development-run \
  --arms algorithm-rung-1-diversity-greedy --repeats 1
```

Protected evaluation path names are rejected before the episode loader opens
them; there is no override. Do not rename or copy protected data into a developer
directory. There is no automatic cache or force-reuse switch. Each new run writes
its own raw outcomes and failures; an existing output directory is refused.
The runner contains no paid registration or live flag. No scores produced here
establish formal study readiness, model performance or final baseline fairness.
