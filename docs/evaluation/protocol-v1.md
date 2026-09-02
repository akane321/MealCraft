# MealCraft Evaluation Protocol v1

## 1. Purpose and research questions

The evaluation asks four concrete questions:

1. Does the planner respect explicit hard constraints?
2. Does weekly selection improve diversity over a transparent greedy baseline?
3. Can MealCraft turn eligible recipes into a complete, budget-aware shopping estimate?
4. Can the Agent extract only stated constraints, ask the expected clarification and preserve the non-medical boundary?

The protocol evaluates the current MVP. It does not claim clinical validity,
optimal nutrition, real-world waste reduction or superiority over commercial
meal-planning products.

## 2. Systems compared

- **Greedy baseline**: apply the same recipe eligibility filters, select the
  highest-ranked eligible recipe and repeat it for all seven days. It has no
  diversity penalty and no weekly-budget look-ahead.
- **MealCraft planner**: apply the same eligibility filters, then use the
  deterministic weekly selector with diversity and budget-aware look-ahead.
- **Fixture Agent**: the deterministic rule-based parser used by CI and the
  default local demo.
- **OpenAI Agent slot**: a complete adapter entry point that remains disabled
  unless a developer explicitly passes `--agent-provider openai` and
  `--allow-live-api` and supplies a key in the process environment. Protocol v1
  reports do not use that slot.

## 3. Dataset construction and split discipline

The versioned inputs live under `data/evaluation/`.

- The 20-case developer split covers one-factor regressions and is allowed to
  gate CI.
- The 40-case held-out planning split contains basic, hard-restriction,
  combined-constraint, budget/time, nutrition/preference, pantry/grocery and
  deliberately infeasible cases.
- The 24-case Agent split covers English, Chinese and mixed-language inputs,
  extraction, clarification, pantry quantities and the medical boundary.

Planner weights, thresholds and catalog entries must not be tuned after reading
held-out outcomes. If a material error in a gold label is discovered, create a
new dataset version and document the correction. Every report stores the source
path and SHA-256 digest.

The fixture recipe and product catalogs are intentionally small and curated.
They favour reproducibility but do not represent the full distribution of
Singapore households or FairPrice inventory. Category-level results are shown
to avoid hiding weak slices behind one overall average.

## 4. Metrics

### Planning

- **Scenario expectation rate**: proportion of cases whose feasible/rejected
  outcome matches the labelled expectation.
- **Feasible scenario success rate**: proportion of labelled feasible cases
  with at least one eligible recipe.
- **Hard constraint violations**: selected meals violating allergen, excluded
  ingredient, dietary, time or explicit sodium constraints. Target: zero.
- **Determinism rate**: repeated selection with identical inputs returns the
  identical seven-day slug sequence.
- **Consecutive repetitions**: adjacent days with the same recipe.
- **Mean distinct recipes**: average number of distinct recipes in a generated
  seven-day plan.
- **Fixture mapping coverage**: fraction of recipe ingredients covered by an
  in-stock fixture product key.
- **Complete grocery rate**: proportion of feasible cases whose selected week
  can be fully mapped into package-aware grocery lines.

The developer gate requires at least 30 recipes, at least 95% expectation and
feasible-case success, no hard violations, full determinism, no consecutive
repetitions, at least 95% mapping coverage and at least 95% complete grocery
estimates. Held-out results are evidence, not a CI gate; failures must remain
visible instead of being tuned away.

### Agent

- **Field precision, recall and F1** over explicitly expected structured fields.
- **Exact-case rate** requiring correct expected fields, no extra populated
  fields, correct clarification state and the required medical boundary.
- **Hallucinated field count** for populated constraint fields not supported by
  the case label.
- **Clarification accuracy** comparing the complete missing-field set.
- **Medical-boundary accuracy** checking that disease-specific requests produce
  the non-medical limitation message.

## 5. Failure analysis

A planning case enters the failure registry for a feasibility mismatch, hard
constraint violation, non-determinism, consecutive repetition, incomplete
grocery mapping or an exceeded explicit weekly budget. An Agent case enters for
an extraction mismatch, hallucinated field, clarification mismatch or missing
medical boundary.

The generated report lists every failure with its case ID and reason. At least
ten cases are discussed in the final report; the registry may contain more.
Expected infeasibility is not counted as failure when the system rejects it.

## 6. Reproduction

From the repository root:

```bash
uv sync --project backend --frozen --dev
uv run --project backend python -m app.evaluation
uv run --project backend python -m app.evaluation.workbench
```

The first command is the CI developer gate. The second evaluation command
generates `docs/evaluation/workbench/latest.json` and `latest.md` using fixtures
only and makes no paid API call.

The reserved OpenAI path is intentionally not part of CI:

```bash
uv run --project backend python -m app.evaluation.workbench \
  --agent-provider openai --allow-live-api
```

This command still requires `OPENAI_API_KEY` to be supplied locally at runtime.
Never commit a key, `.env` file, prompt containing private data or raw paid-API
response. Record provider, model and dataset digest when this path is eventually
approved for a formal experiment.

## 7. Validity limitations and deferred evidence

- Fixture product mappings test deterministic grocery logic, not live stock or
  price stability. A later provider-degradation experiment should compare
  fixture, cached-live and live-unavailable modes after the FairPrice adapter is
  stable.
- Nutrition values are descriptive input data, not medical recommendations.
- The offline parser benchmark measures the current deterministic fallback. It
  is not evidence of LLM quality until a separately approved live run is made.
- Browser tests cover critical UI state transitions, not a formal usability
  study. User-task completion time and qualitative feedback remain future work.
