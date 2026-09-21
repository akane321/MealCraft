# Recipe and Ingredient Data Engineering Handoff

## 1. Why this module exists

This module converts heterogeneous recipe sources into a trustworthy,
versioned catalog that MealCraft can plan with, price against FairPrice,
explain to users, and freeze for comparative evaluation. It is not a general
web-scraping exercise and success is not measured by raw row count alone.

The final goal is a catalog in which every released fact has clear semantics,
provenance, missing-value behaviour, and a named downstream use. A released
recipe must be safe to filter deterministically, sufficiently quantified for
shopping arithmetic, and reproducible from a recorded source and pipeline
version.

This document is the implementation and hand-off guide. The shorter
[Recipe and Ingredient Data Contract](../design/recipe-ingredient-data.md)
remains the canonical cross-module contract.

## 2. Status language and current boundary

| State | Meaning |
| --- | --- |
| Verified baseline | Merged runtime behaviour supported by current code and tests |
| Released data | A versioned release cut by the `data-engineering/` pipeline; release v2.1 is imported beside the curated catalog |
| Accepted target | The intended module responsibility and release contract |

The curated runtime catalog is the compact one in `data/recipes/recipes.json` and
`data/ingredients/ingredients.json`, loaded by `backend/app/data/catalog.py`.
Held-out episodes, planning fixtures and tests name its slugs, so it stays as it is.

Release v2.1 is loaded beside it by `python -m app.data.import_release_v2`
(`backend/app/data/release_v2.py`), which compose runs after the curated import:

- release recipes carry `release_version` (`v2.1`), `external_id` (the release
  `recipe_id`) and a slug `v2-<title>-<id suffix>`, plus the release-only fields
  course, meal types, difficulty, passive time, time and servings basis,
  recipe allergens, source/licence and video URL. Curated recipes leave all of
  these NULL.
- Release allergen names map onto the runtime vocabulary: milk→dairy,
  eggs→egg, peanuts→peanut, tree_nuts→tree_nut, crustaceans and
  molluscs→shellfish, gluten_candidate→gluten. Sulfites have no runtime name and
  are dropped; a request naming them is already unverifiable for every recipe.
- Ingredient lines are stored in grams (`unit = "g"`) with the source wording in
  `original_text`. A weight that rounds to 0 g is stored as an unknown quantity.
  Ingredients whose normalized name matches a curated one reuse that row, and
  its allergen list only grows.
- Recipes with fewer than two ingredient lines are skipped and listed.
- Rows of an earlier release are upgraded in place by `external_id`, so a
  database that held v2 keeps its recipe ids (and the meal plans pointing at
  them) when v2.1 arrives.
- `catalog_imports` records the release digest, which includes the importer
  version. A rerun with the same files does nothing; changed files or importer
  logic re-import, and release recipes no longer in the release are deleted
  unless a meal plan references them.

Release v2.1 differs from v2 only in what the build checks (`data-engineering`,
[quality report](../../data-engineering/data/release/v2.1/quality_report.md)):

- Some RecipeNLG sources list only part of a dish (a crab quiche listing only its
  crust), so allergens derived from the lines miss what the dish contains. A
  recipe whose title or steps name a food carrying an allergen no listed
  ingredient carries was reviewed one by one
  (`data-engineering/scripts/recipe_completeness.py`): 220 found incomplete are
  dropped, 670 whose mention is a serving suggestion or not the food are kept,
  and a flagged recipe no review has seen is dropped. Look-alike phrases keep
  the allergen they carry ("peanut butter" is peanut, "almond milk" tree nut)
  and false friends are removed ("cream of tartar", "eggplant"). A fixed-seed
  sample of 300 recipes the check did not flag, reviewed in full, found one
  incomplete (an unlisted mayonnaise); the word list was extended after it. The
  owner's audit of 40 decisions accepted 39 and found no wrong keep
  (`data-engineering/docs/completeness-v2.1-sampled-audit.json`).
