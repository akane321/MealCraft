# Task B (nutrition mapping) — progress report

> Status: **in progress, not complete.** This is a checkpoint, not the task-B
> deliverable `enrichment-work-package.md` section 4 describes — that still
> needs the quantity→mass conversion and nutrient-aggregation steps this
> report explicitly flags as not started. Written 2026-09-18.

## 0. Baseline (re-measured, not trusted from the doc)

`enrichment-work-package.md` assumes 443 canonical ingredients. Round-6
review-sheet fixes (separate from this task) added 90 more, so the real
number going into task B is **533**, all with `fdc_id` null and `foodon_id`
null beforehand, matching the doc's own "measure it yourself first" step.

## 1. Reference datasets

Foundation Foods alone did not cover enough of the ingredient set to be
usable on its own, so this expanded through the doc's own fallback layers:

| Dataset | Entries | Coverage of 533 (name-token match) |
| --- | --- | --- |
| Foundation Foods (`2026-04-30`) | 469 | 191/533 (35.8%) |
| + SR Legacy (`2018-04`) | 7,793 | 428/533 (80.3%) |
| + FNDDS (`2024-10-31`) | 5,432 | 436/533 (81.8%, +1.5pp over the first two) |

FNDDS's marginal gain is small, but the download/manifest cost was already
paid, so it stayed in rather than being discarded. All three are registered
with source, URL and SHA-256 in `data/reference/usda-{foundation,sr-legacy,
fndds}-manifest.json`; the archives themselves are gitignored per this
project's existing pattern (`data/reference/downloads/**`), not committed.

## 2. Matching methodology (`scripts/build_nutrition_mapping.py`)

Deterministic token matching, not model-based guessing: a candidate is
eligible only when every word of the canonical ingredient name appears
somewhere in the candidate's FDC description. Three correctness fixes were
required after real errors surfaced during review — recorded here because
each is a mechanism a future dataset, not just this one, could trip over
again:

1. **Head-noun guard.** "Almond butter, creamy" is a token-superset match
   for "butter" (it contains the word "butter"), but it is a different food,
   not a variant of dairy butter. Fix: reject any candidate whose
   description is headed by a *different* canonical ingredient's own name
   (here, "almond") unless that word is itself part of the target name.
