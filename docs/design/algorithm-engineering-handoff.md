# Algorithm Engineering Handoff: Planning and Validation

## Status and purpose

This document is the implementation handoff for the contributor completing
MealCraft's planning and validation algorithm. It defines the **accepted final
scope**, not only the current seven-main-meal runtime. The merged runtime remains
documented in [Current Status](../current-status.md); this handoff must not be
quoted as evidence that the final optimizer is complete.

The repository now contains a runnable reference scaffold:

- `backend/app/schemas/planning_v2.py`: final-scope problem, solution, trace and
  validation schemas;
- `backend/app/planning/final_scope_scoring.py`: transparent sodium and local
  loss helpers;
- `backend/app/planning/final_scope_reference.py`: deterministic greedy
  reference planner;
- `backend/app/planning/final_scope_validator.py`: independent constraint and
  shopping validator;
- `data/fixtures/planning-v2/final-scope-multislot.json`: multi-day,
  multi-meal integration fixture.

This is deliberately a foundation. Beam Search, live-product repair,
relaxation search, an optimization oracle and production integration remain
teammate work.

## Final product goal

Given an explicit set of meal slots, household servings, user constraints,
recipe candidates, pantry facts and a versioned FairPrice product snapshot,
produce one of the following:

1. a feasible, explainable plan with a package-correct Shopping List;
2. `needs_clarification` when a material user value is missing;
3. `needs_data` when ingredient, unit, nutrition or product evidence is
   insufficient;
4. `infeasible` only after a complete search or a declared bounded-search
   policy justifies that conclusion, accompanied by minimal user-controlled
   relaxation options.

The horizon is represented by explicit slots rather than a hard-coded number of
days or meals. It must support breakfast, lunch, dinner and optional snacks,
different servings and time limits per slot, required or optional slots, and
locked meals. A one-week plan is one valid instance, not the schema boundary.

## Authority boundary

The Agent may parse intent, request clarification and explain a result. The
algorithm layer owns:

- hard-constraint filtering;
- numeric nutrition and cost calculations;
- selection across the complete horizon;
- known-quantity pantry deduction;
- product/package decisions;
- final independent validation;
- conflict and relaxation evidence.

The LLM must never declare allergen safety, invent nutrition or price values,
silently relax a constraint, or rewrite the Shopping List arithmetic.

## Canonical mathematical model

### Sets and parameters

- `S`: explicit planning slots;
- `R`: frozen recipe candidates;
- `I`: canonical ingredients;
- `P_i`: product candidates compatible with ingredient `i`;
- `e_sr`: 1 when recipe `r` is eligible for slot `s` after hard filtering;
- `q_ri`: normalized amount of ingredient `i` needed by recipe `r` at its
  canonical serving basis;
- `v_s`: requested servings for slot `s`;
- `b_r`: canonical recipe servings;
- `n_rm`: nutrient `m` per serving of recipe `r`;
- `a_ip`: amount of ingredient `i` supplied by one package of product `p`;
- `c_p`: observed checkout price of one package;
- `k_i`: compatible known pantry quantity. Unknown quantity is not assigned a
  numeric value;
- `B`: optional user-entered purchase budget;
- `L_tm`, `U_tm`: optional lower and upper nutrient bounds for scope `t`.

Every parameter carries catalog, product-snapshot and policy versions. External
prices also carry observation time and provider status.

### Decision and derived variables

- `x_sr in {0,1}`: recipe `r` is selected for slot `s`;
- `y_ip in Z_+`: packages of product `p` purchased for ingredient `i`;
- `d_i >= 0`: known pantry amount deducted;
- `Q_i >= 0`: total ingredient demand after serving scaling;
- `E_tm >= 0`: lower/upper nutrition deviation for soft target `t,m`;
- optional search-state variables for repetition, cuisine distribution and
  change disruption.

### Hard constraints

For every required slot:

```text
sum_r x_sr = 1
```

For an optional slot, the right-hand side becomes `<= 1`. Ineligible assignments
are forbidden:

```text
x_sr <= e_sr
```

A locked recipe `r*` requires `x_s,r* = 1`. Ingredient demand and pantry
deduction are:

