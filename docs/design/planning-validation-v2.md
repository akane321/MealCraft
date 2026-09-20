# Planning and Validation v2 in the product path

How the finished planning engine becomes the thing a user actually gets, and
which deepenings follow. Decision: private `ADR-0033`; it amends `ADR-0014` and
works inside `ADR-0021` (exact-cent purchasing), `ADR-0024` section 5 (meal type
is a preference), `ADR-0025` (nutrition scopes) and `ADR-0031` (console,
parameters, experiments).

This document is the contract for building it. Where it and a decision record
disagree, the decision record wins. Related: [algorithm engineering
handoff](algorithm-engineering-handoff.md), [integration
guide](planning-integration-guide.md), [beam search](planning-beam-search.md),
[constraint compiler](planning-constraint-compiler.md), [mixed
shopping](planning-mixed-shopping.md), [operations
console](operations-console.md).

## Where it stands

**Product path.** A request reaches `app/services/meal_plan.py`, which calls
`app/planning/weekly_planner.py`: a greedy day-by-day selector with a fixed
diversity penalty over a truncated candidate list. It applies a budget only when
every candidate's cost is known, and nothing recomputes its result.

**Engine.** `app/planning/` holds the v2 work: constraint compiler, bounded beam
search, the independent validator, mixed-package purchasing, CP-SAT and
exhaustive oracles, bounded snapshot repair, minimal relaxation search and input
audit, with tests. No product request reaches any of it.

Closing that gap is packet P1. Everything after it is a deepening.

## Boundaries

1. Hard constraints, nutrition, packaging, cost and feasibility stay with
   deterministic code. A model may influence candidate order and soft weights,
   nothing else (`ADR-0001`, `ADR-0016`).
2. The independent validator's verdict is final. A `failed` or `indeterminate`
   result is never returned as a plan, and `indeterminate` is never presented as
   success.
3. The product surface stays quiet. A passed plan shows no validation badge,
   panel or score. Failure surfaces as one sentence plus a concrete next step.
   The full derivation lives in the console.
4. Slots are the representation. No new code hard-codes seven, or one meal per
   day; horizons, caps and purchasing are expressed over the slot set.
5. Safety constraints — allergen exclusions, user-stated hard medical limits —
   are never relaxed, and never appear in a suggestion.
6. A learned ranking may reorder candidates and nothing else. Switching it off
   must still yield a valid plan.
7. A free-text theme may only set values on the controlled parameter list.
   Anything outside the list is ignored, and the fact is recorded.
8. Identical packet, settings and seed produce an identical plan.

## Work packets

Each packet is independently reviewable. P1 comes first; P2, P3, P4, P6 and P7
depend on it; P5 does not; P8 depends on the console's experiment module.

### P1 — Route the product request through the engine

Compile the request into the v2 problem, plan with bounded beam search, validate
independently, persist the trace.

- The adapters in `planning-integration-guide.md` build the packet: explicit
  slots, servings, locks, exclusions, nutrition bands, pantry, product evidence
  and versions.
- The outcome distinguishes `feasible`, `needs_clarification`, `needs_data`,
  `candidate_rejected` and `infeasible`, and separately records which of
  *exactly infeasible*, *exhaustively infeasible*, *bounded search exhausted*
  and *needs data* applies. A bounded search that ran out is never written as
  global infeasibility.
- The greedy selector is kept and remains selectable as a baseline: the
  comparison in P8 needs it, and removing it would remove the control group.
- Search settings, seed, limits, expansions, prunings and the validator's checks
  are written into the run record the console reads.

Done when a product request produces a beam-search plan that the independent
validator passed, the greedy path is reachable only as an explicitly selected
baseline, and the run is inspectable end to end.

### P2 — Explain infeasibility with a number

- **Minimal conflicting set**: the smallest subset of the user's own constraints
  that cannot hold together. Report the subset, not a generic refusal.
- **Minimal relaxation**: a proposal drawn only from the declared options of
  `app/planning/relaxation_search.py`, carrying the value that makes the request
  feasible ("a S$46.20 budget works"). The existing distinction between
  `minimal_in_declared_options` and `candidate_without_minimality_proof` is
  preserved in the response; a suggestion never claims minimality the search did
  not establish.
- Safety constraints are excluded from both the suggestion and the relaxation
  search.
- Applying a suggestion is a user action. It re-enters the same pipeline and the
  same validator; nothing is loosened server-side to produce an answer.
- Product copy: one sentence for what is wrong, at most three suggestions, each
  with its number.

Done when each stress fixture in P8 that is infeasible produces a conflicting
set and at least one numeric suggestion, and accepting a suggestion yields a
validated plan.

### P3 — Bound variety and ingredient overlap, then trade them off

Hard caps, checked by the validator:

- no recipe appears twice in one plan horizon;
- the same primary protein does not occupy consecutive slots;
- a single core ingredient appears in at most `max_slots_per_core_ingredient`
  slots.

Inside those caps, shared **non-core** ingredients earn a bounded score reward
traded off against the variety penalty. "Core" is the recipe's primary protein
or defining ingredient; the classification rule ships with the packet and is
recorded, not inferred per request.

Done when a forced-overlap weight cannot produce a plan violating a cap, a
forced-variety weight cannot forbid a legal repetition, and both weights appear
on the controlled parameter list.

### P4 — Compile nutrition targets to the right scope

