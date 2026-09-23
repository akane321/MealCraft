# Product nutrition scope

This contract covers the structured Planning side of
[P4](planning-validation-v2.md#p4--compile-nutrition-targets-to-the-right-scope).
Integration status is recorded in [Current Status](../current-status.md).

## Input and ownership

`WeeklyMealPlanRequest.nutrition_constraints` accepts up to 12 explicit targets.
Planning owns `ProductNutritionTarget` and `app/planning/nutrition_scope.py`.
The caller, including Agent, supplies the metric and at least one bound.
The compiler does not parse language, invent a tolerance for "about", or infer
a medical target.

Each target contains `metric`, optional `lower`/`upper`, and `scope`:

- Omitting scope selects `horizon_average`: hard bounds apply to the average
  of per-serving nutrients across selected meal slots.
- `per_serving` applies hard bounds to each selected meal, represented as
  `per_slot` in the internal Planning schema.

All six existing nutrient metrics are supported. Bounds must be finite and
between zero and 1,000,000,000, with lower no greater than upper. The upper limit
protects arithmetic; it is not dietary guidance. Zero is a real bound, null is
absent. Unknown fields and scopes are rejected. Empty constraints add no target.
Existing explicit max-sodium limits remain separate and cumulative.

The old `nutrition_targets` scalar fields keep their ranking-only meaning.
A profile scalar does not specify an upper limit, lower limit or approximate
range, so it is not silently converted to hard bounds. A caller wanting P4
behavior must send `nutrition_constraints`. Natural-language and profile
translation remain producer integration tasks.

Developer examples are in
`data/fixtures/planning-v2/nutrition-scope-requests-v1.json`. The example range
450–550 is supplied input, not a built-in interpretation of "about 500".

## Average and guard

New average bands carry `average_basis="selected_slots"`. They do not multiply
nutrients by household servings, sum several meals into one day, or include
empty optional slots in the denominator. No selected meals means an
indeterminate average. Missing required slots still fail validation.

Older packets retain `average_basis="represented_days"`, averaging daily
totals. Held-out parsing and scoring defaults are unchanged. Search bounds use
the selected-slot denominator only when every slot must be assigned; optional
slots cause that pruning bound to be omitted conservatively.

Each average target also creates a soft per-slot guard. The controlled
`nutrition_guard_band` parameter ranges from 0 to 1, with developer default
0.25. It multiplies a supplied lower bound by `1 - guard_band` and an upper
bound by `1 + guard_band`. Absent bounds stay absent. The hard average is
unchanged. Zero creates an unexpanded soft guard; it does not disable scoring.

Guard loss is the distance outside the guard, divided by the larger guard
bound or one, clipped at one and averaged across guards. Beam, the greedy
reference and both exhaustive oracles add this nonnegative term to local loss.
Soft guard failures never reject a plan. The explicitly selected legacy greedy
product baseline keeps its own ranking, but its output must pass the same hard
target validator.

## Output and evidence

Successful plan warnings state each bound and whether it applies to each meal
or the average across planned meals. They are persisted and returned on later
reads. No frontend component is changed.

Operation traces record metric, compiled scope, average basis, hard/soft role
and guard parameter, omitting the user's numeric bounds. The input digest
identifies the request. Scoped requests use `product-scoped-nutrition-v1`;
legacy requests keep their policy ID.

Independent validation recomputes nutrients from selected recipes. Conflict
suggestions preserve the hard bands. Bounded search failure is not a global
infeasibility proof. This implementation covers new-plan generation; legacy
replanning integration remains part of P6.

Tests cover different scopes on the same catalog, multiple meals per date,
optional slots, zero/invalid values, lower guard scores for even meals, HTTP
persistence and rejection without saving a plan. They do not establish natural
language interpretation, browser presentation or Agent integration.
