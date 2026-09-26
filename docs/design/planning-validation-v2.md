# Planning and Validation v2 in the product path

How the finished planning engine becomes the thing a user actually gets, and
which deepenings follow. Decision: private `ADR-0033`; it amends `ADR-0014` and
works inside `ADR-0021` (exact-cent purchasing), `ADR-0024` section 5 (meal type
is a preference), `ADR-0025` (nutrition scopes) and `ADR-0031` (console,
parameters, experiments).

This document is the contract for building it, and the briefing for whoever
picks it up. Where it and a decision record disagree, the decision record wins.
Related: [algorithm engineering handoff](algorithm-engineering-handoff.md),
[integration guide](planning-integration-guide.md), [beam
search](planning-beam-search.md), [constraint
compiler](planning-constraint-compiler.md), [mixed
shopping](planning-mixed-shopping.md), [operations
console](operations-console.md).

## Where it stands

For verified implementation status and pending branch work, see
[current status](../current-status.md). The
[product adapter](planning-product-path.md) documents P1's input, validation,
storage and trace boundary.

**Engine.** `backend/app/planning/` holds about 3,500 lines of v2 work, with
tests: `constraint_compiler.py`, `beam_planner.py` and `mixed_beam.py`,
`final_scope_validator.py`, `mixed_shopping.py` and `package_optimizer.py`,
`package_cp_sat.py` and `exhaustive_oracle.py` (oracles), `snapshot_repair.py`
and `mixed_repair.py`, `relaxation_search.py`, `input_audit.py`, `preview.py`,
and the adapters `recipe_input.py` / `product_input.py`.

P1 connects these components to product requests. The remaining packets deepen
that integration without bypassing the independent validator.

## Why it is shaped this way

The reasoning matters more than the rules, because an unfamiliar case will need
the reasoning.

**Why an independent validator at all, when the planner already checked?** A
planner that checks its own work shares its own bugs. If the planner miscounts
packages, its self-check miscounts the same way and the plan looks fine. The
validator recomputes from the immutable problem without reading the planner's
claims, so the two have to agree by being right, not by being the same code.
This is why "make the validator reuse the planner's helpers to avoid
duplication" is exactly the wrong instinct here — duplication *is* the
mechanism.

**Why the product surface says nothing when validation passes.** The first
draft of this plan surfaced a validation panel. The owner rejected it: a user
does not care about our internal computation, and a badge on every plan makes
the interface busy while telling them nothing they can act on. A verdict only
earns space on screen when it changes what the user should do next. So: silence
on success, one actionable sentence on failure, and the full derivation in the
console, where the team can actually falsify it.

**Why infeasibility has to carry a number.** "No plan fits your constraints" is
a dead end: the user has no idea which constraint to give up or by how much. We
can compute the answer — the search already explores the boundary — so refusing
to state it is withholding work we already did. "Raising the budget to S$46.20
gives a plan" turns a dead end into one decision. This is also the honest form
of intelligence: not the system quietly bending the rules to produce something,
but the system telling the user exactly what the rules cost.

**Why variety and overlap are split into caps and weights.** Both objectives are
right and both are dangerous alone. Chasing variety alone forbids reasonable
repetition and inflates the basket; chasing ingredient overlap alone converges
on one ingredient eaten seven nights running, which is cheap and unusable. A
single weight cannot express "never do the stupid thing, otherwise prefer the
cheaper thing" — so the stupid thing becomes a hard cap the validator checks,
and the preference becomes a bounded weight inside it. If a weight can ever
produce a capped-out plan, the cap is not a cap.

**Why slots rather than "the week".** The MVP showed seven dinners; since
ADR-0046 the product plans the meals each household chose. Hard-coding seven is how a prototype becomes a
rewrite: every horizon, cap and purchase optimisation written against "the week"
has to be reopened the day the product plans lunches. Writing against the slot
set costs nothing now and saves the rewrite. `ADR-0014` already chose this;
P1–P8 just have to not undo it.

**Why the learned ranking may only reorder.** A model that can reject or admit
candidates is a model that can violate an allergen exclusion, and no amount of
accuracy makes that acceptable. Restricted to ordering, the worst it can do is
suggest a valid plan the user likes less. That bound is what lets it ship at
all.

**What we deliberately did not do.** Expiry-first sequencing was proposed and
declined: we have no trustworthy expiry data, and waste reduction is not a
product goal or an evaluation metric, so it would be an unmeasurable objective
competing with measured ones. Recorded in `ADR-0033` section 10 so it is not
reintroduced as a default later.

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

## Start here

Before writing anything, run the existing tests and read one plan end to end.

```bash
cd backend && python -m pytest tests/ -q
```

