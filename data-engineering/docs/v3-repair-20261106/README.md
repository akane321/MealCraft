# Data release v3 repair (issue #426), 2026-11-06

What issue #426 asked for by 11-05/11-06, what was done, and what is left for people. All decisions in this folder
were made by an AI model (Claude, `claude-opus-5-5`, run as a workflow subagent), not by a person. The `reviewer`
column says `claude-ai (pending owner spot-check)`. The issue requires a real person in that column and a second
person's 20-recipe re-check; neither has happened yet.

## Files

- `decisions.csv`: one row per reviewed recipe. 391 main/side recipes hit by the six B patterns, plus the 37 recipes of
  the fat safety list (one, `RCP2_60CBCEBF9B73`, is on both lists). Columns: recipe_id, title, origin, course, list,
  patterns, decision (withdraw / servings / keep), servings_old, servings_new, reason, reviewer.
- `p4f-candidates.csv`: the 132 scan-P4f lines that are `estimated` and have a mass `correct_release_v22.stated_mass`
  can read (the issue's "125 rows" by the same rule on the 11-04 release), with what the build now does with each.

## A: cooked rice (P5a) and package mass (P4f)

`build_release_v3.py` rule 7, function `correct_v3_line`, run through `correct_release_v22.correct_recipe` (new
`fix_line` argument; the v2.2 classes and `correct_line` are unchanged) after the v2.2 correction. Changes go into
`corrections.jsonl` with classes `cooked_rice` and `package_mass`, so the manifest's `corrected_lines_by_class` counts
them. Owner decision 2026-11-04: a first-build record these classes change is exempt from rule 5 / check 2
(`verify` and `test_every_first_build_record_is_byte_identical`); v2.2's 8,968 records never change.

- `cooked_rice`: 39 lines in 39 recipes (19 first-build, 20 other added). The 11 v2.2 hits stay.
  - Rule: an `ING_RICE` or `ING_BROWN_RICE` line whose text says cooked, steamed, prepared, precooked or leftover
    before "rice" (not "uncooked", "dry", "raw", "makes"...) gets `cooked` in its preparation, so its form is
    `#cooked`.
  - A cup amount is re-weighed at the cooked form's cup (white 158 g, brown 195 g).
  - Assumption, written down as the issue asked: a line with no unit (e.g. "steamed rice, to serve", 370-740 g
    estimated) or a pouch keeps its grams. The estimate is read as cooked rice, so only the per-gram nutrition
    changes (365 to 130 kcal per 100 g for white rice).
  - A mass amount ("60 g steamed rice", v2.2) is left.
- `package_mass`: 108 lines in 105 recipes (51 first-build, 57 other added).
  - Rule: an `estimated` counted line takes the mass its own text states ("1 (14 ounce) can coconut milk" weighed
    as one cup = 226 g becomes 396.9 g) when that mass is more than 20% away. Lines already corrected, cooked lines
    and chicken lines are left.
  - Excluded:
    - drained, rinsed, optional or partly used text ("drain", "rinse", "out of the can", "start with", "half",
      "reserve", "only", "optional");
    - a recipe that does not eat it all ("pour out", "drink", "any or all" in the steps): beer can chicken, a choice
      of pizza toppings;
    - a can or jar of a food packed in liquid (beans, chickpeas, corn, peas, olives, artichoke, water chestnut,
      mushroom, fruit, onion, sauerkraut), since the net weight includes the liquid;
    - a recipe that marinates (the marinade is discarded);
    - masses the parser misreads ("(.25 ounce)" read as 25 oz, "1 pt. 2 oz.");
    - a stated mass more than 10x off the built grams (a typo such as "1/16 ounce" ramen).
  - Of the 132 candidates, 92 changed. Not changed: 24 liquid-packed cans or jars, 4 drained or partly used,
    4 marinades, 3 optional or not all eaten, 4 v2.2 records, 1 cooked form (`p4f-candidates.csv`). Split of the candidates: v2.2 4, first-build
    60, other added 68. 16 more changed lines are outside the scan's P4f (e.g. "14 1/2 ounce" cans, which the scan
    skips).