- Ten ingredients carry owner-confirmed allergen additions, only ever stricter
  (`data-engineering/config/allergen_corrections.csv`): butter or margarine and
  margarine (dairy), the three condensed cream soups (dairy, gluten), tortilla
  and crisp rice cereal (gluten), egg substitute (egg), imitation crab (fish,
  egg, gluten, shellfish) and clam juice (shellfish).
- An ingredient carrying fish or shellfish makes a recipe neither vegetarian nor
  vegan (kimchi in a fried rice), and so does a title or step naming meat or fish.

### FairPrice products for release v2 ingredients

Release ingredients are priced through a reviewed mapping, not the name matcher
(which serves the curated ingredients it was tuned on and paired generic
release names with wrong products). The mapping follows
[FairPrice Product Grounding](../design/fairprice-product-grounding.md):

- `data-engineering/scripts/capture_fairprice_snapshot.py` searched FairPrice
  once per ingredient, then again with the reviewer's suggested texts for those
  still unmatched, and keeps every raw result with its query and time
  (`data-engineering/data/enrichment/fairprice/v2/observations.jsonl`).
- `data-engineering/scripts/fairprice_mapping.py` packs each ingredient with its
  candidates for review, validates the proposals and merges them into
  `mapping.jsonl`: status (`mapped`, `unavailable`, or `not_purchased` for tap
  water and ice), the selected products with each pack expressed in grams of the
  ingredient and how (printed weight, volume x density, count x grams per piece,
  drained weight for canned food in liquid), rejected near-matches with reasons,
  and a confidence. Proposals are AI-made and stay `proposed` until the owner's
  sampled review records a verdict (`fairprice_mapping.py record`).
- `export` writes the runtime view, `data/products/fairprice-v2-snapshot.json`.
  It leaves out unavailable ingredients, mappings the owner marked for
  correction, and mappings below confidence 0.6, which are substitutes (dried
  for fresh herbs) or rough yield estimates rather than the ingredient.

At run time (`choose_product` in `backend/app/planning/grocery_estimator.py`) a
mapped ingredient buys the in-stock selected product that is cheapest for the
quantity needed, not cheapest per gram. In live pricing mode the ingredient's
recorded query is searched and only its reviewed product ids are accepted, with
the mapped pack weight; if none comes back the line stays unpriced with a
visible warning. Curated ingredients keep the name matcher and use the mapping
only when it finds nothing convertible, so curated plans and evaluation outputs
do not change. Weekly plans and replacements load only recipes whose every
ingredient is priceable (`RecipeRepository.list_for_planning`), and the planner
receives as many of the best-scored candidates as its beam budget can visit
(`ProductPlanningEngine._packet_limit`).

The pipeline lives in [`data-engineering/`](../../data-engineering/README.md):
RecipeNLG schema v1 is frozen, releases pass a four-condition gate, and each
release carries a manifest and quality report under
`data-engineering/data/release/`. Release sizes, enrichment progress and what
is not yet imported are recorded only in [Current Status](../current-status.md).
Released data is not runtime behaviour until an import is merged.

## 3. Final product target

The accepted end state is a versioned catalog release that supports all of the
following without silent guessing:

1. deterministic allergen and diet filtering;
2. user-supplied calorie and macronutrient constraints, with explicit
   nutrition basis and completeness;
3. known-quantity pantry deduction and ingredient demand aggregation;
4. ingredient-to-FairPrice product mapping and package arithmetic;
5. preference retrieval using only defined and sufficiently covered fields;
6. reproducible Rule-only, LLM-only, MealCraft and human-planning comparisons;
7. traceable correction when a source, parser or mapping rule is wrong.

There is no fixed recipe-count target (decision ADR-0024 withdrew the earlier
150-250 range). Every released recipe must pass the release gate, and the
canonical ingredients must cover every released recipe and every benchmark
grocery demand. A smaller release whose quantities, safety labels and
provenance hold up is preferable to a larger one that cannot support planning
claims.

Every release must provide:

- 100% schema-valid released rows;
- 100% source and transformation provenance for released recipes;
- explicit `known`, `unknown`, `not_applicable`, or `unresolved` semantics for
  fields used by constraints or metrics;
