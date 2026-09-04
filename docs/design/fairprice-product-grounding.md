# FairPrice Product Grounding Contract

## Purpose

This module turns an abstract recipe requirement such as `tomato, 800 g` into
traceable FairPrice product candidates and package-aware purchase facts. It is
the bridge between recipe planning and an actionable Shopping List.

## Verified baseline

The current provider supports fixture and live modes, normalized product
responses, a 15-minute PostgreSQL cache, explicit visible fallback, package
rounding, purchase cost, ingredient-use cost and surplus quantity. Product
responses include external ID, name, brand, category, package size/unit, price,
URL, image URL, stock state, source and fetch time.

The current catalog and mapping logic are intentionally small. They do not yet
establish broad FairPrice coverage, robust package parsing across categories,
or stable live-site behaviour.

## Accepted target records

### Product observation

A product observation is immutable evidence from one lookup time. It should
contain:

- provider and external product ID;
- raw title plus normalized brand and category;
- displayed package text plus parsed quantity, canonical unit and multipack
  count;
- regular price, effective observed price, promotion metadata when available,
  and currency;
- availability state;
- product/source URL, optional image URL, retrieval method and `fetched_at`;
- parser version, validation status and raw-field provenance;
- source mode: `live`, `cache`, or `fixture`, without silent substitution.

Unknown package quantity must remain unknown. It must not default to one gram,
one item, or any guessed pack size.

### Ingredient-product mapping

The mapping should preserve:

- canonical ingredient ID and product observation ID;
- candidate rank, lexical/semantic evidence and mapping method;
- match confidence and review status;
- compatible purchase unit and any explicit conversion;
- rejection reason for near-name mismatches, wrong categories or unsuitable
  variants;
- alternative products, rather than only the product ultimately selected.

Product choice is downstream of retrieval. Keeping candidates separate from the
selected product allows mapping quality, price selection and planner behaviour
to be evaluated independently.

## Retrieval and normalization flow

```text
canonical ingredient or query
  -> FairPrice search/retrieval
  -> raw observation capture
  -> package, price and availability parsing
  -> ingredient-product candidate mapping
  -> deterministic validation and ranking
  -> cache or frozen evaluation snapshot
  -> package-aware grocery estimator
```

Live failures should return a typed failure or visibly marked fallback. A stale
cache may be useful, but it must retain its original timestamp.

## Primary and robustness evidence

The primary comparative planning experiment uses one frozen, timestamped
FairPrice snapshot so all systems receive identical facts. Live lookup is tested
separately as a robustness and operations question across:

- live success;
- cache hit;
- stale cache;
- live timeout or schema drift;
- fixture fallback;
- unavailable or unmapped ingredient.

Mixing changing live prices into the primary baseline comparison would confound
system quality with retrieval time.

## Fair input for the context-matched LLM-only baseline

Provide the same product evidence available to MealCraft: product ID, raw name,
brand, category, package quantity/unit, price/promotion, availability, source and
timestamp. In the controlled planning condition, the reviewed canonical
ingredient mapping may be shared because normalization is not the mechanism
being tested.

Provide all relevant candidates plus deliberate decoys, unavailable results and
near-name mismatches. Do not provide MealCraft's chosen product, package count,
total cost, feasibility decision or gold mapping. Those are answers, not input
facts.

## Quality metrics

- query success and typed-degradation rate by source mode;
- package parse exact-match rate;
- normalized quantity error after unit conversion;
- ingredient-product precision, recall and `Recall@k` on reviewed candidates;
- selected-product accuracy under a predeclared selection rule;
- Shopping List line coverage;
- package-count exact match;
- purchase-cost absolute error and ingredient-use-cost error;
- source freshness and cache/fallback disclosure accuracy;
- latency by live, cache and fixture mode.

## Minimum hand-off

The planning and evaluation modules need a versioned snapshot containing all
candidate products required by the frozen recipe pool, not only successful
final selections. Every benchmark ingredient must be marked mapped, deliberately
unmapped, or unavailable. Unit incompatibility and missing packages must have
typed reasons.

## Definition of done

1. Package schema and unit policy are versioned.
2. A reviewed mapping set includes positive, negative and ambiguous examples.
3. Fixture and frozen-snapshot adapters implement the same public contract as
   live retrieval.
4. Mapping, package and cost metrics are reported separately.
5. Live degradation is visible in API, UI and logs.
6. No evaluation run silently mixes observation times or source modes.