- Spot check, 10 changed recipes per class drawn with `random.Random(20261106)`, read by the AI (not a person), all
  judged reasonable:
  - `cooked_rice`: RCP2_3074DBBA42A1, 3E1A8D3A573A, 5BB7F02D0D9B, 8993605D4EA0, 09781E0F368B, A2BD17504D06,
    B71531D66E4F, A045C7FAA39F, BFB971F81726, A3FAA4E0CA8C. 92-185 g cooked rice a serving.
  - `package_mass`: RCP2_C4F2DAB5B1A0, 06BD5193D2D9, 12E6C1C8729C, 22B9CA19D67D, 426675F7EC7F, 02369FA0C7BF,
    B686D1183CDA, 5825C0738AED, 6C59131F0211, 4F7383D25A1E. Each new weight is the can or jar mass its text states.
- Tests: `test_build_release_v3.py` `V3LineClassesTest` (a hit and a no-hit case per class).
- Not done (written into `SHORTCUTS`): P4a, P4b, P4c, P4e, P5b, liquid-packed cans, and the v2.2 hits.
  The ADR-0111 amendment needs a paired Knowledge PR.

## B: withdraw broken recipes, fix absurd servings

- 391 main/side recipes (v2.2 217, added 174) from the six patterns in
  `../v3-quality-scan-20261104/hits.csv` (P7b, P3, P8d, P8e, P8f, P6h). The AI read each recipe's title,
  ingredients and steps.
  - withdraw 230 (v2.2 119, added 111): mostly steps that stop part-way, steps that are only a link or a note, or
    a main ingredient that is not listed.
  - servings 5 (added only): RCP2_001D96D38CEB 2 to 4, 037D595945A8 1 to 6, 175BE2BD8D3F 2 to 3,
    7FD933840208 1 to 4, C8133F6D4AC7 8 to 12. The last two are the reviewer's estimate, not a number in the source
    (their reason starts `estimate:`), so the build marks them `servings_basis: estimated`, confidence 0.6.
  - keep 156: optional dips and serving suggestions, implied steps, frying oil counted in full, false positives.
- Fat safety list, by the owner's rule (2026-11-04), as a script that can be run again:
  `python data-engineering/scripts/v3_fat_safety_scan.py`.
  - Rule: the steps say butter / buttered / ghee (not peanut butter and the like) or lard / bacon fat / grease /
    drippings, the list has no such line, and for butter or ghee the recipe is not labelled milk or is labelled
    dairy-free.
  - 34 butter and 4 lard/bacon hits in 37 recipes (the issue measured about 39).
  - withdraw 14 (v2.2 8, added 6); keep 23 (an oil alternative is offered, a serving suggestion, a "butter knife",
    "omit the butter").
  - The three named recipes, RCP2_21F314DDC0CC, RCP2_244D8C7CC69D and RCP2_A7EF75920F8A, are withdrawn.
- Where it went:
  - v2.2: 127 entries added to `data/recipes/withdrawn.json`, slug from `v3_corrections.recipe_slug`.
  - Added recipes: 117 withdraw rows and 5 servings rows in `data/enrichment/v3-corrections.csv`, then
    `v3_corrections.py withdraw` added 117 entries (a second run adds 0).
  - `withdrawn.json` now holds 246 entries.
  - `v3_corrections.py validate`: 122 rows, 0 problems.
- Sampled recipes these changes touch are noted in the `README.md` of `manual-check-20261103`,
  `manual-check-20261104` and `allergen-review-20261103`.

## C and D: known limitations

These were added to `build_release_v3.SHORTCUTS`, so they appear in `data/release/v3/quality_report.md`:

- serving carriers and optional dips (the planner adds a staple; an unreviewed carrier may carry gluten);
- salt, pepper, water, ice and greasing or frying fat taken as at home (sodium low, frying energy low; P1 hits are
  not a defect count);
- the A items left for later.

## E: meal_role tags

The code changes (E1-E4) and tests are in `backend/app/data/recipe_tags.py` and
`backend/tests/test_recipe_tags.py`. The re-ask route, its counts and what is left are in
`../tag-sample-20261103/README.md`.