```text
Q_i = sum_s sum_r x_sr * q_ri * v_s / b_r
d_i = min(Q_i, k_i)             only when pantry quantity and unit are known
remaining_i = Q_i - d_i
```

Package coverage and purchase budget are:

```text
sum_(p in P_i) a_ip * y_ip >= remaining_i
sum_i sum_(p in P_i) c_p * y_ip <= B       when budget is explicitly hard
```

Allergen, prohibited-ingredient, dietary, explicit time and explicit numeric
nutrition limits are compiled into `e_sr` or scoped hard inequalities. Missing
facts produce `needs_data`; they are not interpreted as zero or compliant.

### Nutrition scope

User-entered nutrition targets declare their scope explicitly:

- `per_slot`: each selected recipe is checked per person;
- `per_day`: selected meals on the same date are summed per person;
- `horizon_average`: daily totals are averaged across represented dates.

MealCraft does not invent BMR/TDEE or medical targets. General lower-sodium,
lower-sugar and lower-calorie language remains a soft preference unless the
user enters a numeric constraint.

For lower-sodium ranking, the reference benchmark is energy proportional:

```text
sodium_reference(recipe) = 2000 mg * recipe_calories / 2000 kcal
```

This is a broad preference anchor, not a prescription or a strict 2000 mg/day
feasibility test. The current scaffold gives zero loss at or below the anchor
and increases linearly to maximum loss at twice the anchor. The final policy
must be frozen before evaluation and must preserve this non-medical wording.

### Lexicographic objective

Hard validity is not exchanged for a better preference score. Search should
therefore use two ordered layers:

1. minimize hard violations and unresolved decisive facts; a reportable
   feasible plan has zero hard violations and zero decisive unknowns;
2. among valid plans, minimize a normalized soft loss:

```text
J = w_n * nutrition_deviation
  + w_v * repetition_and_variety_loss
  + w_t * cooking_time_loss
  + w_p * unused_priority_pantry_loss
  + w_h * general_health_preference_loss
  + w_c * package_cost_and_surplus_loss
  + w_d * replanning_disruption_loss
```

Weights apply only to active, observable dimensions. Missing fields are masked
from the denominator rather than scored as zero satisfaction. Stable recipe and
product IDs provide deterministic tie-breaking.

## Proposed production algorithm

### Phase 1: compile and filter

Validate IDs, units, unknown states and target scopes. Compile a slot-specific
eligibility matrix with machine-readable rejection reasons. Locked recipes are
validated before search.

### Phase 2: candidate retrieval

Request a bounded, diverse recipe pool from the recipe/retrieval layer. The
planner consumes canonical records and never scrapes recipes itself. A fixture
must remain available so algorithm work is independent of the live data
pipeline.

### Phase 3: horizon search

Implement deterministic Beam Search as the practical production method:

1. order slots by constrainedness, then date/meal type/stable ID;
2. expand each partial state with eligible recipes;
3. carry daily nutrition, recipe/cuisine counts, pantry coverage and approximate
   demand in the state;
4. prune hard-invalid states immediately;
5. retain the best `K` states by lower-bound soft loss plus deterministic
   tie-break;
6. make beam width, candidate limit and timeout explicit trace fields.

The existing greedy planner is only a smoke-test reference and comparison
baseline. It must not be relabelled as the final algorithm.

### Phase 4: product grounding and bounded repair

After a provisional plan determines ingredient demand, call the Retrieval
contract for current FairPrice candidates. Recompute exact package counts,
checkout cost and surplus. If product unavailability or the exact budget makes
the plan invalid, return a typed repair request to the search layer. Limit the
number of retrieve-repair rounds and preserve every snapshot and rejection.

Live retrieval is for product operation. Comparative evaluation uses a frozen
snapshot so all methods receive the same facts.

### Phase 5: independent validation

The validator receives the immutable problem, selected assignments and Shopping
List. It recomputes constraints without trusting planner score fields. Each
check reports code, scope, actual value, limit, margin, hard/soft status and
detail. A failed soft band remains visible but does not become a hard failure.

### Phase 6: infeasibility and relaxation

Do not infer global infeasibility merely because Beam Search found no candidate.
Use one of these evidence levels in the trace:

