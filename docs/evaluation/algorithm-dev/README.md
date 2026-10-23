# Recipe-pair developer calibration

`near-duplicates.json` records 16 pairs from the committed recipe catalogs,
their label reasons, measured signals and all selected-policy predictions.
Labels were drafted by the agent before computing the signals. They have not
been independently reviewed. These are development examples, not held-out data.

The script `scripts/calibrate_recipe_pairs.py` compares 150 threshold settings,
minimizing false merges before missed variants. The selected setting has zero
false merges and two missed variants on these same 16 pairs. Both misses are
fried-rice variants with cosine similarity below 0.70. This measures fit to the
development labels; it does not estimate accuracy on unseen recipes.

The explicit policy requires title overlap >= 0.20, ingredient overlap >= 0.05
and cosine similarity >= 0.70. Existing committed vectors are reused; running
the script makes no model request. The report records fixture and vector-source
digests. Edited recipes may need refreshed vectors before a future evaluation.

Run from the repository root with the backend on `PYTHONPATH`:

```text
python scripts/calibrate_recipe_pairs.py
pytest backend/tests/test_diversity_greedy.py -o addopts=-ra
```

The greedy integration test uses actual recipe quantities and nutrients, with
clearly synthetic product packages and prices. It verifies the connection from
pair classification to selection and independent validation. It does not measure
retail savings, latency at production scale or comparative algorithm quality.

## Search-arm smoke comparison

Budget checks apply separately to each shopping trip. The greedy arm also
checks an optimistic fractional cost for the whole remaining horizon: each
unfilled slot contributes its cheapest generated meal at unit prices, with
known pantry credited. It does not add separately rounded packages for each
future meal. The exact basket and independent validator still decide acceptance.
This lower bound deliberately grants the original pantry to each trip, so it can
miss a future shortage but cannot reject a plan by charging that pantry twice.
The experimental beam reserves places for low-checkout and low-usage-cost states.
Both searches track whether explicit recipe/ingredient minimums remain reachable;
request progress affects search order, not the final common objective.

An empty partial plan skips only soft selected-slot average nutrition while
being ranked. Complete plans still undergo the unchanged nutrition checks.
Unknown pantry quantities are never deducted, including in the native reference.

`scripts/compare_algorithm_dev.py` runs diversity-aware greedy, seeded GRASP
(8 total constructions, restricted list of 3) and first-improvement local
search (100 evaluated neighbors maximum). Local moves replace one meal or swap
two compatible meal assignments. All use the same candidate generator, ranking,
objective and independent validator. GRASP retains the deterministic seed;
local search accepts only strictly better validated solutions. Neither proves
optimality. Local search cannot repair a rejected seed in this version.

`search-smoke.json` retains three timing observations per arm and case, including
candidate generation and validation. Input preparation and recipe-vector loading
are outside the timer. Fixtures use two, three or seven dinners, including real
recipes with synthetic prices. Five methods found equal scores on the feasible
cases and rejected the over-budget case. Extra search did not improve these
examples. Randomized runs use seed 0; three repeats measure timing, not variation
across seeds. Broader datasets and multiple seeds remain pending.

The comparison also includes an experimental shared-objective beam (width 8,
1,000 expansion cap, retaining a greedy incumbent) and seven dinners using the
real-recipe fixture. This is separate from the product beam. The expanded fixture
has eight recipes; all five arms obtain six conservative representatives over
seven dinners. This narrow example does not establish the general five-main
acceptance target. Beam timing includes its
initial greedy run. A regression checks recovery when greedy fails a final
horizon nutrition bound, and another checks retention of a validated incumbent
when the expansion budget is exhausted.

Simulated annealing runs 200 proposals, with seed 0 and geometric temperature
1.0 to 0.01. Moves replace a meal or swap compatible meals. Every accepted
candidate passes independent validation; the best result is retained separately
from the current state. Acceptance of worse moves uses the first differing
score component divided by max(1, absolute current component). Final ordering
still uses the common lexicographic score. This is an explicit experimental
exploration policy, not a scalar reformulation or optimality guarantee.

`EnumeratedReference` checks every combination of the same generated meal
options, using the same validator and fixed shopping builder. For eight recipes
and three dinners, all 512 combinations were checked and all five algorithms
matched its best score. Seven dinners require 2,097,152 combinations and are
refused before enumeration by the report's 1,000-combination cap. Unknown
validation evidence prevents an optimality claim. No global catalog optimum or
optimized package-product combination is claimed. Percentage gaps stay null
because the score is lexicographic; exact score equality is reported separately.

The product's existing CP-SAT model still optimizes the old objective. A separate
offline `SharedScoreCpSat` reference now uses a bounded count-state table for
interchangeable, required, single-dish slots. Other packets use ordered meal-option
tables, retaining slot dates, roles, nutrition checks and shopping trips.
It does not implement a scalable native household constraint model.

