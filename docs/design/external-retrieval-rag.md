# External Retrieval and RAG Handoff

## Purpose and final goal

This module retrieves current external evidence only when a confirmed product
workflow needs it. It connects MealCraft's canonical recipe and ingredient
facts to current FairPrice observations and to one relevant YouTube cooking
tutorial without allowing either source to overwrite internal recipe truth.

The final goal is a traceable Retrieval-Augmented Generation pipeline in which:

1. retrieval is triggered by a specific planning, Shopping List, or recipe-
   execution need;
2. every result becomes a typed evidence packet with source, query, mode,
   timestamp and parser version;
3. deterministic code validates packages, prices, mappings and video
   eligibility;
4. the Agent may explain or orchestrate evidence, but never invents missing
   product, cost, nutrition or safety facts;
5. the UI exposes source and degraded states;
6. evaluation can replay frozen evidence independently of live source changes.

## Status boundary

### Verified baseline

MealCraft already supports FairPrice fixture/live modes, normalized product
responses, a 15-minute PostgreSQL cache, explicit fixture fallback, package
rounding, purchase cost, ingredient-use cost and surplus quantity.

### Foundation added by this work package

- shared `RetrievalTrace` and `RetrievalEvidencePacket` schemas;
- FairPrice responses linked to mode, status, query, parser version, candidate
  count and fetch time;
- a recipe tutorial endpoint with deterministic query construction and Top-1
  selection over fixture candidates;
- explicit fixture fallback for an unavailable live YouTube provider;
- an offline fixture proving that only one selected tutorial is returned.

The live YouTube request, advanced relevance features, persistent video cache,
frontend player, broad FairPrice package handling and production RAG
orchestration remain teammate-owned. A scaffold is not a complete live feature.

## One external-evidence architecture

```text
confirmed domain need
  -> provider-specific query builder
  -> on-demand external provider
  -> raw candidate observations
  -> normalization and typed validation
  -> deterministic filtering and ranking
  -> Retrieval Evidence Packet
  -> deterministic consumer or Agent explanation
  -> source-aware UI and frozen evaluation snapshot
```

| Stage | Responsibility | Must not happen |
| --- | --- | --- |
| Retrieval | issue a bounded query and preserve candidates needed for audit | crawl unrelated catalog pages or treat no result as a fact |
| Augmentation | construct compact typed evidence | pass raw pages or hidden gold/intermediate answers to the LLM |
| Generation/decision | explain evidence or select a tool path | let an LLM calculate packages, cost, constraints, nutrition or safety |

An external result is evidence, not application state. A product observation or
video candidate remains distinct from the final Shopping List line or the one
video displayed to the user.

## Shared retrieval trace

| Field | Meaning |
| --- | --- |
| `requested_source` | intended source such as `fairprice` or `youtube` |
| `provider_used` | provider that actually returned data, including fixture |
| `mode` | `live`, `cache`, or `fixture` |
| `status` | `success`, `degraded`, or `unavailable` |
| `query` | exact normalized query |
| `fetched_at` | observation time, retained when cache is reused |
| `parser_version` | parser/normalizer contract |
| `candidate_count` | count before downstream selection |
| `selected_external_id` | selected item, or null when selection is downstream |
| `warnings` | visible degradation or incomplete-evidence messages |

Future persistence should treat observations and traces as append-only evidence.
Refreshing creates a new observation instead of rewriting the result used by an
existing plan.

## FairPrice design

### Trigger boundary

```text
validated weekly plan
  -> aggregated canonical ingredient demand
  -> known pantry deduction
  -> remaining shopping demand
  -> FairPrice queries for demanded ingredients only
```

FairPrice is queried on demand for actual plan/Shopping List needs. It does not
pre-crawl a broad product catalog. Replanning reuses fresh observations and only
refreshes changed or expired demand.

### Retrieval output

A product observation preserves:

- external ID, raw title, brand and category;
- displayed package text and parsed size/unit/multipack;
- regular/effective price, promotion metadata and SGD currency;
- stock state, product URL, optional remote image URL and fetch time;
- exact query, source mode, parser version and raw-field provenance;
- validation warnings instead of guessed quantities.

Ingredient-product candidates additionally require canonical ingredient ID,
rank, lexical/category/unit evidence, review state, compatible unit, conversion
and rejection reason. Retrieval, mapping and final selection stay separately
measurable.

### Selection and arithmetic

The deterministic grocery layer owns unit compatibility, reviewed conversions,
package count, purchase/consumed cost, excess quantity, budget truthfulness and
unmapped status. The Agent may construct a query and explain the trace. It must
not infer package sizes or perform free-form cost arithmetic.

### Degradation modes

Distinguish live success, fresh cache, stale cache, timeout, schema drift,
fixture fallback, empty search, unmapped ingredient and unknown package. Fixture
results keep tests or demos running but are never labelled current FairPrice.