- exact proof from CP-SAT/MILP on the bounded candidate packet;
- exhaustive search on a small packet;
- `search_exhausted` with explicit limits, which is not a proof.

Generate minimal relaxation options by assigning predeclared costs to
relaxable, non-safety constraints. Allergens and prohibited ingredients are
never auto-relaxed. The user chooses whether to accept a relaxation.

## Interfaces with other modules

### Recipe and ingredient data

Required fields are canonical IDs, recipe serving basis, normalized quantities
and units, meal-type eligibility, time, allergens, dietary tags, per-serving
nutrition, cuisine/preference attributes, provenance and completeness flags.
The planner must reject or mark unknown unsupported facts rather than patching
the database locally.

### Retrieval and RAG

The planner sends only consolidated canonical ingredient demand and context.
Retrieval returns timestamped product candidates, package quantity/unit, price,
availability, mapping confidence, source mode and warnings. The planner owns
the final package choice and budget calculation; Retrieval owns evidence, not
the optimization decision. YouTube tutorial selection occurs only after a
recipe is selected and has no authority over planning facts.

### Agent

The Agent supplies validated structured intent, clarification state and explicit
user choices. It receives typed planner status, relaxation options and trace
references. Free-form Agent text cannot mutate the problem after confirmation.

### Frontend

The UI must render required/optional slots, locks, servings, target scope,
purchase total, pantry assumptions, validation margins, missing-data states and
relaxation choices. It should not reduce `needs_data` or `candidate_rejected` to
a generic server error.

### Evaluation

All systems under comparison receive the same immutable scenario packet,
candidate recipes and FairPrice snapshot. The Rule-only Planner, contextual
LLM-only baseline, plain general-purpose LLM and MealCraft must be evaluated on
hard validity, nutrition deviation, budget/package correctness, preference fit,
diversity, runtime, repair success and failure modes. Held-out labels are never
used to tune weights or beam settings.

## Work packages left for the algorithm contributor

1. **Schema hardening**: review v2 fields, add completeness/provenance links,
   dietary compatibility policy and stable serialization tests.
2. **Constraint compiler**: create the eligibility matrix and structured
   rejection trace with exhaustive hard-filter tests.
3. **Beam Search**: implement bounded deterministic search, state dominance,
   lower bounds, tie-breaking and performance benchmarks.
4. **Nutrition objective**: freeze tolerance, normalization and missing-data
   policies using developer data only.
5. **Package optimization**: support multiple product alternatives, compatible
   substitutions, exact package coverage, checkout budget and surplus.
6. **Retrieve-repair loop**: integrate the Retrieval evidence packet with
   bounded retries and explicit degraded states.
7. **Independent validator**: extend coverage proof, trace margins and validator
   mutation tests.
8. **Relaxation engine**: generate minimal non-safety relaxations and distinguish
   proof from bounded-search exhaustion.
9. **Oracle and baselines**: add a small CP-SAT/MILP oracle for optimality-gap
   analysis and preserve an independently runnable strong Rule-only baseline.
10. **Production integration**: add versioned API/service/persistence migration,
    frontend states and backward compatibility without silently changing the
    current `/api/plans` contract.

## Definition of done

- arbitrary explicit meal-slot packets run without fixed seven-meal logic;
- all hard constraints and unknown semantics have deterministic tests;
- valid outputs have zero independently recomputed hard violations;
- every plan, product choice and relaxation is traceable to frozen inputs;
- known pantry quantities are deducted exactly once; unknown quantities are
  never deducted;
- package counts cover remaining demand and purchase totals are reproducible;
- the same input and versions produce byte-equivalent decision outputs;
- infeasibility claims declare proof strength;
- comparison baselines use the same candidate and product context;
- developer tuning and held-out evaluation remain physically separated;
- documentation, API contract, migration and frontend states are updated when
  the scaffold becomes runtime behaviour.

## Running the scaffold

From the repository root:

```bash
uv run --project backend python -m app.planning.final_scope_cli
uv run --project backend pytest backend/tests/test_planning_v2.py
```

The first command proves schema, deterministic selection, shopping derivation
and validation can execute on a final-scope-shaped packet. It does not prove
optimality, production readiness or live FairPrice integration.