For eight recipes over seven dinners, 2,097,152 ordered assignments become 3,432
canonical count states. Each state's shopping and validation are computed first.
CP-SAT receives the feasible table and minimizes each score component in order,
fixing the proven optimum before proceeding to the next. Exact ordinal levels
preserve the observed score ordering without floating-point scaling or weights.
The selected plan is independently validated again. Unknown evidence blocks an
optimality claim. `optimal_for_count_table` means optimal in this bounded table,
under the fixed shopping policy; it is not a full-catalog or package-optimization
claim. Table construction is enumerative, so this is an offline correctness
reference rather than a scalable native CP-SAT formulation. Ordered tables have
the same pre-enumeration state cap; oversized inputs are refused, not approximated.

All five search arms matched the seven-dinner count-table optimum. The report
preserves table-building and solver measurements separately. They are local
reference timings, not production performance results.

The composed-week fixture combines seven dinners, main/vegetable/optional soup,
hard per-meal/day/horizon calorie bounds, two shopping trips and 300 g pantry.
Its 128 ordered combinations were checked by both exhaustive enumeration and
the CP-SAT table reference; optimal scores match. All five search arms match
that optimum too. Tests verify pantry is deducted only once across trips and
impossible upper/lower bounds remain rejected. Prices and nutrition are synthetic
test values. This checks implementation, not dietary adequacy or retail savings.

The table references remain useful for small cross-checks. A separate direct
model is now available as described below.

## Direct meal-option model

`NativeSharedScoreCpSat` has one Boolean per generated meal option, with exactly
one option per slot. It never enumerates complete plans. Native constraints
encode the deterministic representative recurrence, repeated-pair counts,
ranking loss, per-day/horizon hard nutrition bounds, package ceilings, minimum
checkout across compatible individual products and sequential pantry deductions
across shopping trips. Local validation checks meal structure, safety, shares,
equipment, perishability and per-dish/per-slot hard nutrition before options
enter the model. The returned full plan is independently checked again, including
agreement between its score and all six model objective components.

Objectives are solved lexicographically. The next component is optimized only
after the previous optimum is proven. Time-limited runs are never labelled
optimal. Quantity scaling includes serving denominators; unsupported coefficient
precision is refused. Nutrition coefficients use 0.001 units, ranking 0.0001,
and product prices integer cents. Unknown local evidence prevents a proof.
The optimum is within generated options and the existing one-product-per-line
shopping policy, not over all catalog recipes or mixed product combinations.

Soft nutrition deviations and explicit recipe/ingredient repetition rules are
now encoded and checked against exhaustive reference cases. Aggregate soft
deviation uses rounded milli-nutrient margins and explicit normalization scales.
Current limitations: explicit legacy diversity policies are refused, and
aggregate nutrition requires required meal slots. Those cases can still use
bounded table references. This does not cover every household packet or replace
the product path.

`scripts/compare_native_algorithm.py` records the current run in
[native-scale.json](native-scale.json), including machine, source version,
solver workers and symmetry information. Recipe-count cases use developer
recipes, synthetic prices and exactly one dish per dinner. They do not measure
retail savings or end-to-end product latency.

The existing fixtures have no `PlanningSlot.members`. Member eligibility and
coverage come from the shared candidate generator and validator (ADR-0071);
these runs do not establish member-level algorithm quality. Nutrition bands
in these packets describe the whole table. Member-specific tests and comparisons
are a separate required delivery.

## Controlled speed comparison

`benchmark_native_speed.py` alternates three baseline/optimized runs on the
same 16-recipe, 14-dinner packet. `native-speed.json` preserves every timing and
score. The optimized model reduces quantity coefficients by an exact common
divisor, orders interchangeable meals within a shopping trip only when there
are no nutrition bands, skips constant objective stages, and uses four solver
workers instead of one. No objective component or hard constraint is dropped.
An earlier partial-hint experiment did not reliably improve time and was removed.

The historical observations remain in [native-speed.json](native-speed.json).
The reported median comparison of 5.13 s to 2.75 s used **one worker versus
four workers**, so it does not isolate the model changes. It used 16 developer
recipes and 14 single-dish dinners with synthetic prices and no slot members.
The original CPU model, core count and code version were not recorded; the JSON
says so rather than assigning today's machine or commit to old measurements.

Four seconds is not a pass threshold. ADR-0079 and its amendment ADR-0080 make
timing descriptive; product planning must not reduce quality or fail because of
a time limit. These offline solver comparisons retain an explicit diagnostic
limit and do not call a time-limited result optimal. Multiworker timings and
selected equal-score assignments may vary across runs and machines.

The benchmark generator records machine details, code commit, dirty-tree status
and each run's workers for future measurements. Fixture/vector preparation,
model calls, network and UI time are outside its timer. No held-out data or paid
model calls are used.