The batch `recipe-tags-v1/llm-v3-20261103` was not accepted. All 233 of its values are `reviewed: false`, so the
planner treats those recipes as untagged (`meal_composition.unreviewed`, ADR-0094).

## Rebuild and scan, before and after

| | Before (11-04 v3) | After |
| --- | ---: | ---: |
| fingerprint | `fd33aba2ae94...` | `c9ce37569b0f...` |
| released / v2.2 / over-quota / wave 1 / wave 2 | 18335 / 8968 / 1867 / 2237 / 5263 | unchanged |
| corrections.jsonl lines | 638 | 785 (+39 `cooked_rice`, +108 `package_mass`) |
| scan P5a | 50 | 11 (all v2.2) |
| scan P4f | 181 | 96 |
| scan P6h | 73 | 68 |
| scan HP union / core union | 4771 / 2824 | 4684 / 2717 |

The scan does not read `withdrawn.json`, so the withdrawals do not lower any count.

## Planner pins that moved

- `test_walkthrough_1004_planning.py`: the offers for four and for two moved from S$42 / S$33 to S$64 / S$41.
  - Four people's cheapest week is now S$63.61; it was S$41.65.
  - The cheapest backed check is now S$33; it was S$32.
  - Cause, traced on both trees: the old S$42 week was Sesame Ramen With Green Peas (RCP2_C54503B406F8) with
    pickles. Its "1 (3 ounce) package ramen noodles" was weighed at 28.3 g and is now 85 g (`package_mass`).
- `test_ablation_switches.py`: re-measured on all 21 development episodes.
  - `local_improvement_off` no longer changes mdw-dev-007, so that case now uses mdw-dev-008.
  - No episode plans five different weeks any more. On mdw-dev-007, `repair_off` is now refused, and the test allows
    exactly that one refusal.
  - This changes the test's intent slightly; the owner should confirm it.
- `full_default`: PASS. `shared_dish`: PASS (0 violations). `app.evaluation` and `household_rules`: exit 0.
  - Their reports under `docs/evaluation/` were regenerated.
  - `workbench` was not run locally (CI runs it).

After merging the hand-recorded prices (issue #391), re-measured on both together:

- Same test: four people's offer is S$54 (cheapest S$53.15), two people's stays S$41, the budgeted check's cheapest
  stays S$33 (S$32 is the most it refuses). The S$54 week buys no hand-recorded product: it also plans at S$54 with
  the manual snapshot stubbed out, where the refusal still offers S$64. The larger pool changed the packet, so the
  cost-led search reaches it.
After a review of that merge blanked 11 hand-recorded price rows (multi-packs, a stand-in, oversize packs;
`docs/design/manual-prices.md`) and rule 7 left three more package lines alone, re-measured again:

- No pin moved: four people's S$54, two people's S$41 and the S$32 refusal boundary all pass unchanged. Those weeks
  buy no hand-recorded product, so the blanked rows do not reach them.
- Coverage is 609 of 699 (87.1%), 17,568 of 18,334 recipes (95.8%). The 90% target is not met; the blanked rows can
  be recorded again with a single-unit product.
- The planning pool is 16,126 recipes, 13,273 filling a planner role. 239 of the 246 withdrawn recipes count in the
  report's "withdrawn" row; the others already fall at an earlier gate.

## Left for people

1. Owner spot-check of `decisions.csv`, then the second person's 20-recipe re-check (10 withdraw, 10 keep). Put a real
   name in the reviewer column of `v3-corrections.csv` and `withdrawn.json`.
2. A real person checks 10 changed recipes per A class.
3. E: the two-person calibration on `../tag-sample-20261103/calibration-30.json` (at least 24/30), then the 40-recipe
   scoring of the new `sample.xlsx`. If it reaches 36/40 with no savoury main or side tagged sauce, dessert or drink,
   the owner accepts the batch. Also decide whether people label the main/side recipes E1 no longer asks.
4. Knowledge PR: an ADR amending ADR-0111 rule 5 (owner decision 1) and the reasoning for this PR (ADR-0053).
