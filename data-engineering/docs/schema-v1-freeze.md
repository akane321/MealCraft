# Schema v1 freeze

> Status: **frozen**, effective this document's commit. Any additive field
> needs a proposal + a new `schema_version`; nothing here changes silently.
> This is the concrete implementation of the "accepted target" in
> [`docs/design/recipe-ingredient-data.md`](../../docs/design/recipe-ingredient-data.md)
> and the process ADR-0012 defined, evaluated against real full-dataset
> evidence rather than the 20-row synthetic pilot.

## Why now

Coverage thresholds and unknown-value semantics have to be declared before a
release is evaluated against them (ADR-0012, `docs/data/README.md` §3). Until
this point every number in this pipeline came from a 5,000–300,000-row sample.
The pipeline has since run cleanly on the **entire 1,643,098-row `Gathered`
set** (chunked to fit 16GB RAM; see `scripts/run_full_dataset.py`) with a
streaming `validate` pass reporting **zero errors** across all 1,642,647
recipes and 657,516 canonical/candidate ingredients. The numbers below are
measured on that full run, not extrapolated.

## What is frozen

### Schema version

`mealcraft.recipe.v1` / the matching `mealcraft.ingredient` shape in
`schemas/recipe.schema.json` and `schemas/ingredient.schema.json`, **including**
`servings` and `servings_basis` (added this round — see below). This is the
first point either schema has been declared frozen, so today's shape *is* v1;
there is no pre-`servings_basis` v1 to be compatible with.

### ID policy

- `RCP_<hex>` recipe IDs: a stable hash of `title` (casefolded) + the raw
  `ingredients` list, so re-running the pipeline on the same input reproduces
  identical IDs and duplicate source rows collapse to one recipe.
- `ING_<NAME>` canonical ingredient IDs: hand-assigned in
  `config/ingredient_aliases.csv`, human-reviewed.
- `CAND_<hex>` candidate ingredient IDs: a stable hash of the normalized
  ingredient phrase, auto-generated only when no alias matches. A candidate ID
  is not a claim that the ingredient is correctly identified — see
  `normalization_status`.

### Unit vocabulary

`config/units.csv` (~100 entries across `mass` / `volume` / `count` /
`package` / `informal` dimensions). Adding a unit is a reviewed config change
per `docs/team-workflow.md`, not a code change.

### Unknown-value semantics

- `null` always means "not stated in the source," never `0` and never a
  guess. Enforced throughout: `quantity_min`/`quantity_max`, `servings`,
  `prep_minutes`/`cook_minutes`, `cuisine`, all `nutrition.*` fields.
- `normalization_status ∈ {mapped, candidate, unresolved}` — `candidate` is a
  parsed, stable-ID'd guess at a *new* ingredient, not a reviewed fact.
- `servings_basis ∈ {stated_exact, range_lower_bound, null}` is the **only**
  sanctioned approximation in the schema: a source range ("Serves 10 to 12")
  is stored as its lower bound with `range_lower_bound` so it is never
  conflated with a source-stated exact count. See `src/mealcraft_data/servings.py` for the
  full extraction rules and why range-derived estimates are a conservative
  (not arbitrary) choice for a diet-planning consumer.

### Release-readiness gate (four conditions)

A recipe is **release-eligible for v1** only when every one of its ingredient
rows has:

1. `normalization_status == "mapped"` (not `candidate`/`unresolved`);
2. `quantity_min is not None`;
3. `unit_normalized` in a physically anchored dimension — `mass`, `volume`,
   or `count` (informal units like `pinch`/`dash` do not clear the bar, since
   they cannot support package/shopping arithmetic);

and the recipe itself has:

4. `servings is not None` (either basis).

Measured on the full 1,642,647-recipe run:

| Metric | Value |
| --- | --- |
| Ingredient-level mapping coverage | 81.77% |
| Ingredient-level quantity coverage | 91.97% |
| Ingredient-level unit coverage | 92.09% |
| Recipe-level servings coverage | 5.09% (83,689) — 3.43% `stated_exact` + 1.66% `range_lower_bound` |
| **Recipes clearing all four conditions** | **8,718 / 1,642,647 (0.531%)** |

