# MealCraft Current Status

> Last verified public snapshot: 2026-09-10
>
> Remote repository: `akane321/MealCraft`
>
> Verified remote `main`: `f979052` - `feat: add durable bounded agent runs (#37)`

## How to Read This Document

- **Verified** means the capability was merged to remote `main` and supported by
  recorded code or test evidence.
- **Partial** means a working slice exists but does not yet meet the final design
  depth.
- **Target** means the accepted product direction; it is not current behaviour.
- Current code and tests take precedence if this snapshot becomes stale.

## Verified Product Baseline

| Area | Verified behaviour | Important boundary |
| --- | --- | --- |
| Full-stack environment | FastAPI, PostgreSQL, Nuxt, Docker Compose, migrations, catalog import, and CI | Local development baseline, not production deployment evidence |
| Household profile | One shared profile, member servings and safety constraints, shared defaults, immutable versions, profile-linked plans | Does not generate separate dishes for each member |
| Identity and sessions | Argon2id credentials with upgrade-on-login, atomic account and default-household registration, login lockout, digest-only opaque sessions, per-session CSRF, current-actor lookup, session listing, logout and per-device revocation | **Authentication is not enforced on any business route.** Profile, Plan, Dashboard, Agent, Replanning and Shopping remain anonymous and single-tenant; no private domain table carries an owner column, and the frontend has no login page |
| Recipe catalog | 30 validated recipes and 34 normalized ingredients imported idempotently | Smaller and less dimensional than the final benchmark target |
| Agent | Persistent sessions, bilingual scope isolation, structured constraints, typed clarification, confirmation, bounded tool authorization, grounded claims, Agent-driven replanning, and synchronous per-action `AgentRun` with input digests, explicit deadlines and budgets, durable checkpoints, ordered tool receipts, idempotent replay and run list/detail/cancel APIs | Default parser is deterministic fixture mode. Runs are synchronous: asynchronous pause/resume/retry, external-tool evidence, natural-language claim extraction and formal live-model evidence are deferred. `AgentRun.household_id` is nullable and is not yet bound to an authenticated actor |
| Weekly planning | Seven persisted main meals plus independently callable Planning v2 constraint compilation, bounded Beam Search, conservative nutrition bounds, independent shopping/budget recomputation, and a small exhaustive oracle | The product API still uses the current baseline path; Beam parameters are untuned and the oracle proves results only for small packets under the fixed shopping policy |
| FairPrice | Live lookup, normalized results, 15-minute PostgreSQL cache, explicit fixture mode | Live-site robustness requires further observation |
| Shopping List | Aggregated demand, known-quantity deduction, package rounding, price and budget results | Unknown pantry quantities are never deducted |
| Check-in and Dashboard | Planned/completed/skipped states, completed cumulative nutrition KPIs and curves, current-plan comparison, labelled daily detail, completion coverage | Cumulative actuals count completed MealCraft dishes only; planned rows are previews and skipped rows are not counted |
| Replanning | Preview, confirm/discard, plan revision, event history, local meal changes, price and Shopping List deltas | Broader preference and stress-event semantics remain partial |
| Evaluation | Developer, held-out, Agent, scope and grounding fixtures; greedy and Strong Rule-only references; matched-information v2 developer packets; failure registry; state and 1280×720 desktop browser tests | Visible orchestration/v2 packets validate contracts but are not independent held-out comparative evidence |

## Recorded Evaluation Snapshot

### Datasets

- 20 developer planning scenarios;
- 40 held-out planning scenarios: 36 feasible and 4 infeasible;
- 24 offline Agent fixtures;
- 36 bilingual scope developer cases and 12 typed grounding developer cases;
- two fully covered, leakage-resistant matched-information Evaluation v2 developer packets;
- 30 recipes and 34 normalized ingredients in the recorded catalog.

### Held-out planner comparison

The greedy baseline and MealCraft used the same eligible recipe pool.

| Metric | Greedy baseline | MealCraft |
| --- | ---: | ---: |
| Adjacent repetitions | 216 | 0 |
| Mean distinct recipes | 1.0 | 6.1389 |
| Feasible-case failures | 36 | 0 |

MealCraft recorded zero hard-constraint violations in this run.

The Strong Rule-only reference uses the same upstream hard filtering and fixed
ordering by consumed ingredient cost, cooking time, recommendation score and
recipe ID. On the same v1 held-out set it recorded zero adjacent repetitions,
`2.0` mean distinct recipes, zero feasible-case failures and zero hard-constraint
violations.

**Read this comparison carefully.** Against the strong reference, MealCraft ties
on scenario expectation rate (`1.0` each), hard-constraint violations (`0` each)
and recorded failure cases (`0` each). The only separation is mean distinct
recipes, `6.1389` against `2.0`. A primary metric that saturates for both systems
measures the difficulty of the evaluation set, not the strength of the planner,
and it cannot by itself isolate Agent causality or support a superiority claim.
Raising the discriminating power of the held-out set is the purpose of
[Comparative Evaluation v2](design/comparative-evaluation-v2.md).

### Offline Agent fixture result

