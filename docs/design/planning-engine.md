# Planning Engine Contract

## Purpose and boundary

The planning engine converts a validated structured request plus recipe and
grocery facts into a feasible, explainable weekly plan. It owns arithmetic,
hard-constraint decisions, package-aware cost and final validation. The LLM may
help users express intent, but it must not replace this authority.

## Verified baseline

The current implementation produces seven persisted main meals. It filters
allergens, excluded ingredients, dietary incompatibility, time and explicit
sodium limits; ranks eligible recipes using active nutrition, pantry and time
dimensions; controls adjacent repetition; calculates per-person nutrition;
aggregates grocery demand; deducts only known compatible pantry quantities;
rounds product packages; and records weekly budget status.

The current selector is deterministic and provides a useful MVP baseline. It is
not yet evidence of global optimality, broad preference fit, or performance over
a high-dimensional catalog.

## Accepted target pipeline

The target is not hard-coded to seven dinners. It accepts an explicit set of
multi-day breakfast, lunch, dinner and optional snack slots, with per-slot
servings, time limits, required/optional state and locks. A one-week plan is one
instance of this model, not its upper or lower boundary. See the detailed
[Algorithm Engineering Handoff](algorithm-engineering-handoff.md) for the
mathematical model, Beam Search proposal, retrieval-repair loop, work packages
and completion criteria.

```text
validated request and immutable context
  -> candidate retrieval
  -> deterministic hard filtering
  -> soft score components with missing-data masks
  -> week construction under diversity and budget state
  -> consolidated demand and pantry deduction
  -> product selection and package rounding
  -> final constraint and Shopping List validation
  -> feasible plan, infeasibility report, or explicit relaxation options
```

Each stage should emit a machine-readable trace. The final validator must
recompute decisive facts rather than trust an earlier score or model statement.

## Input contract

The authoritative planning input should contain:

- planning horizon, start date, meal slots and household servings;
- allergen, prohibited-ingredient and dietary hard constraints;
- cooking-time, meal-budget, weekly-budget and explicit numeric nutrition
  limits;
- soft health and preference priorities;
- user-entered calorie and macronutrient targets, never automatically invented;
- pantry items with canonical ID, known/unknown quantity and unit;
- locked/completed entries and the prior revision for replanning;
- frozen recipe catalog and product snapshot identifiers;
- policy and algorithm versions.

Unknown, absent and zero are different states and must not be collapsed.

## Output and trace contract

A planning result should preserve:

- status: `feasible`, `needs_clarification`, or `infeasible`;
- selected recipe per day/slot and servings;
- rejected candidates and hard-rejection reasons;
- active soft-score components, normalized values and weights;
- constraint margins and nutrition deviation;
- consolidated ingredient demand, pantry deductions and unresolved units;
- product candidates, selected products, package counts, surplus, purchase cost
  and ingredient-use cost;
- warnings, fallback/source state and unresolved mappings;
- deterministic validation result;
- input, catalog, snapshot, policy and algorithm versions.

The user-facing explanation may summarize this trace but cannot introduce facts
that the trace does not support.

## Constraint semantics

- Hard constraints are pass/fail and cannot be traded against diversity or a
  high soft score.
- General lower-sodium, lower-sugar and lower-calorie requests are soft
  preferences unless the user supplies an explicit numeric ceiling.
- User-entered calorie and macronutrient targets are planning targets, not
  medical prescriptions or automatically generated goals.
- A known pantry quantity may be deducted only after unit compatibility is
  established. An unknown quantity may influence rank but has zero purchase
  deduction.
- When no valid plan exists, the engine returns the conflicting constraints and
  ranked, user-controlled relaxation options. It must not fabricate compliance.

## Baseline separation

Evaluation must keep these mechanisms distinct:

- the weak greedy-repeat lower bound demonstrates that repeating the top item is
  inadequate;
- the strong Rule-only Planner receives structured input and applies filtering,
  a reasonable transparent heuristic and simple no-adjacent-repeat logic;
- MealCraft adds its complete deterministic planning, grocery validation,
  clarification and orchestration pipeline;
- an optional MILP or CP-SAT oracle may estimate an upper bound or optimality
  gap, but it is not a user-facing system by default.

The Rule-only baseline must not be intentionally crippled. It should be a
credible implementation a competent developer could build without an Agent.

## Planning metrics

- strict feasible/infeasible classification accuracy;
- episode-level hard-constraint violation rate;
- violation count per planned meal and per applicable constraint;
- required-slot completion rate for feasible cases;
- nutrition absolute deviation and rate within predeclared tolerance;
- weekly-budget compliance and cost regret against the best known valid plan;
- adjacent repetition and distinct-recipe count;
- soft-preference satisfaction over fields that are actually labelled;
- Shopping List line/item/package/cost correctness;
- deterministic repeatability;
- replanning validity, unnecessary disruption and Shopping List delta accuracy.

No average preference score may compensate for an allergen or other hard-
constraint failure.

## Parallel-development fixtures

The planner should expose small versioned fixtures that do not require live
recipe ingestion or FairPrice retrieval:

1. a complete feasible packet;
2. an ambiguous packet that should not reach planning;
3. an infeasible hard-constraint packet;
4. a pantry unit-compatible and unit-incompatible pair;
5. a product-unavailable packet;
6. a replanning packet with completed and locked meals.

`data/fixtures/planning-v2/final-scope-multislot.json` is the first runnable
final-scope-shaped packet. It covers explicit breakfast, lunch, dinner and
optional snack slots, serving scaling, a locked meal, scoped nutrition bands,
known and unknown pantry quantities, product packages and purchase budget.

The accompanying deterministic greedy reference and independent validator are
integration scaffolds. They are not the final Beam Search implementation and
must not be used to claim global optimality or production completion.

These fixtures let Agent, frontend and Evaluation contributors integrate before
full upstream data is ready.

## Definition of done for a planning change

1. Input/output schemas and unknown semantics are documented.
2. Hard checks and arithmetic have deterministic tests.
3. A trace explains every rejection and selected score component.
4. Shopping output is revalidated against the final plan.
5. The Rule-only baseline remains independently runnable on the same packet.
6. Relevant Evaluation v2 categories are enabled only when their data-readiness
   gates pass.