(An earlier ad-hoc check during development used a hardcoded unit whitelist
that missed several valid `count`-dimension units — `clove`, `dozen`, `slice`,
`stick`, `square` — and undercounted this at 6,556. `scripts/cut_release.py`
is the authoritative gate and checks `unit_dimension` instead of a hand-listed
set of unit names, so it does not silently drift as `units.csv` grows.)

Servings is the binding constraint by two orders of magnitude — see
`HANDOVER.md` and `docs/recipenlg-5000-profile.md` for why loosening it further
is not done here (it would mean guessing, not extracting).

## Known gaps (not blocking v1, but not silently "done" either)

- **Nutrition stays `not_computed` for every recipe**, release-eligible or
  not. Computing it needs a servings count (now available for the
  release-eligible subset) **and** a reviewed ingredient→USDA mapping **and**
  a quantity→mass conversion path, none of which exist yet. This is R12's
  next real sub-project, not a v1 deliverable.
- **Allergen labels are deterministic-rule-only.** They come from
  `config/ingredient_aliases.csv`'s hand-assigned allergen column. A
  round-2 human review pass (`data/review/MealCraft_review_packet_round2*`,
  `safety_allergens` sheet) re-checked a random sample against the principle
  that `confirmed_allergens` at the canonical-ingredient level should record
  **Definite/inherent** allergen content only (an ingredient that always
  contains the allergen), not **Possible/conservative** exposure (an
  ingredient that sometimes does, e.g. via shared-facility or ambiguous-brand
  risk) — because this field feeds a hard-constraint filter, where
  over-labeling causes false positives (recipes wrongly excluded) without
  protecting anyone, rather than a soft warning where caution costs little.
  This is consistent with FDA's 9-category major-allergen list (milk, egg,
  fish, **Crustacean shellfish**, tree nuts, wheat, peanuts, soybeans,
  sesame; molluscan shellfish and coconut are *not* on it as of the FDA's
  5th-edition Food Allergen Q&A guidance, effective ~2025-01-06). Applying
  this round-2 review corrected 3 canonical ingredients (coconut milk,
  coconut flavoring/extract → no tree-nut label; imitation crabmeat → fish,
  not crustacean) and, in the process, caught and fixed a real pre-existing
  bug where `"imitation crab"` was wrongly aliased to actual crab
  (`ING_CRAB`, crustaceans). There is still no independently reviewed gold
  subset checking labelling precision/recall end-to-end on real recipes
  (ADR-0012's "safety-critical labels require deterministic rules *plus*
  review evidence" — only the first half is done). **Do not treat v1
  allergen labels as sufficient for a production hard-constraint safety
  claim** until that review exists (task #9 in the original data-engineering
  task list).
- **High-dimensional fields are empty by design**: `cuisine`, `meal_types`,
  `methods`, `equipment`, `difficulty`, `dietary_tags` are all `null`/`[]`
  for every recipe. No controlled vocabulary or coverage study exists for
  them yet; populating them is out of scope for this freeze.
- **`servings_basis = range_lower_bound` is an estimate, not a fact.** It is
  a documented, one-directional-safe approximation (see `src/mealcraft_data/servings.py`),
  not a source-verified number. Anything that needs to distinguish the two
  can filter on this field; the release manifest reports both counts
  separately for that reason.
- **`ambiguous_or`, `composites`, `safety_allergens`, `empty_after_parsing`
  review sheets are still open** (see `data/review/`). None of them gate the
  four-condition release filter above, but they represent known-incorrect or
  known-unreviewed rows in the *non*-released 99.6% of the dataset.

## Open questions (deferred — not decided by this pipeline)

These surfaced during the round-2 allergen review. Both are data-taxonomy
decisions (ADR-0012 territory), not parsing bugs, so they are recorded here
undecided rather than resolved unilaterally in config:

- **Is `molluscs` a legitimate allergen taxonomy category?** FDA's major-
  allergen list covers **Crustacean shellfish** only (shrimp, crab, lobster);
  molluscan shellfish (clams, mussels, oysters, scallops, squid) is not a US
  major allergen, though it is regulated/labeled in some other jurisdictions
  (e.g. EU). `config/ingredient_aliases.csv` currently has no `molluscs`
  category at all — molluscan ingredients carry no allergen tag. Before
  adding one (or before treating its absence as intentional), the team needs
  to decide which regulatory framework(s) `confirmed_allergens` is meant to
  satisfy; that scope decision should get an ADR, not a config patch.
- **A "layer 2" product-level allergen check does not exist.**
  `confirmed_allergens` labels the *canonical ingredient* ("butter" always
  has milk). It cannot capture genuine *product-instance* uncertainty (e.g.
  a specific "imitation crabmeat" brand that blends in real crab, or a
  margarine formulated with milk solids) — that needs a separate,
  not-yet-built check at the point of product selection, distinct from this
  recipe-level dataset. v1 does not attempt this; anything that surfaces
  `confirmed_allergens` to an end user as a safety claim should be paired
  with a product-level check, not treated as sufficient on its own.

## What changes this freeze

A new field, a changed unit-recognition rule, or a changed release-gate
condition all require bumping `schema_version` (e.g. `mealcraft.recipe.v2`)
and re-declaring thresholds against fresh full-dataset evidence — not editing
this document's numbers in place.

## v1.1 release (2026-09-17)

Same frozen schema, same four-condition gate, same `schema_version`
(`mealcraft.recipe.v1`) as above — nothing in "What is frozen" changed. What
changed is data quality: a round of human-reviewed config fixes
(`config/ingredient_aliases.csv` — new aliases, 3 allergen corrections
documented below, an `ambiguous_or` parser false-positive fix) improved
mapping coverage on the same full 1,642,647-recipe input. `dietary_tags`
went from always-empty to populated for release-eligible recipes, using the
field `schemas/recipe.schema.json` already declared (an array of strings) —
not a schema addition. A companion field, `dietary_tags_basis` (per-tag
`derived_true` / `derived_false` / `unknown_ingredient`), *is* new; a
recipe's `dietary_tags` list is only ever a positive claim, so this basis
map is what lets a consumer tell "confirmed not vegan" apart from "can't
tell" without it looking identical to a recipe that just isn't vegan (see
`scripts/derive_dietary_tags.py` for the derivation rules and
`scripts/build_dietary_origin.py` for the per-ingredient classification
behind it).