Then read, in this order: `planning-integration-guide.md` (how a packet is
assembled), `constraint_compiler.py` (what a constraint becomes),
`final_scope_validator.py` (what is checked and what makes a check
indeterminate), and `weekly_planner.py` (what you are replacing). Real released
records to build against are in `data-engineering/data/fixtures/ops/` — a
genuine partial build, not invented samples.

The first useful slice is narrow on purpose: take one existing product request,
build the v2 packet from it, plan with beam search, validate, and return the
result through the existing response shape with the trace persisted. No new
features. Get that green, then take the packets below in order.

## Work packets

Each packet is independently reviewable. P1 comes first; P2, P3, P4, P6 and P7
depend on it; P5 does not; P8 depends on the console's experiment module.

### P1 — Route the product request through the engine

Compile the request into the v2 problem, plan with bounded beam search, validate
independently, persist the trace.

**Inputs.** The household profile and its version, the requested slots, pantry
contents with known quantities, the candidate recipes, and product evidence when
a budget is in play. The adapters in `planning-integration-guide.md` build this;
do not assemble a packet by hand in the service layer.

**Outputs.** Either a validated plan, or a typed non-plan. The outcome
distinguishes `feasible`, `needs_clarification`, `needs_data`,
`candidate_rejected` and `infeasible`, and separately records which of *exactly
infeasible*, *exhaustively infeasible*, *bounded search exhausted* and *needs
data* applies.

That second distinction is the one people collapse, so state it plainly: a beam
search that hit `max_expansions` and found nothing has proved **nothing** about
the problem. It may not be reported as infeasible, and the suggestion machinery
in P2 must not offer relaxations as though the constraints were the obstacle.
The honest answer there is "we ran out of search, here is what we tried",
recorded in the trace and visible in the console.

**Keep the greedy selector.** It stays reachable as an explicitly selected
baseline. P8 compares against it, and deleting it removes the control group that
makes the comparison mean anything.

**Persist.** Search settings, seed, limits, expansions, prunings, the validator's
checks, and the packet digest go into the `OperationRun` record
(`backend/app/models/platform.py`) the console reads.

*Done when* a product request produces a beam-search plan that the independent
validator passed, the greedy path is reachable only as an explicitly selected
baseline, the four infeasibility kinds are distinguishable in the trace, and the
whole run is inspectable end to end.

### P2 — Explain infeasibility with a number

**Minimal conflicting set.** The smallest subset of the user's own constraints
that cannot hold together. Worked example: a user asks for gluten-free, under
S$40 for the week, and nothing over 30 minutes. The gluten-free catalog alone
fits the budget; gluten-free alone fits the time limit; budget and time together
fit. Only gluten-free + 30 minutes is unsatisfiable. The user should be told
those two, not handed all three, and certainly not "your request is too strict".
Finding it is a small search — drop one constraint at a time, keep the smallest
subset that still fails — and the packets are small enough that the naive
version is fast enough. Do not reach for a clever algorithm before measuring.

**Minimal relaxation with a number.** A proposal drawn only from the declared
options in `relaxation_search.py`, carrying the value that makes the request
feasible: "a S$46.20 budget works", "35 minutes works". That module already
distinguishes `minimal_in_declared_options` from
`candidate_without_minimality_proof`; carry that distinction into the response
and never let the wording claim a minimality the search did not establish. "The
smallest change we found" and "the smallest change that exists" are different
sentences and only one of them is usually true.

**Safety is excluded from both.** An allergen exclusion or a stated hard medical
limit is never part of a conflicting set offered for relaxation, never priced,
and never suggested. If the only way to feed someone is to give them the thing
they are allergic to, the answer is that we cannot plan this week, not a
negotiation.

**Applying a suggestion is a user action.** It re-enters the same pipeline and
the same validator. Nothing is loosened server-side to produce an answer — the
moment the system can quietly relax a constraint to avoid an awkward message, no
verdict it reports means anything.

**Product copy.** One sentence for what is wrong, at most three suggestions,
each with its number. Write it the way a person would say it: "There is no
gluten-free plan under 30 minutes for this week. With 40 minutes there is one,
or with a S$46.20 budget."

*Done when* each infeasible stress fixture in P8 produces a conflicting set and
at least one numeric suggestion, accepting a suggestion yields a validated plan,
and a bounded-search-exhausted outcome produces no relaxation suggestion at all.

### P3 — Bound variety and ingredient overlap, then trade them off

Hard caps, checked by the validator:

- no recipe appears twice in one plan horizon;
- the same primary protein does not occupy consecutive slots;
- a single core ingredient appears in at most `max_slots_per_core_ingredient`
  slots.