- An unqualified numeric target compiles to a `horizon_average` band over the
  slot set, plus a per-slot guard band applied as a soft penalty, so the average
  cannot be met by pairing extremes.
- Explicitly per-meal wording compiles to a `per_serving` hard band.
- The compiled scope is echoed in the words the plan uses, so the user can see
  which reading was taken.

Evaluation is unchanged: held-out episodes declare their own scope with no
default (`ADR-0025`), and the scorer recomputes from the frozen catalog.

Done when the two phrasings produce different plans on the same catalog, and
each plan states its scope.

### P5 — Purchase across the whole slot set

Extend mixed-package selection from per-ingredient to the whole slot set, so one
larger package can cover demand that several slots share. Arithmetic stays as
`ADR-0021` requires: whole cents, integer package counts, no invented stock, no
unit conversion beyond the compatible-unit rules, and an independent recompute
of identity, coverage, cost and surplus.

Done when a fixture whose per-ingredient optimum exceeds the budget becomes
feasible under whole-slot-set purchasing, with the validator recomputing the
basket, and the improvement is reported as a cost and surplus difference.

### P6 — Replan by changing only what must change

A single-slot edit, or a product snapshot that changed under an existing plan,
keeps every unaffected slot's recipe. The response states which slots changed
and how the shopping list differs.

Done when the invariant is asserted in tests for both triggers, and the reported
difference matches the actual one.

### P7 — Learned ranking and free-text themes

- Record meal check-in feedback in a form an offline replay can read.
- A reorder-only hook over the candidate list, **off by default**, that cannot
  admit a rejected candidate or alter any arithmetic.
- An offline replay harness that measures a ranking against recorded feedback.
  Until the held-out set is frozen, it runs on synthetic or developer data only
  (`ADR-0020` section 2 as amended by `ADR-0029` section 1).
- Theme translation: free text to values on the controlled parameter list, with
  everything outside the list dropped and the drop recorded in the trace.
  Difficulty and active minutes per slot are expressed the same way, as a soft
  preference over the existing score.

Done when the hook can be switched off with the plan still valid, the replay
harness reproduces a ranking comparison from recorded conditions, and a theme
request that asks for something outside the list is visibly ignored rather than
silently honoured.

### P8 — Evidence

- Ablation presets in the console experiment module: independent validation off,
  repair off, variety penalty off, overlap reward off, learned ranking off, beam
  search replaced by the greedy selector.
- Stress fixtures the acceptance runs against: infeasible by one cent,
  allergen-saturated candidates, pantry-heavy input, a price change between
  planning and purchasing, an unavailable retrieval provider.
- Reporting follows `ADR-0028`: per-category counts and failure mechanisms, no
  per-category success rates.

## Controlled parameters

These are the values the console may set and an experiment may vary
(`ADR-0031` section 7). Values marked *current* are what the code uses now and
are not frozen; freezing them is `OPEN_QUESTIONS.md` items 15, 18 and 20, and it
happens through recorded experiments, not through argument.

| Parameter | Meaning | Status |
| --- | --- | --- |
| `beam_width` | states kept per slot expansion | to freeze |
| `max_expansions` | hard ceiling on expansions | current: 10000 |
| `candidate_limit_per_slot` | candidates considered per slot | to freeze |
| `diversity_penalty` | variety weight | current: greedy path uses 8.0 |
| `overlap_reward_weight` | bounded reward for shared non-core ingredients | new, P3 |
| `max_slots_per_core_ingredient` | hard cap on one core ingredient | new, P3 |
| `nutrition_guard_band` | per-slot soft band under a horizon average | new, P4 |
| `effort_rhythm_weight` | difficulty and active-minute shaping per slot | new, P7 |
| `ranking_model` | off, or a named offline-trained ranking | default off |
| `repair_rounds` | bounded retrieve-repair attempts | to freeze |

A parameter not on this list cannot be set from the console or by a theme.

## Dependency on release v2

Everything here is built against the released record shape, which
`data-engineering/data/fixtures/ops/` already holds as a real partial build.

**Not blocked**: P1 through P8 can all be built now.

**Only meaningful after v2**: the measured effect of the overlap reward and of
whole-slot-set purchasing, because both depend on how many recipes share
ingredients, and the catalog is small until v2 ships. Build them now; quote
their numbers against v2.

## Acceptance

| Area | Must hold |
| --- | --- |
| Verdict | no plan reaches a user without a passed independent validation; `indeterminate` is never shown as success |
| Quiet surface | a passed plan adds no validation UI; a failure is one sentence plus concrete suggestions |
| Safety | no suggestion, relaxation or weight can loosen an allergen exclusion or a stated hard medical limit |
| Explanation | every infeasible fixture yields a minimal conflicting set and a numeric suggestion, and a suggestion never overstates minimality |
| Caps | no weighting can produce a plan violating a variety cap |
| Scope | the two nutrition phrasings produce different plans, each stating its scope |
| Money | budget comparison stays exact in cents across whole-slot-set purchasing |
| Replan | an unaffected slot never changes, and the reported difference matches the real one |
| Determinism | the same packet, settings and seed give the same plan and the same trace fields |
| Learning | the ranking hook off by default, reorder-only, and removable with the plan still valid |
| Slots | no new code hard-codes seven slots or one meal per day |
| Evidence | each ablation runs from the console with its conditions recorded, and results follow `ADR-0028` |
