# Recipe and Ingredient Data Contract

## Purpose

This module turns heterogeneous recipe text into facts that planning, grocery
grounding, explanation and evaluation can share. Its goal is not to maximize
the number of fields. Its goal is to provide trustworthy, typed facts that have
an identified consumer.

For the operational pipeline, source policy, release artifacts, two-person
workflow and acceptance gates, use the
[Data Engineering Handoff](../data/README.md). This document remains the short
canonical contract between modules.

## Verified baseline

The current catalog contains 30 recipes and 34 normalized ingredients. A recipe
already exposes identity, title, description, cuisine, meal type, servings,
preparation and cooking time, dietary tags, per-serving calories/macronutrients/
sodium/sugar, normalized ingredient quantities, preparation notes, allergen
labels, and ordered steps.

Current limitations include small scale, limited provenance, a narrow unit
vocabulary, limited preference attributes, and no general conversion model for
incompatible household, recipe and product units.

## Accepted target

### Canonical ingredient

Each ingredient record should be able to support:

| Field group | Required meaning | Downstream use |
| --- | --- | --- |
| identity | stable ID, canonical name, display name, language and aliases | parsing, joins, user display |
| safety | allergen categories and reviewed diet compatibility | hard filtering |
| classification | food group and optional parent/variant relation | retrieval, substitution, analysis |
| quantity semantics | canonical mass/volume/count unit, density or piece-weight conversion only when sourced | grocery and pantry arithmetic |
| nutrition link | reference-food ID, basis and source where available | recipe nutrition provenance |
| provenance | source, extraction method, reviewer and version | audit and benchmark freezing |
| quality | completeness, confidence and unresolved flags | missing-data policy |

Aliases and preparation descriptions must not create new ingredients. For
example, `two chopped tomatoes` should retain `tomato` as the canonical
ingredient, `2` and `piece` as quantity semantics, and `chopped` as preparation.

### Canonical recipe

A target recipe record should include:

- stable recipe ID, title, language, source URL or internal source, licence or
  use status, capture time and schema version;
- servings, preparation/cooking/total time and meal type;
- cuisine plus controlled taste, cooking method, equipment and difficulty
  attributes only after their vocabularies are defined;
- dietary tags derived under documented rules, not copied blindly from a page;
- ingredient rows with canonical ID, original text, quantity, unit,
  preparation, optional flag and normalization status;
- per-serving nutrition values with basis, source, calculation method,
  completeness and uncertainty/missing flags;
- ordered cooking instructions and optional media provenance.

## Transformation pipeline

```text
raw source
  -> parsed recipe fields and original ingredient text
  -> alias resolution and preparation separation
  -> unit normalization and safe conversions
  -> safety/diet tag validation
  -> nutrition attachment or calculation with provenance
  -> schema and cross-field validation
  -> versioned catalog release
```

Raw records must remain distinguishable from normalized facts. Automatic
normalization should produce an unresolved state instead of silently guessing a
canonical ingredient or conversion.

The raw, staging, candidate, review, curated and immutable release layers must
remain distinguishable. Restricted raw datasets stay outside the public
repository and are referenced by a source manifest and checksum. A candidate
match score is a review-prioritization signal, not evidence that the match is
correct.

## Minimum hand-off contracts

The planner can consume a recipe only when identity, servings, time, dietary
tags, ingredient IDs, allergen facts and nutrition completeness are explicit.
The grocery module additionally requires quantities and units that are either
directly compatible with a product package or linked by a reviewed conversion.

The Evaluation v2 harness requires a frozen catalog version and must know which
fields were genuinely available to each compared system. Missing nutrition or
preference labels are not negative evidence and must not be scored as if they
were known.

## Quality metrics

- schema-valid recipe rate;
- canonical-ingredient resolution coverage;
- quantity-and-unit coverage;
- unit-conversion coverage and reviewed conversion error rate;
- allergen and dietary-label precision/recall on an independently reviewed
  subset;
- nutrition-field completeness by field and source;
- provenance coverage;
- duplicate recipe and duplicate ingredient rate;
- inter-reviewer agreement for subjective attributes.

Every metric must state its denominator. Coverage over easy imported rows alone
must not be presented as whole-catalog coverage.

## Definition of done for a catalog release

1. Schema, controlled vocabularies and missing-value semantics are versioned.
2. Validation produces a machine-readable quality report.
3. At least one planner fixture and one grocery-mapping fixture consume the new
   or changed fields.
4. Safety-critical labels receive independent review.
5. Sources and transformations are traceable.
6. Evaluation claims are enabled only for fields whose coverage meets a
   predeclared threshold.
7. The release manifest records source versions, code revision, schema version,
   output hashes, metric denominators and known gaps.

## Open design questions

- Which source licences permit redistribution of full recipe text?
- Which unit conversions are reliable enough for package arithmetic?
- Which taste, method, equipment and difficulty vocabularies have enough
  coverage to justify product and evaluation use?
- Should nutrition be source-reported, ingredient-calculated, or both with a
  disagreement field?