Inside those caps, shared **non-core** ingredients earn a bounded score reward
traded off against the variety penalty.

**Core versus non-core is the whole design.** Rewarding overlap on chicken
breast produces chicken seven nights. Rewarding overlap on spring onions, soy
sauce, garlic and a bunch of coriander produces a cheaper basket and a week that
still reads as seven different dinners. So "core" means the recipe's primary
protein or defining ingredient, and only non-core lines earn the reward. The
classification rule ships with the packet and is recorded in the trace — it is
not re-derived per request, and not guessed by a model.

Worked example of the trade-off working correctly: two candidate weeks both
satisfy every hard constraint. Week A uses seven unrelated ingredient sets and
needs eleven bought packages. Week B repeats coriander, ginger and sesame oil
across four dishes with four different proteins and needs eight. B should win.
If a weight setting can make "chicken on five nights" win, the cap is wrong or
not enforced.

**The reward is bounded.** An unbounded reward eventually outweighs everything
else it competes with. Cap its contribution so it breaks ties and shifts close
calls, and cannot dominate nutrition or preference terms.

*Done when* a deliberately extreme overlap weight cannot produce a plan that
violates a cap, a deliberately extreme variety weight cannot forbid a legal
repetition, both weights appear on the controlled parameter list, and the
validator rejects a hand-built plan that breaks a cap.

### P4 — Compile nutrition targets to the right scope

- An unqualified numeric target — "about 500 kcal a night" — compiles to a
  `horizon_average` band over the slot set, plus a per-slot guard band applied
  as a soft penalty.
- Explicitly per-meal wording — "every dinner under 500 kcal" — compiles to a
  `per_serving` hard band.
- The compiled scope is echoed in the words the plan uses, so the user can see
  which reading was taken.

**Why the guard band exists.** A pure average is gameable by pairing extremes: a
300 kcal salad on Monday and a 900 kcal stew on Tuesday average out and satisfy
nobody. The guard band is a soft penalty on how far a single slot may sit from
the target, so the average is met by a plausible week rather than an arithmetic
trick. It is soft on purpose: one heavy Saturday should cost score, not
feasibility.

**Why the scope is echoed back.** These two readings produce genuinely different
plans, and the user said one sentence. Stating which reading we took is how they
catch us being wrong, at the only moment where correcting it is cheap.

Evaluation is unchanged: held-out episodes declare their own scope with no
default (`ADR-0025`), and the scorer recomputes from the frozen catalog. Do not
teach the scorer this product default.

*Done when* the two phrasings produce different plans on the same catalog, each
plan states its scope, and a plan meeting the average by pairing extremes scores
worse than an even one.

### P5 — Purchase across the whole slot set

Extend mixed-package selection from per-ingredient to the whole slot set, so one
larger package can cover demand that several slots share.

The per-ingredient case is already solved (`ADR-0021`): three slots each needing
100 g of rice, minus 50 g of pantry rice, is 250 g, and one 150 g pack plus one
100 g pack beats repeating either size. The unsolved case is across ingredients
and slots at once: two 500 g packs of chicken for four dishes rather than four
retail portions, where the saving only appears when demand is aggregated before
packages are chosen.

Arithmetic stays as `ADR-0021` requires: whole cents with no tolerance, integer
package counts, no invented stock, no unit conversion beyond the compatible-unit
rules, and an independent recompute of identity, coverage, cost and surplus.
One cent over a hard budget fails; a sub-cent price is a data problem to report,
not something to round into compliance.

Scale check before optimising: the packet has a few dozen ingredients and a few
package options each. `package_cp_sat.py` already exists for the exact answer on
small inputs. Measure first — if the exact solver returns in time on realistic
packets, use it and skip the heuristic entirely.

*Done when* a fixture whose per-ingredient optimum exceeds the budget becomes
feasible under whole-slot-set purchasing, the validator recomputes the basket
independently, and the improvement is reported as a cost and surplus difference
rather than asserted.

### P6 — Replan by changing only what must change

A single-slot edit, or a product snapshot that changed under an existing plan,
keeps every unaffected slot's recipe. The response states which slots changed
and how the shopping list differs.

**Why this is a correctness property, not polish.** A user who asks to swap
Friday and gets a different Monday, Tuesday and Wednesday has lost the work they
already approved, and has no reason to trust the next plan either. It also
unblocks a held-out category we currently cannot score: the multi-turn
replanning episodes have no invariant to check, because the system guarantees
nothing about what stays. This packet creates the invariant that makes those
episodes scorable.

