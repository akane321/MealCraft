# Algorithm follow-up inventory — 2026-10-25

This inventory describes the development branch, not merged product acceptance.
Human pair annotation is paused at the contributor's request. Full CI is run by
the contributor; local verification does not replace it.

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

## Still open

| Requirement | Current boundary | Next work or dependency |
| --- | --- | --- |
| Independent near-duplicate labels and 21 swaps | Paused; product still uses title kinds | Independent labels, frozen thresholds, then swap acceptance and matching validator integration |
| Member-mean product objective | Implemented offline; product remains table-based by instruction | Separate product decision before adoption |
| Global minimum and at most 5% gap | Offline exact references exist; product remains heuristic | Matched exact comparisons using identical product packets and shopping policy; no minimum-price claim without proof |
| Full parameter calibration | Parameter sweep uses single-dish developer cases; household comparison tests the current default | Composed-household parameter scan before selecting a new default |
| Fine-grained stage timing | Engine total and local improvement measured | Profile candidate generation, shopping and validation separately; current times exclude LLM and live lookup |
| Real-price evaluation | Both reports use fixture prices | Versioned observed-price snapshots, then matched comparison; fixture results cannot establish this criterion |
| Mixed packages in product | Mixed shopping optimizer and validator exist offline | Agree the multi-package-per-ingredient/trip output contract with the shopping/retrieval owners, then connect and test it |
| Other section 7 acceptance | Shared-dish, nutrition, feedback and relaxation components exist | End-to-end checks for variable dish counts, cross-week penalties, counterfactual refusals and mixed purchase |
| Genetic algorithm | Optional in the task plan | Deferred while existing methods still require product acceptance; no GA implementation claim |
| Final acceptance | Local developer diagnostics | Full CI and the remaining independent/exact/real-price evidence; final evaluation remains with its owner |

These reports do not close all of issue #310. A non-worsening weekly objective
does not mean every quality measure or the checkout price improves. A faster
setting alone is not grounds to reduce search breadth.