- Exact-case rate: `16/24 = 0.6667`;
- Field precision: `1.0`;
- Field recall: `0.8298`;
- Field F1: `0.907`;
- Clarification accuracy: `0.875`;
- Medical-boundary accuracy: `1.0`;
- Hallucinated fields: `0`;
- Visible Agent failures: `8`.

The 44-record failure registry contains 36 greedy-baseline failures and eight
Agent failures. It is not a count of 44 MealCraft product defects.

## Gap to the Final Product Baseline

The initial proposal remains the minimum final-product ambition. Technologies
may be substituted, but the product responsibility should be preserved or
improved.

| Design capability | Status | Remaining work |
| --- | --- | --- |
| Unified planning workspace | Partial | Connect Profile, Assistant, Plan, Recipe, Shopping, Dashboard, and Replan into a more coherent workflow |
| Authentication and user separation | Partial | Credentials, revocable sessions, CSRF and device revocation are merged and tested. Remaining: enforce authentication on every business route, add and backfill household ownership on private domain tables, add Alice/Bob isolation tests, and build the login/registration frontend |
| High-dimensional recipe knowledge | Partial | Expand the catalog and complete cuisine, taste, method, equipment, difficulty, nutrition provenance, instruction, source, and media fields |
| Verified recipe benchmark | Partial | Grow from 30 recipes toward the proposal's 150-250 design target with quality checks and source coverage |
| Validated web-recipe supplementation | Target | Implement search, parsing, normalization, provenance, validation, and trusted fallback |
| Semantic preference retrieval | Target | Combine semantic matching with strict metadata filtering and evaluate its incremental value |
| Recipe execution side panel | Partial | Unify attributes, ingredients, instructions, provenance, and optional post-selection tutorial support |
| Final-scope planning and validation | Partial | Constraint compilation, bounded Beam Search, conservative bounds, independent shopping/budget validation and a small exhaustive oracle are executable; integrate them into the production API, add bounded retrieve-repair and mixed-package optimization, tune parameters, and run controlled ablations |
| Nutrition elastic policy | Partial | Complete source-aware target deviation, lower-sodium/lower-sugar policy, tolerance, missing-data behaviour, and dedicated evaluation |
| Grocery grounding robustness | Partial | Measure live/cache/fixture degradation, mapping quality, package parsing, and source freshness |
| Dynamic replanning | Partial | Add broader event semantics, temporary versus persistent preference handling, disruption metrics, and Shopping List consistency stress tests |
| Agent scope, interaction and grounding | Partial | Bilingual scope/mixed-intent isolation, typed UI interaction, stale-answer guard, deny-by-default authorization, structured claim verification and synchronous durable `AgentRun` checkpoints are executable; production classifier evidence, asynchronous pause/resume/retry, the full typed tool graph, external-tool evidence and natural-language claim extraction remain target work |
| Evaluation scale | Partial | Expand toward 150-200 verified requests, 150-250 recipes, 80-120 planning scenarios, and complete grocery coverage for benchmark demand; preserve frozen splits and digests |
| Multiple baselines | Partial | Strong Rule-only is executable; run frozen Context-matched LLM-only, Plain LLM and Human Manual comparisons only after common outputs and held-out labels are ready |
| Capability-centred Evaluation v2 | Partial | Packet compiler, coverage/leakage gates and visible developer packets are executable; common output validator, independent held-out set, repeated model runs, human study and paired statistics remain open |
| User-facing quality | Partial | Typed quick clarification and cumulative-plus-daily Dashboard passed 1280×720 Browser and Playwright acceptance; deepen loading, empty, error, degraded and accessibility coverage |
| Operations and maintainability | Target beyond the original proposal | Add health, data-quality, mapping, trace, and evaluation diagnostics where they reduce maintenance and demo risk |

## Current Priorities

1. Turn the separate working slices into a stable, understandable end-to-end
   product journey.
2. Expand and deepen the recipe and nutrition data model with provenance and
   deterministic validation.
3. Complete nutrition-target and elastic-preference semantics and evidence.
4. Test FairPrice live/cache/fixture degradation against real changes.
5. Integrate the verified Planning v2 components into the product path, then
   evaluate Beam parameters, retrieve-repair and package optimization without
   overstating global optimality or infeasibility.
6. Extend the merged synchronous `AgentRun` into asynchronous pause/resume/retry
   with bounded external-tool adapters, then build an independent held-out
   orchestration set and the common v2 output validator before any explicitly
   authorized, budget-capped live-model comparison.
7. Expand dynamic-replanning stress cases and measure unnecessary disruption.
8. Increase browser coverage and prepare a repeatable demonstration path.
9. Enforce the merged authentication on business routes and complete the staged
   household-ownership migration with cross-household denial tests, so that
   "accounts exist" cannot be mistaken for "data is isolated".
10. Raise the discriminating power of the held-out evaluation before tuning
    planner parameters. On the current v1 set the strong Rule-only reference
    matches MealCraft on task success, hard-constraint violations and failure
    count; a saturated primary metric cannot support a superiority claim.
11. Progressively close the final-design gaps documented above rather than
    treating the current MVP as the finished product.

## Verification Boundary

This file records the last merged and verified snapshot. Before updating it:

1. inspect remote `main` and current tests;
2. distinguish implementation from roadmap;
3. update the date and commit;
4. link the relevant evidence;
5. do not describe an unmerged branch as a product capability.