2. **Generic-term ambiguity detection.** Some names (`nuts`, `broth`,
   `meat`, `cheese`, `onion`...) have no single correct FDC analog — many
   candidates are genuinely different foods, or the only candidate available
   is a narrow, unrepresentative one (`radish` → "Radish seeds, sprouted,
   raw"; a fried-rice dish whose description merely says "without meat" was
   briefly `meat`'s only match). Detected by counting distinct qualifier
   patterns among tied top candidates, or flagging a lone candidate with a
   high extra-word count, and routed to `needs_review` instead of guessed.
3. **Benign-qualifier gate (the largest fix).** USDA's raw-commodity naming
   is verbose ("Peaches, yellow, raw") while its prepared-dish naming is
   terse ("Pie, peach"), so "fewest extra words" alone systematically
   favored desserts, lunch meats and meat-free substitutes over the actual
   plain ingredient: `bacon` → "Bacon, meatless", `milk` → "Sweetened
   condensed milk", `peach` → "Pie, peach", `zucchini` → "Muffin, zucchini",
   `beef` → "Bologna, beef". Fix: a candidate is only auto-accepted when
   every one of its extra words is on a small whitelist of genuine prep/
   cultivar terms (raw, dried, ground, canned, salted, whole, colors, ...);
   ranking also now searches **all three tiers** before choosing, since the
   first tier reached under a naive stop-at-first-match rule sometimes only
   had a bad candidate while a later tier had a clean one (`peach`'s "Peach,
   raw" was sitting in FNDDS while SR Legacy's "Pie, peach" would have won
   under the old rule).

`"X or Y"` composite canonical names (16 of them, e.g. "butter or
margarine") are routed straight to `unresolved` — picking either half would
misrepresent whichever a given recipe actually used; they belong in the
compute-from-components layer, not a single catalog lookup.

Confidence is `max(0.4, 0.95 - 0.08 × extra_word_count)`, forced down to
`min(confidence, 0.5)` whenever the ambiguity/guard logic above fires. The
confidence floor and status threshold (`mapped` requires `confidence ≥ 0.6`
**and** no guard triggered) are this pipeline's own coverage-vs-accuracy
call, per the doc's delegation of that decision — recorded here rather than
picked silently.

## 3. Results (533 canonical ingredients, all denominators shown)

| Status | Count | % |
| --- | --- | --- |
| `mapped` (auto-accepted, `fdc_id` written) | 213 | 40.0% |
| `needs_review` (candidate exists, not auto-trusted) | 209 | 39.2% |
| `unresolved` — `or_composite` | 16 | 3.0% |
| `unresolved` — `no_catalog_match` | 95 | 17.8% |

`mapped` by source tier: Foundation 50, SR Legacy 79, FNDDS 84 — FNDDS,
despite its small raw-coverage contribution, supplied the most *auto-
accepted* matches, because it happened to hold more plain/benign-qualifier
entries than SR Legacy did for the ingredients where both had *a* candidate.

`needs_review` breakdown: 175 `non_benign_qualifier` (a candidate exists but
its only extra words look like a different product, e.g. `tofu` → "Tofu
yogurt"), 33 `generic_term_multiple_variants` (name is a category, not one
food), 1 `sparse_weak_match`.

`no_catalog_match` (95) skews toward three categories: regional/branded
spice blends (garam masala, za'atar, herbes de provence, old bay
seasoning), flavor extracts (almond/orange/rum/coconut extract), and
branded or highly specific prepared products (tater tots, gnocchi,
crescent rolls). None of these are realistic Foundation/SR Legacy/FNDDS
entries; they would need the doc's layer 2 (other national DBs, license
permitting) or layer 4 (web, dated + URL) to close.

## 4. Known errors found (not left blank per the doc's own instruction)

Three concrete, previously-shipped errors were caught only because of
manual spot-checking, not by any automated check:

- `butter` → "Almond butter, creamy" (wrong food entirely)
- `nuts` → "Nuts, brazilnuts, raw" (arbitrary specific species for a generic
  term)
- `bacon` → "Bacon, meatless", `milk` → "Sweetened condensed milk`, `peach`
  → "Pie, peach" and several more of the same systematic pattern

All three are fixed in the current script (section 2). The fact that a
first automated pass produced 393 "mapped" results with these errors
sitting inside them, and a second pass (after the head-noun guard alone)
still had bacon/milk/peach-class errors, is itself evidence this class of
mistake is not obviously visible from the confidence score — **spot-
checking mapped output, not trusting the confidence number alone, is what
actually caught these.**

## 5. Spot check (per the doc's acceptance criterion — 20 items)

Two spot-check rounds were run against the *final* script, both on random
seeds:

- 12-item sample, seed 42: found 3 genuine errors (all three bug classes in
  section 2), leading to the fixes described there.
- 20-item sample, seed 99, taken **after** all three fixes: 0 errors —
  every entry (ketchup, coconut milk, cream cheese → "Cheese, cream",
  steak sauce, vanilla ice cream, rye flour, sesame oil, peas, raisin,
  onion soup mix, lemonade concentrate, ...) was a correct, representative
  match.

This is evidence the current `mapped` tier is in much better shape than the
raw confidence numbers alone would suggest, but it is a 20-item sample
against 213 mapped rows (9.4%), not an exhaustive audit — treat it as
supporting evidence, not proof of zero remaining errors.

## 6. Applied to the catalog

`scripts/apply_nutrition_mapping.py` wrote this back onto
`data/curated/ingredients.jsonl`: 211 ingredients got `fdc_id` set (213
mapped minus 3 whose canonical ingredients happen to have zero occurrences
in the current full 1,642,647-recipe run — `ground_turkey`,
`shredded_wheat`, `ground_pork` — so they never materialized as catalog
rows to begin with); 530 ingredients (every `mapped` + `needs_review` +
`unresolved` row that *does* have a catalog entry) carry the full
`nutrition_mapping` evidence object regardless of whether `fdc_id` was set,
so the "why" is visible even where the answer is "not confident enough."
`scripts/validate_streaming.py` passed with 0 errors on the resulting
1,642,647-recipe / 647,975-ingredient dataset. No release has been cut from
this state yet — that is a deliberate, separate decision, not an oversight.

## 7. Downstream impact

- `ingredients.jsonl` entries now often carry `fdc_id` and always carry
  `nutrition_mapping` where task B has touched them; nothing about the
  recipe schema (`schema_version: mealcraft.recipe.v1`) changed.
- **`recipe.nutrition.status` is still `not_computed` for every recipe.**
  A populated `fdc_id` is necessary but not sufficient: turning it into an
  actual per-recipe nutrition figure still needs (a) the FDC nutrient
  values themselves pulled from `food_nutrient.csv` and matched to a
  serving/measure, (b) a quantity→mass conversion path (density data,
  currently nonexistent for most ingredients), and (c) aggregation across
  a recipe's ingredient list, divided by servings. None of that exists yet.
- No other pipeline output (dietary tags, allergens, release gate) is
  affected by this work.

## 8. Network / API disclosure (per the doc's PR-writeup requirement)

Three one-time bulk CSV downloads from `fdc.nal.usda.gov` (official USDA
FoodData Central bulk-download mirrors, CC0 1.0): Foundation Foods, SR
Legacy, FNDDS. No calls were made to the rate-limited FDC search API
(`api.nal.usda.gov`). No other network access occurred.

## 9. Explicitly not done yet

- The 209 `needs_review` rows have no human decision recorded — they sit as
  `fdc_id: null` with their candidate and rejection reasons visible, not
  silently resolved either way.
- The 16 `or_composite` and 95 `no_catalog_match` rows have not been routed
  through layer 3 (compute from components) or layer 4 (web) yet.
- Quantity→mass conversion and actual nutrient aggregation into
  `recipe.nutrition` — not started; this is the largest remaining piece of
  task B.
- Task C (cooking time extraction) and task D (meal affinity) — not
  started.
