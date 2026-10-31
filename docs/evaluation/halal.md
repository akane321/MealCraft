# Halal in the evaluation

Contract: `docs/design/halal.md` (Knowledge ADR-0104). The scorers read the one set of labels
(`app.data.halal`); unknown is never halal.

## What fails a halal case

- **Baseline plans** (`baseline_validation`, check `halal_requirement`, hard on both bases): any mapped line that is
  `not_halal` or `uncertain` (a line with no label counts as `uncertain`), any unmapped line, or a
  `needs_certification` line (meat, and a pantry basic such as soy sauce, vinegar or mayonnaise) with no available
  certified product in the frozen snapshot (the product's
  `halal_certified` flag, or the offline facts `fairprice-halal-v1.json`). The validator's own halal rule is switched
  off for baselines (`episode_problem`), because a baseline dish has no recipe status for it to read.
- **Any system's common-shape answer** (`strict_success`, check `halal_respected`, added only to halal episodes): every
  selected recipe is `halal` or `needs_certification` over all its lines, and every `needs_certification` line with
  a quantity is bought only as certified products on the Shopping List. Such a line left off the list fails here,
  a pantry basic included.
- **MealCraft's own plans** go through the product validator, as before.

Certification is looked up with `app.data.halal.product_certified`, which reads a frozen id (`fixture:` and the
`<id>@<ingredient>` suffix of a product shared by two ingredients dropped) by FairPrice's own id, in the
baseline, strict and label code alike. `multidish_labels.check` proves the four developer cases with these facts.

## Basics that need a certified product (owner, 2026-10-31)

For a halal household the product does not take a pantry basic that needs certification (soy sauce, vinegar,
mayonnaise, ketchup ...) as at home (`household_slots.assumed_basics`): it is bought, as a Halal-marked product.
The evaluation follows, for halal cases only; the other cases and their digests are unchanged:

- **Baselines** (`BaselineResources.not_bought(household, halal=True)`): the basics a baseline may leave unbought
  leave out the names that need certification, so they are priced. A halal episode is one whose gold states
  `halal_required` (or whose profile states `requires_halal`). `baseline_validation` prices a halal case's shopping
  from certified products only for these lines, and `halal_requirement` fails one with no certified product.
- **Label proofs** (`multidish_labels`): a proof never took a basic as at home, it prices every line. A halal case
  buys a line that needs certification only as a certified product, in the v2 pool and eligibility
  (`_context`) and in the v3 witness weeks (`bought(..., halal=True)`, the product's `requires_halal`).
- **Strict scorer** (`halal_respected`): a basic that needs certification and is not bought as a certified product
  on the Shopping List fails, as meat does; "assumed at home" is not a purchase.

## Episodes

A halal episode states `halal_required: true` in `gold.applicable_hard_constraints`. The household profile may state
`requires_halal` (the switch); without it the request must carry the requirement, as in the Chinese case.

`data/evaluation/dev/halal-v1.json` holds four developer cases (protocol v2-multidish, one file with a list of
episodes; `multidish_runner --episodes` takes a directory or such a file): `halal-dev-001` pork-free but uncertified
meat, `-002` an ingredient of unknown status, `-003` a halal household of five for a week, `-004` the request in
Chinese. Pools are drawn by `multidish_pool` and every label is proven by `multidish_labels`. Developer cases only.

## Agent benchmark

`data/evaluation/agent/fixture-v1.json` states no halal expectation: none of its 24 messages mentions halal, and
`requires_halal` is dropped from the compared fields when false. Nothing assumes halal is declined. The halal
extraction cases are `cud-014`, `cud-099` and `cud-101` of `constraint-understanding-dev-v1.json`, which already
expect `requires_halal: true`.
