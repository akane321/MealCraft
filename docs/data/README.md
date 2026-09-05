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
| Prototype evidence | A separate data-cleaning pilot has run successfully, but its pipeline and outputs are not yet integrated into MealCraft |
| Accepted target | The intended module responsibility and release contract |
| Working target | A planning number or threshold that must be reviewed after real-data profiling |

The verified runtime baseline is 30 recipes and 34 normalized ingredients in
`data/recipes/recipes.json` and `data/ingredients/ingredients.json`. The current
schema is deliberately compact and is loaded by `backend/app/data/catalog.py`.

A separate prototype verified the proposed pipeline mechanics on 20 synthetic
RecipeNLG-shaped recipes. It produced 96 ingredient occurrences and 50
canonical/candidate ingredient records, with:

- `83.33%` internal ingredient resolution coverage (`80/96` occurrences);
- `85.42%` quantity coverage (`82/96` occurrences);
- `62.50%` recognized-unit coverage (`60/96` occurrences);
- zero duplicate recipe and ingredient IDs;
- all three prototype quality gates passing;
- 11 automated tests passing;
- 31,341 FoodOn terms loaded and 244 mapping candidates generated;
- 395 USDA Foundation Food entries loaded, with 116 candidates generated for
  37 internally resolved ingredient queries.

These numbers demonstrate that the pipeline, manifests, review queues and
reference matching can run. They do **not** establish production accuracy,
catalog coverage, safety-label quality, or readiness for Evaluation v2.

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

The proposal-scale working target is 150-250 independently checked recipes,
plus enough canonical ingredients to cover every released recipe and every
benchmark grocery demand. This is a working range, not permission to lower the
quality gates. A smaller high-quality release is preferable to a larger catalog
whose quantities, safety labels or provenance cannot support planning claims.

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
  -> human review decisions
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
| Nutrition link | reference source, FDC ID, basis, matched description | External match remains a candidate until reviewed |
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

## 9. Normalization and review policy

Automatic processing should narrow the human workload, not make final claims
on insufficient evidence.

1. Preserve the raw value before parsing.
2. Parse quantity, unit, ingredient phrase and preparation separately.
3. Resolve exact reviewed aliases first.
4. Generate ranked candidates for unresolved values.
5. Validate dimensions and cross-field consistency.
6. Route uncertain, safety-critical, composite, or conflicting rows to review.
7. Store the accepted/rejected decision and reason.
8. Rebuild curated outputs deterministically from raw inputs, configuration and
   review decisions.

The following are prohibited:

- automatically accepting the first FoodOn or USDA search result;
- treating `0` as missing nutrition or quantity;
- converting count, volume and mass without a sourced conversion;
- deriving disease-specific medical advice from recipe data;
- asking an LLM to invent a serving size, nutrient value or allergen fact;
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

## 13. Recommended delivery sequence

### D0 - Reproduce the pilot

- Run the synthetic pipeline and tests from a clean environment.
- Confirm manifests, review queues, quality report and deterministic outputs.
- Treat the observed coverage as diagnostics, not acceptance targets.

### D1 - Profile a real sample

- After personally accepting the RecipeNLG terms, store the raw dataset
  outside Git and record its checksum.
- Run a fixed-seed, source-filtered 5,000-row sample.
- Review a stratified set of at least 200 ingredient/recipe issues.
- Measure the long tail of aliases, units, composites, duplicates and missing
  serving information before freezing new thresholds.

### D2 - Produce the first integrated catalog release

- Freeze schema v1, controlled units and canonical ingredient IDs.
- Curate the first 150-250-recipe working range subject to quality gates.
- Add an adapter/migration into the existing MealCraft runtime.
- Add planner and grocery fixtures and regression tests.
- Publish the quality report, release manifest and known gaps.

### D3 - Freeze evaluation-ready data

- Create independent gold subsets for safety labels, normalization and
  ingredient-product mappings.
- Freeze the catalog and FairPrice snapshot used by all relevant baselines.
- Record missingness and coverage by scenario difficulty.
- Prevent train/development examples or review feedback from leaking into the
  held-out set.

## 14. Definition of done

The data-engineering module is complete for a release when:

1. permitted inputs can be reproduced from manifests without committing
   restricted raw data;
2. the pipeline rebuilds staging, candidates and curated outputs
   deterministically;
3. canonical ingredient and recipe schemas, IDs, vocabularies and missing
   semantics are versioned;
4. review decisions are auditable and safety-critical facts are independently
   checked or explicitly unresolved;
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

- Whether full recipe text from each source may be redistributed publicly.
- Which household-unit, density and piece-weight conversions are reliable
  enough for FairPrice package arithmetic.
- Whether nutrition should be source-reported, ingredient-calculated, or both
  with a disagreement field.
- Which taste, method, equipment and difficulty vocabularies achieve enough
  coverage and reviewer agreement to justify product use.
- The exact release thresholds after the real 5,000-row profile.
- Whether the pilot pipeline should be integrated directly, adapted into an
  import package, or retained as a separate data-build repository.