Note the honest edge: a changed slot can force a shopping-list change that
touches an unaffected slot's *ingredients* — the same 500 g pack now covers less
— and that is fine. The invariant is about which recipe sits in each slot, not
about the basket being untouched. Say which changed and why.

Existing starting point: `backend/app/services/replanning.py` and
`snapshot_repair.py`.

*Done when* the invariant is asserted in tests for both triggers, the reported
difference matches the actual one, and a replan that reshuffles unaffected slots
fails a test rather than being noticed later.

### P7 — Learned ranking and free-text themes

- Record meal check-in feedback (cooked, skipped, swapped) in a form an offline
  replay can read.
- A reorder-only hook over the candidate list, **off by default**, that cannot
  admit a rejected candidate or alter any arithmetic.
- An offline replay harness that measures a ranking against recorded feedback.
  Until the held-out set is frozen, it runs on synthetic or developer data only
  (`ADR-0020` section 2 as amended by `ADR-0029` section 1).
- Theme translation: free text to values on the controlled parameter list, with
  everything outside the list dropped and the drop recorded in the trace.

**On the ranking.** There is no real user data yet, and there will not be much
during the course. Build the mechanism and prove it by replay; do not ship a
model trained on a handful of our own check-ins and call it personalisation.
The deliverable is an honest one: the loop exists, the measurement exists, and
the default is off.

**On themes.** The user says "lighter Korean food this week, and nothing fiddly
on weeknights". The model's entire job is to turn that into values on the
parameter list — cuisine affinity, an energy preference, an effort weight for
weekday slots. It does not choose recipes, does not add or remove hard
constraints, and does not touch arithmetic. When it produces something outside
the list — a new constraint, a specific dish, a budget — that output is dropped
and the drop is recorded. A silently honoured off-list instruction is a second,
softer path into the plan, which is exactly what `ADR-0001` forbids.

Effort rhythm is the same mechanism: difficulty and active minutes from the
released catalog, weighted per slot. No new machinery.

*Done when* the hook can be switched off with the plan still valid, the replay
harness reproduces a ranking comparison from recorded conditions, and a theme
asking for something off-list is visibly ignored rather than silently honoured.

### P8 — Evidence

- Ablation presets in the console experiment module: independent validation off,
  repair off, variety penalty off, overlap reward off, learned ranking off, beam
  search replaced by the greedy selector.
- Stress fixtures the acceptance runs against: infeasible by one cent,
  allergen-saturated candidates, pantry-heavy input, a price change between
  planning and purchasing, an unavailable retrieval provider.
- Reporting follows `ADR-0028`: per-category counts and failure mechanisms, no
  per-category success rates.

This is the packet that turns the rest into a claim anyone can check. An
improvement nobody measured against the baseline is an opinion.

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

## How to tell you did it well

Beyond the tests passing:

- **Someone else can replay your run.** Given the trace, a teammate reproduces
  the same plan without asking you anything.
- **The failure messages are ones you would accept as a user.** Read them aloud.
  If the sentence does not say what to do next, it is not finished.
- **Removing a component degrades rather than breaks.** Switch off the overlap
  reward and you get a valid, slightly costlier plan — not a crash and not an
  invalid one.
- **Nothing new hard-codes seven.** Grep your own diff for `7`, `week`,
  `dinner` before you open the PR.
- **The validator caught something.** If it has never disagreed with the
  planner, you have probably wired it to the planner's own numbers. Break the
  planner on purpose once and confirm the validator notices.

## Common ways this goes wrong

- Reporting bounded search exhaustion as infeasibility, and then cheerfully
  suggesting relaxations for constraints that were never the problem.
- Letting the validator read the planner's computed totals "to avoid
  duplication", which quietly removes the entire point of it.
- A suggestion that claims minimality the search did not prove.
- An overlap reward that is not bounded, which looks fine until one week where
  it outweighs nutrition.
- Replanning by regenerating everything and then diffing — the diff will look
  small most of the time, and will embarrass you the one time it does not.
- Recording experiment conditions incompletely, which makes the run unquotable
  and the work invisible.

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
| Search honesty | a bounded-search-exhausted result is never reported as infeasible and offers no relaxation |
| Caps | no weighting can produce a plan violating a variety cap |
| Scope | the two nutrition phrasings produce different plans, each stating its scope |
| Money | budget comparison stays exact in cents across whole-slot-set purchasing |
| Replan | an unaffected slot never changes, and the reported difference matches the real one |
| Determinism | the same packet, settings and seed give the same plan and the same trace fields |
| Learning | the ranking hook off by default, reorder-only, and removable with the plan still valid |
| Slots | no new code hard-codes seven slots or one meal per day |
| Evidence | each ablation runs from the console with its conditions recorded, and results follow `ADR-0028` |