- independent review, or an explicit unresolved state, for safety-critical
  allergen and diet labels;
- stable IDs and versioned controlled vocabularies;
- a machine-readable quality report and release manifest;
- frozen fixtures or a catalog digest for downstream tests and Evaluation.

Coverage thresholds for ingredient resolution, quantities, units, nutrition
and product mapping must be declared before a release is evaluated. They must
be calculated over the full release candidate, not only easy or matched rows.

## 4. Source portfolio and legal boundary

| Source | Intended role | Storage and use rule |
| --- | --- | --- |
| RecipeNLG | Large-scale raw recipe text and ingredient parsing input | Research/education and non-commercial terms must be accepted by the person downloading it. Keep the raw archive outside the public repository; do not redistribute it through MealCraft without a documented licence decision. |
| RecipeDB | Optional nutrition-, process-, and utensil-rich comparison or supplementation source | Confirm the applicable CC BY-NC-SA terms and required attribution before importing or redistributing records. |
| FoodOn | Controlled food names, synonyms and ontology identifiers | Record the release/version and attribution; use as a candidate reference, not automatic truth for a particular recipe phrase. |
| USDA FoodData Central | Nutrition reference and portion candidates | Record FDC IDs, data type, release date, nutrient basis and matching decision. Prefer versioned downloads for batch work; use the API only for bounded checks. |
| SG FoodID | Singapore-specific nutrition cross-check and terminology | Use for manual or approved reference workflows; do not bulk scrape unless an explicit access and redistribution basis is documented. |
| FairPrice | Current product, package, availability and price grounding | Owned by the separate FairPrice module. Recipe data emits canonical ingredient demand; it does not copy volatile product observations into recipe truth. |

Canonical source pages:

- [RecipeNLG dataset and terms](https://recipenlg.cs.put.poznan.pl/dataset)
  and [source repository](https://github.com/Glorf/recipenlg);
- [RecipeDB](https://cosylab.iiitd.edu.in/recipedb/);
- [FoodOn](https://github.com/FoodOntology/foodon);
- [USDA FoodData Central downloads](https://fdc.nal.usda.gov/download-datasets/)
  and [API guide](https://fdc.nal.usda.gov/api-guide/);
- [Singapore HPB SG FoodID](https://www.hpb.gov.sg/healthy-living/food-and-beverage/sgfoodid/).

Open Food Facts may be useful for exploratory barcode or package metadata, but
it is crowd-sourced and is not evidence that a product is currently sold by
FairPrice. Its ODbL obligations must be assessed before any derived database is
redistributed.

API keys, authenticated downloads, raw restricted datasets, and local cache
files must never be committed. Store only allowed fixtures, manifests, derived
records whose redistribution is permitted, and source citations.

## 5. Data-layer architecture

```text
external source
  -> raw snapshot + checksum + source manifest
  -> parsed staging records that preserve original text
  -> normalization candidates + automatic validation
  -> resolutions recorded with evidence (rules, or an agent under ADR-0024)
  -> curated canonical ingredients and recipes
  -> quality gates + release manifest
  -> runtime import and frozen evaluation fixtures
```

The layers have different responsibilities:

| Layer | Mutable? | Required contents | Must not do |
| --- | --- | --- | --- |
| Raw | Append-only snapshot | Original bytes, source ID, retrieval time, checksum, terms/version | Be edited in place or committed when redistribution is restricted |
| Staging | Regenerable | Parsed fields, original ingredient strings, parser version, parse warnings | Replace unknown values with invented facts |
| Candidate | Regenerable | Alias, unit, FoodOn, USDA and duplicate candidates with scores and reasons | Treat rank or confidence as reviewed accuracy |
| Review | Auditable | Reviewer decision, timestamp, decision reason, previous value | Erase rejected candidates or decision history |
| Curated | Versioned | Canonical ingredient and recipe records that pass release policy | Depend on undocumented local corrections |
| Release | Immutable | Catalog version, input/output hashes, code revision, metrics, known gaps | Change silently after evaluation begins |

The public repository should ultimately contain code, schemas, controlled
configuration, permitted small fixtures, curated release artifacts, quality
reports, and manifests. Large or restricted raw files belong in a documented
local/object-storage location and are referenced by checksum rather than copied
into Git.

## 6. Canonical storage artifacts

The integrated module should converge on these versioned artifacts. JSONL is a
convenient pipeline interchange format; the runtime may import the release into
PostgreSQL or serialize the compatible subset to the current JSON catalog.

| Artifact | Purpose | Minimum identity |
| --- | --- | --- |
| `source_registry` | Terms, attribution, source owner and permitted uses | `source_id`, version/date, URL, licence/use status |
| `raw_manifest` | Reproduce a downloaded snapshot | source ID, captured time, filename, byte size, checksum |
| `recipe_staging` | Preserve parsed and original source content | source recipe ID, raw text link, parser version, warnings |
| `ingredient_alias` | Map spelling, language and phrase variants | alias, canonical ID/candidate, locale, rule/source, status |
| `unit_vocabulary` | Normalize quantity units without unsafe conversion | raw unit, canonical unit, dimension, conversion rule, status |
| `canonical_ingredient` | Shared ingredient identity and reference links | stable ID, canonical/display name, aliases, safety, provenance |
| `canonical_recipe` | Planner-ready recipe facts and steps | stable ID, ingredient rows, servings, time, tags, nutrition, provenance |
| `mapping_review` | Retain candidate and reviewer history | object ID, candidate, score, decision, reviewer, reason, time |
| `quality_report` | Gate a release with denominated metrics | release candidate ID, counts, coverage, errors, gate outcomes |
| `release_manifest` | Freeze downstream input | catalog version, schema version, code revision, hashes, known gaps |

## 7. Canonical ingredient contract

A canonical ingredient should support these field groups. Fields may be null
only when the missing-state semantics are explicit and downstream behaviour is
defined.

| Group | Representative fields | Rule |
| --- | --- | --- |
| Identity | `ingredient_id`, `canonical_name`, `display_name`, `language` | Stable across spelling changes |
| Aliases | raw alias, locale, source, status | Alias and preparation text do not create a new food identity |
| Classification | food group, parent ingredient, variant | Controlled vocabulary and source required |
| Safety | allergen categories, diet compatibility, review state | Safety labels require deterministic rules plus review evidence |
| Quantity | canonical dimension/unit, density, piece weight | Density or piece conversions require a cited source and applicability |
| Nutrition link | reference source, FDC ID, basis, matched description, confidence, rejected alternatives | Only a `mapped` resolution carries an FDC ID; `needs_review` is a candidate, not a fact |
| Provenance | source, extraction/rule, version, reviewer | Every accepted value can be traced |
| Quality | completeness, resolution status, flags | Confidence is a triage score, not a truth probability |

For example, `two chopped tomatoes` should preserve the original phrase and
separate it into canonical `tomato`, quantity `2`, unit `piece`, and preparation
`chopped`. If the mass of one tomato is not sourced for the relevant variety,
the pipeline must not invent a gram conversion.

Composite phrases such as `salt and pepper`, `soup mix`, or `mixed vegetables`
must remain unresolved/composite or be decomposed under an explicit reviewed
rule. They must not be forced into whichever FoodOn or USDA candidate happens
to rank first.

## 8. Canonical recipe contract

Each released recipe should include:

- stable recipe ID, title, language, source recipe ID/URL, licence/use status,
  capture time, schema version and pipeline version;
- servings and preparation/cooking/total time with missing flags;
- cuisine, meal type, cooking method, equipment, taste and difficulty only
  where a controlled vocabulary and sufficient coverage exist;
- ordered ingredient rows containing original text, canonical ingredient ID,
  quantity, unit, preparation, optional flag, resolution status and provenance;
- allergen and dietary tags derived from ingredient composition and documented
  rules, rather than copied blindly from source text;
- per-serving calories, protein, carbohydrate, fat, sodium and sugar with
  source, basis, calculation method, completeness and uncertainty flags;
- ordered instructions and optional media with source/usage provenance;
- validation state, reviewer state and release version.

The current runtime format remains supported during migration. New fields
should first be added to a versioned schema and import adapter; consumers should
not parse ad hoc pipeline files directly.

## 9. Normalization and resolution policy

Automatic processing and agent resolution are accepted paths when every
resolved value records its evidence (decision ADR-0024): the candidate chosen,
the source it came from, a confidence, and the alternatives rejected. Human
review is a sampling audit of those records, not a gate on each one.

1. Preserve the raw value before parsing.
2. Parse quantity, unit, ingredient phrase and preparation separately.
3. Resolve exact aliases first.
4. Generate ranked candidates for unresolved values.
5. Validate dimensions and cross-field consistency.
6. Resolve with recorded evidence, or leave the row explicitly unresolved or
   composite.
7. Rebuild curated outputs deterministically from raw inputs, configuration and
   recorded resolutions.

Allergen labels are the exception: they are derived only by deterministic rules
over canonical ingredients, never by agent inference, and an unknown allergen
status excludes a recipe rather than admitting it.

The following are prohibited:

- accepting a FoodOn or USDA candidate without recording why it won;
- treating `0` as missing nutrition or quantity;
- converting count, volume and mass without a sourced conversion;
- deriving disease-specific medical advice from recipe data;
- producing a serving size, nutrient value or allergen fact with no recorded
  basis;
- changing a previously frozen evaluation catalog without a new version.

## 10. Quality gates and metric definitions

Every metric must report numerator, denominator and excluded states.

| Metric | Definition |
| --- | --- |
| Schema-valid recipe rate | valid released recipe candidates / all release candidates |
| Ingredient occurrence resolution | occurrences linked to reviewed canonical IDs / all ingredient occurrences |
| Quantity coverage | occurrences with parsed numeric quantity / all ingredient occurrences |
| Recognized-unit coverage | occurrences with a controlled unit / all ingredient occurrences containing or requiring a unit |
| Safe conversion coverage | occurrences with direct compatible units or reviewed conversions / occurrences requiring grocery conversion |
| Provenance coverage | released facts with required source and transformation fields / all released facts in scope |
| Nutrition completeness | known values / required nutrient fields, reported per nutrient and source |
| Duplicate rate | confirmed duplicate records / all release candidates |
| Label precision/recall | measured on an independently reviewed subset with the gold-label procedure recorded |
| Inter-reviewer agreement | agreement statistic on overlapping review items, stratified by subjective field |

A release fails if a schema, safety, provenance or deterministic-rebuild gate
fails. Coverage below a predeclared threshold may either fail the release or
disable the corresponding planner/evaluation capability; it must not be hidden.

## 11. Cross-module hand-off

### Planner and Agent

Provide a frozen recipe catalog version with stable IDs, constraint fields,
nutrition completeness and explicit unresolved states. The Agent may help parse
user intent, but the recipe catalog owns food facts and the deterministic
planner owns constraint enforcement.

### FairPrice grounding

Provide canonical ingredient ID, required quantity/unit, accepted conversions
and substitution eligibility. Receive product observations through a separate
versioned ingredient-product mapping. Do not store live price or availability
as a permanent recipe attribute.

### Frontend

Provide display names, ingredients, steps, nutrition basis, provenance and
degraded/unknown states through an API or import adapter. The frontend should
not infer safety or silently hide incomplete facts.

### Evaluation

Provide an immutable Evaluation Packet containing catalog version, hashes,
available fields, missingness profile and mapping coverage. Every baseline must
receive the same eligible recipe and FairPrice facts required by its declared
information condition. Claims whose upstream readiness gate is unmet stay
deferred.

## 12. Parallel two-person workflow

The work can be divided into two independently testable lanes without binding
it to personal names.

| Lane | Main responsibility | Independent fixture | Hand-off artifact |
| --- | --- | --- | --- |
| Source and parsing | source registry, download manifest, raw/staging schema, quantity-unit-preparation parsing, duplicate candidates | synthetic and permitted small RecipeNLG-shaped rows | parsed JSONL, parser report, raw manifest, known parse failures |
| Curation and release | aliases, canonical IDs, FoodOn/USDA candidates, review queue, safety/nutrition validation, release gates | frozen staging fixture supplied in Git | reviewed mappings, canonical JSONL, quality report, release manifest |

Each lane must be runnable against a frozen fixture even while the other lane
is being improved. A hand-off is complete only when it contains:

1. artifact version and schema version;
2. exact command used to generate it;
3. input and output hashes or Git commit;
4. row counts and quality metrics with denominators;
5. unresolved cases and known failure examples;
6. licence/redistribution status;
7. focused tests and expected outputs;
8. downstream change notes.

Use a feature branch and Pull Request for each coherent change. Review schema
and controlled-vocabulary changes before bulk annotation, because changing an
ID or field meaning later invalidates mappings, fixtures and evaluation labels.

## 13. Delivery sequence

Schema v1 is frozen and releases are being cut (see
[Current Status](../current-status.md) for which). The remaining steps are:

### Enrich the release

- Map canonical ingredients to nutrition sources with recorded evidence, then
  convert quantities to mass and aggregate per-recipe nutrition.
- Derive cooking time and meal affinity with a recorded basis; meal affinity is
  a preference, never a filter (ADR-0024 section 5).
- Audit a sample of each enrichment and publish the audit with its
  denominators.

### Import into the runtime

- ~~Add an adapter or migration from the release into the runtime catalog.~~ Done; release v2.1 is imported (see section 2).
- ~~Let candidate retrieval reach the whole catalog, not the first 500 recipes by id.~~ Done: recommendations rank every recipe whose course can fill a meal (curated, or v2 `main`/`soup`) and keep the best 500 within budget; weekly plans and replacements load only recipes the planner can price (`RecipeRepository.list_for_planning`).
- ~~Map release ingredients to products.~~ Done for release v2 (see section 2); the owner's sampled review is recorded in `data-engineering/docs/fairprice-v2-sampled-review.json`.
- Add planner and grocery fixtures and regression tests.
- Publish the quality report, release manifest and known gaps with the import.

### Freeze evaluation-ready data

- Freeze the catalog and FairPrice snapshot used by all relevant baselines.
- Record missingness and coverage by scenario difficulty.
- Keep development examples and review feedback out of the held-out set.

## 14. Definition of done

The data-engineering module is complete for a release when:

1. permitted inputs can be reproduced from manifests without committing
   restricted raw data;
2. the pipeline rebuilds staging, candidates and curated outputs
   deterministically;
3. canonical ingredient and recipe schemas, IDs, vocabularies and missing
   semantics are versioned;
4. every resolution is auditable from its recorded evidence, a sampling audit
   is published, and allergen labels are rule-derived or explicitly unresolved;
5. all release gates pass and the quality report states denominators;
6. the current runtime imports the release idempotently;
7. planner, FairPrice, frontend and Evaluation consumers have frozen fixtures
   and documented degraded behaviour;
8. the release manifest records source versions, code revision, hashes,
   metrics and known gaps;
9. no credential, restricted raw file or unsupported medical claim is present;
10. another contributor can reproduce the release using only the documented
    commands, permitted source access and review artifacts.

## 15. Decisions still requiring evidence

- Which household-unit, density and piece-weight conversions are reliable
  enough for FairPrice package arithmetic.
- Which taste, method, equipment and difficulty vocabularies achieve enough
  coverage to justify product use.

Settled since this handoff was written: the committed releases are published
under the owner's confirmed non-commercial educational licence (the upstream
dump stays local); the pipeline lives in `data-engineering/` in this
repository; and the release gate is frozen with schema v1. RecipeNLG carries no
source-reported nutrition, so its releases compute nutrition from ingredient
mappings recorded under ADR-0024. Whether a future source's own values would
also be kept remains open.