| Metric | v1 | v1.1 |
| --- | --- | --- |
| Ingredient-level mapping coverage | 81.77% | 82.5% |
| Ingredient-level quantity coverage | 91.97% | 91.97% (unchanged — round-6 didn't touch quantity parsing) |
| Ingredient-level unit coverage | 92.09% | 92.1% (unchanged) |
| Recipe-level servings coverage | 5.09% (83,689) | 5.09% (unchanged — round-6 didn't touch servings extraction) |
| **Recipes clearing all four conditions** | 8,718 / 1,642,647 (0.531%) | **9,282 / 1,642,647 (0.565%)** |
| Released canonical ingredients | 443 | 465 |
| `dietary_tags` populated, of released recipes | n/a (field always empty) | vegetarian 5,625 (60.6%) · gluten-free 4,507 (48.6%) · dairy-free 3,602 (38.8%) · vegan 1,030 (11.1%) |

The +564 released recipes come from round-6's added aliases raising mapping
coverage, not from any change to the release gate itself. `dietary_tags`
coverage is much lower dataset-wide than per-ingredient mapping coverage
because a recipe only gets a positive tag when *every* one of its
ingredients is mapped — the same compounding effect that makes the
four-condition gate itself select 0.565% out of 82.5% per-ingredient
coverage. Full-dataset (not just released-subset) `dietary_tags` numbers:
68.85% of all 1,642,647 recipes have at least one unmapped ingredient and so
carry no positive tag (`dietary_tags_basis` says `unknown_ingredient`, not
`derived_false`) — see `scripts/derive_dietary_tags.py`'s own output for the
full breakdown.

Round-6 also corrected 3 canonical ingredients' allergen labels (coconut
milk, coconut flavoring, imitation crabmeat) per the Definite-vs-Possible
principle described above, and fixed a real pre-existing bug where
`"imitation crab"` was aliased to real crab's crustacean allergen — both
already folded into the "Known gaps" allergen entry above, since that entry
describes the *current* state rather than a v1-frozen one.

Release artifacts: `data/release/v1.1/`. v1 was an additional release, not a
correction in place, and its artifacts were untouched by v1.1. v1 has since been
deleted from the repository under `ADR-0030` section 1, which makes v1.1 the
source release; this record describes the freeze as it stood.