## YouTube tutorial design

### Product boundary

YouTube runs only after a recipe is selected or its Recipe Side Panel opens. It
is execution support, not a planning input. Video content cannot replace
MealCraft ingredients, safety labels, nutrition, quantities or written steps.

### Query contract

The initial deterministic query contains recipe title, cuisine, up to three
primary ingredients, requested language, and `cooking tutorial`. The live
adapter should normalize video ID, title, channel, thumbnail, duration,
embeddability, language hint and fetch time for a bounded candidate set.

### Hard filtering and deterministic Top-1

At minimum, non-embeddable candidates are excluded. The completed provider also
validates availability, region, content type and a documented duration policy.
The initial ranking scores recipe-title, cuisine and ingredient overlap,
tutorial intent, practical duration and language match. Tie-breaking is stable.

All candidates and score components remain available internally for review and
evaluation. The public API and Recipe Side Panel return only the highest-ranked
eligible video. If none is eligible, return an explicit unavailable state.

The UI should show title, channel, source attribution, a privacy-aware embed or
link, and a warning that an external tutorial may differ from the canonical
MealCraft recipe.

## External recipe retrieval

Web recipes use the same evidence pattern but have a higher admission gate. A
retrieved recipe cannot enter planning until it is parsed, ingredient-
normalized, safety-checked, nutrition-linked where required and released under
the recipe-data contract. Implement this after the internal catalog pipeline is
stable; do not fold it into the tutorial provider.

## Storage target

| Record | Purpose |
| --- | --- |
| `retrieval_requests` | purpose, query, source, plan/recipe link and request time |
| `external_observations` | immutable normalized results and raw-field provenance |
| `retrieval_candidates` | eligibility, rank features, score and rejection reason |
| `retrieval_selections` | selected external ID, policy version and reason |
| `retrieval_snapshots` | frozen evidence, code revision, hashes and known gaps |
| `provider_runs` | latency, cache, status, error class, parser version and counts |

Do not add these tables until fields and retention needs are reviewed. The
current `ProductSnapshot` remains the runtime baseline.

## Teammate work packages

### A. FairPrice robustness

1. Separate request, raw capture, parse and normalize stages.
2. Add response fixtures for ordinary, promotion, multipack, unavailable,
   missing-package and schema-drift cases.
3. Expand mass, volume, count and multipack parsing without unsafe conversion.
4. Persist parser version and provider-run diagnostics.
5. Build reviewed positive, negative and ambiguous product mappings.
6. Measure package parse, `Recall@k`, product selection and cost accuracy.

### B. YouTube live retrieval

1. Implement `YouTubeDataApiProvider` with server-side runtime key, bounded
   timeout and normalized error types.
2. Fetch only required metadata and track provider/quota state.
3. Complete eligibility checks and freeze a ranking-policy version.
4. Add cache/persistence and refresh behaviour.
5. Add Recipe Side Panel loading, unavailable, degraded and Top-1 states.
6. Build reviewed query-video labels and report Top-1 and candidate recall.

### C. RAG integration

1. Build typed evidence packets instead of passing provider pages.
2. Link every Agent statement about price, availability or source to evidence.
3. Keep planner/grocery calculations outside generation.
4. Persist tool trace, packet digest, model configuration and warnings.
5. Add prompt-injection fixtures proving external text is data, not instruction.

Each package ships a versioned fixture, unknown/degraded semantics, tests,
metrics with denominators, known failures and downstream instructions.

## Evaluation plan

FairPrice metrics include live/cache/fixture success, typed degradation,
package exact match, normalized quantity error, mapping precision/recall,
`Recall@k`, selected-product accuracy, Shopping List coverage, package-count
exact match, cost error, freshness, latency and disclosure accuracy.

YouTube metrics include eligible-candidate recall, Top-1 relevance on a two-
person reviewed subset, unavailable/embedding failures, language/duration-policy
compliance, latency, cache hit and provider-call count. It may be included as a
human usefulness item, but not as part of strict planning validity.

Primary FairPrice comparison uses a frozen snapshot. Separate live runs measure
retrieval robustness.

## Definition of done

1. FairPrice is queried only for current plan/shopping demand and returns a
   complete trace.
2. Package parsing, mapping and arithmetic are independently testable.
3. YouTube live retrieval yields bounded candidates, deterministic eligibility
   and one user-visible Top-1.
4. Empty, timeout, quota, schema-drift, cache and fixture states are explicit.
5. Agent output is linked to evidence and cannot override calculations.
6. Offline fixtures reproduce critical provider and degradation states.
7. Evaluation reports denominators and frozen versions.
8. A contributor can continue either provider from the interfaces, fixtures,
   commands and TODOs in this contract and the standalone `Retrieval` starter.
