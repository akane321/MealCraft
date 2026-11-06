# Algorithm follow-up inventory — 2026-10-27

This inventory describes the development branch, not merged product acceptance.
The contributor confirmed completion of the supplied human review; reviewer
identity was not recorded. PAIR-030 remains unsure and is excluded from fitting
and correctness counts. Full CI on #370 commit 69c1387 passed (run 40434611660). The new
sequential-swap test is locally verified and is not included in that CI run.

## Covered by this batch

- Product beam plans receive validated simulated annealing. The seed and every
  proposal retain per-meal budgets and requested minimum recipe counts. The
  scoring map contains exactly the recipes that survived packet validation.
- The product retains table `dish_kind` scoring and member eligibility checks.
  Under ADR-0095, a proposal that increases adjacent repeats is discarded in
  favor of the validated seed. Trace distinguishes the returned and discarded
  scores. Offline objectives and evaluation rules are unchanged.
- Checked-price searches use checkout-first improvement while retaining all
  product gates. This is a checked heuristic price, not a proven global minimum.
- The [parameter report](README.md) covers widths 8/16/32/64 and 0/50/200
  annealing proposals, each evaluated three times on fixed developer cases.
- The [household comparison](../product-household-comparison/README.md) covers
  all five full-default developer households, with the improvement off and on.
  Original JSON retains checks, meals and timing. Neither report changes a default.
- The [full parameter calibration](full-parameter-calibration-2026-11-06/README.md)
  covers the complete 8/16/32/64 width by 0/50/200-step matrix on all five
  full-default developer households, with three rotated matched repetitions and
  inclusive stage profiles. All 36 condition-runs passed. The matched evidence
  does not justify a production-default change, and none was made.

- A composed 21-dish preview regression requires all 21 swaps across seven
  three-role dinners to be accepted through the product API, including saved
  role identity and product dish-kind
  uniqueness. A separate sequential 21-slot regression checks confirmation,
  persistence, unchanged dishes, revisions and checkout deltas. Product swap
  thresholds are frozen as `product-swap-acceptance-v1`; the supplied review
  still does not establish independently attributable accuracy.

## Still open

| Requirement | Current boundary | Next work or dependency |
| --- | --- | --- |
| Independent near-duplicate labels and 21 swaps | Operational thresholds are frozen separately from exploratory fitting; product validation checks composed-meal dish kinds; 21 accepted composed-meal previews and 21 sequential confirmed swaps cover the product API on a fixed developer catalog | Obtain an attributable independent review and resolve the unsure pair. This is not full-catalog accuracy evidence |
| Member-mean product objective | Implemented offline; product remains table-based by instruction | Separate product decision before adoption |
| Global minimum and at most 5% gap | Matched fixed-catalog product references now cover up to 14 days and two trips; product remains heuristic | Broader catalog and observed-price comparisons; generated options and fixed packages do not prove global minimum |
| Fine-grained stage timing | Recommendation/candidate generation, meal-option generation, shopping, independent validation and objective instrumentation are implemented | Use these inclusive, overlapping timings in further matched scans; candidate generation includes its nested fixture grocery estimates, stages must not be summed, and they exclude LLM and live lookup |
| Real-price evaluation | The generated snapshot package-policy report compares fixed-product and exact mixed-package checkout on identical observed FairPrice facts and deterministic synthetic demands | Run a matched product-plan comparison on real household demands after product mixed-package wiring; this diagnostic is not a plan optimum or five-percent result |
| Mixed packages in product | Mixed shopping optimizer and validator exist offline | Agree the multi-package-per-ingredient/trip output contract with the shopping/retrieval owners, then connect and test it |
| Other section 7 acceptance | Shared-dish, nutrition, feedback and relaxation components exist | Cross-week recency is not wired: the product ranking boundary receives no household completion history, and ADR-0073 fixes only the qualitative bounded/fading behavior rather than a numeric decay policy. Define that input/policy and check/save cache consistency before wiring; complete end-to-end checks for variable dish counts, counterfactual refusals and mixed purchase |
| Genetic algorithm | Optional in the task plan | Deferred while existing methods still require product acceptance; no GA implementation claim |
| Final acceptance | Local developer diagnostics | Full CI and the remaining independent/exact/real-price evidence; final evaluation remains with its owner |

These reports do not close all of issue #310. A non-worsening weekly objective
does not mean every quality measure or the checkout price improves. A faster
setting alone is not grounds to reduce search breadth.

`PriceReferenceDomain` now makes the claim boundary executable: only an exact
full-supported-catalog comparison using mixed packages and an observed snapshot
may be labelled `real-minimum`. Current fixture/fixed-product references are
mechanically labelled `generated-domain-reference`, even when their measured
gap is within 5%.

The generated [real-price readiness audit](../algorithm-dev/real-price-minimum-readiness.json)
binds its counts to the observed snapshot digest. It records that the snapshot
contains many multi-product ingredients while the product packet retains one
selected product per line, candidate generation is bounded, and no joint exact
plan-and-purchase solver is wired. It is evidence that the requested conclusion
is currently unsupported, not a substitute minimum-price result.

The generated [matched snapshot packaging comparison](../algorithm-dev/snapshot-package-policy-comparison.json)
holds ingredient, demand, availability, package sizes and observed prices fixed
while comparing the current one-product-type checkout rule with the exact
mixed-package optimizer. Its demands are a deterministic developer grid derived
from package sizes, not household shopping demand, so it isolates packaging
policy value without claiming end-to-end plan quality or a real minimum.

Latest composed-household diagnostic: [0/50/200 steps](../composed-household-steps/README.md). All 15 runs passed their household checks; the six-person 200-step plan traded higher cost for more table dish kinds. No default was changed.

`md-dev-012` consistency review: the developer episode is stored under the
developer directory, identifies itself as `md-dev-012`, and its `feasible`
label has a recorded S$18.31 witness in the generated developer report below
the S$21.06 budget. The native search rejection is therefore not grounds to
change the label. The episode has no separate witness directory; its generated
developer result is the current executable witness carrier.
