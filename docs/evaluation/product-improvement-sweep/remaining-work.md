# Algorithm follow-up inventory — 2026-10-27

This inventory describes the development branch, not merged product acceptance.
Engineering acceptance and the reproducible developer evidence listed below are
complete. The contributor confirmed completion of the supplied human review,
but reviewer identity was not recorded; PAIR-030 remains unsure and is excluded
from fitting and correctness counts. Independent attribution and global-minimum
evidence remain unresolved.

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
| Independent near-duplicate labels and 21 swaps | The frozen operational policy, composed 21-preview acceptance, and sequential 21-confirmation acceptance are complete on the fixed developer catalog; the supplied review still has no attributable reviewer identity and PAIR-030 remains unsure | Obtain an independently attributable review and resolve PAIR-030. The operational acceptance is complete, but this is not full-catalog accuracy evidence |
| Member-mean product objective | Implemented offline; product remains table-based by instruction | Separate product decision before adoption |
| Global minimum and at most 5% gap | Matched fixed-catalog and observed-price developer references now cover up to 14 days and two trips, with exact price-gap claim scoping; product remains heuristic and the evidence is not a full-catalog optimum | Provide a broader exact comparison over the supported catalog, mixed packages, and observed prices before making a global-minimum or ≤5% claim |
| Fine-grained stage timing | Recommendation/candidate generation, meal-option generation, shopping, independent validation, objective instrumentation, and the full matched parameter calibration are complete; timings remain inclusive and overlapping and exclude LLM/live lookup | No engineering work remains in this row; do not sum overlapping stages or turn developer timing into a product quality claim |
| Real-price evaluation | Matched observed-price household comparison is complete, using identical observed FairPrice facts and the product mixed-package path | No further acceptance work in this row; the comparison is developer evidence, not a plan optimum or ≤5% result |
| Mixed packages in product | Product wiring, planning/public grocery allocations, independent arithmetic and compatibility validation, FairPrice cart expansion, and matched observed-price household evidence are complete | No further acceptance work in this row; the evidence does not prove a global-plan optimum |
| Other section 7 acceptance | Shared-dish, nutrition, feedback, relaxation, mixed purchase, cross-week recency, variable dish counts, counterfactual refusals, and their focused product-path regressions are complete. The live household path applies the documented bounded 21-day recency decay; absent history is neutral. | No remaining engineering work in this row; broader full-catalog evidence stays under the separate independent-review and global-minimum rows |
| Genetic algorithm | Optional in the task plan | Deferred while existing methods still require product acceptance; no GA implementation claim |
| Final acceptance | Engineering acceptance and reproducible developer evidence are complete; the remaining blockers are independent attribution for PAIR-030 and proof of the global-minimum/≤5% claim | Obtain the independent review and broader exact observed-price comparison; do not close the issue or make global claims before both are resolved |

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
or more product allocations per line. Candidate generation remains bounded and
no joint exact plan-and-purchase solver is wired. The audit therefore removes
the product-contract blocker but still records that the requested global claim
is unsupported; it is not a substitute minimum-price result.

The generated [matched snapshot packaging comparison](../algorithm-dev/snapshot-package-policy-comparison.json)
holds ingredient, demand, availability, package sizes and observed prices fixed
while comparing the former one-product-type rule with the exact mixed-package
optimizer now used by product shopping. Its demands are a deterministic developer grid derived
from package sizes, not household shopping demand, so it isolates packaging
policy value without claiming end-to-end plan quality or a real minimum.
Both JSON artifacts have script `--check` modes and focused regression coverage
that fails when committed evidence differs from deterministic regeneration.

Latest composed-household diagnostic: [0/50/200 steps](../composed-household-steps/README.md). All 15 runs passed their household checks; the six-person 200-step plan traded higher cost for more table dish kinds. No default was changed.

`md-dev-012` consistency review: the developer episode is stored under the
developer directory, identifies itself as `md-dev-012`, and its `feasible`
label has a recorded S$18.31 witness in the generated developer report below
the S$21.06 budget. The native search rejection is therefore not grounds to
change the label. The episode has no separate witness directory; its generated
developer result is the current executable witness carrier.
