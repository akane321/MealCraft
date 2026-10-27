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

- A sequential 21-slot swap regression checks preview isolation, confirmation,
  persistence, unchanged other dishes, revision increments and checkout deltas.
  It does not supply independent human similarity labels or freeze thresholds.

## Still open

| Requirement | Current boundary | Next work or dependency |
| --- | --- | --- |
| Independent near-duplicate labels and 21 swaps | Supplied review recorded; development rule and replacement gate implemented; product planning still uses title kinds | Independent validation beyond the fitted pairs; resolve unknown evidence and complete swap acceptance. Both independent previews and 21 sequential confirmed swaps are covered on a fixed developer catalog; this is not full-catalog acceptance |
| Member-mean product objective | Implemented offline; product remains table-based by instruction | Separate product decision before adoption |
| Global minimum and at most 5% gap | Matched fixed-catalog product references now cover up to 14 days and two trips; product remains heuristic | Broader catalog and observed-price comparisons; generated options and fixed packages do not prove global minimum |
| Full parameter calibration | Parameter sweep uses single-dish developer cases; household comparison tests the current default | Composed-household parameter scan before selecting a new default |
| Fine-grained stage timing | Candidate generation, shopping, validation and objective instrumentation implemented | Use these inclusive, overlapping timings in further matched scans; they exclude LLM and live lookup |
| Real-price evaluation | Both reports use fixture prices | Versioned observed-price snapshots, then matched comparison; fixture results cannot establish this criterion |
| Mixed packages in product | Mixed shopping optimizer and validator exist offline | Agree the multi-package-per-ingredient/trip output contract with the shopping/retrieval owners, then connect and test it |
| Other section 7 acceptance | Shared-dish, nutrition, feedback and relaxation components exist | Cross-week penalties still need historical input and check/save cache consistency; complete end-to-end checks for variable dish counts, counterfactual refusals and mixed purchase |
| Genetic algorithm | Optional in the task plan | Deferred while existing methods still require product acceptance; no GA implementation claim |
| Final acceptance | Local developer diagnostics | Full CI and the remaining independent/exact/real-price evidence; final evaluation remains with its owner |

These reports do not close all of issue #310. A non-worsening weekly objective
does not mean every quality measure or the checkout price improves. A faster
setting alone is not grounds to reduce search breadth.
