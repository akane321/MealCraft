# MealCraft Current Status

> Last verified public snapshot: 2026-09-19
>
> Remote repository: `akane321/MealCraft`
>
> Verified remote `main`: `d6f2b66`

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
| Full-stack environment | FastAPI, PostgreSQL, Nuxt, Docker Compose, migrations, catalog import, and CI (which also lints and tests `data-engineering`) | Local development baseline, not production deployment evidence |
| Household profile | One shared profile, member servings and safety constraints, shared defaults, immutable versions, profile-linked plans. Each ingredient carries an allergen list; an allergen outside the checked vocabulary (`data/ingredients/allergen-vocabulary.json`) excludes every recipe rather than none, and the profile offers only allergens the catalog can check | Does not generate separate dishes for each member. Allergen labels are rule-derived from ingredient data, not verified against products |
| Identity, sessions and tenancy | Argon2id credentials with upgrade-on-login, atomic account and default-household registration, login lockout, digest-only opaque sessions, per-session CSRF, current-actor lookup, session listing, logout and per-device revocation. Private Profile, Plan, Dashboard, Agent, Replanning and Shopping workflows require an active authenticated household; private ownership is non-null, repository queries are household-scoped, cross-household identifiers resolve as not found, and the browser has registration and login flows. Private routes authorize each action through one `HouseholdAction` dependency (`VIEW`, `EDIT_PROFILE`, `CREATE_PLAN`, `CHECK_IN`) in the order authentication, active household, action, CSRF; unknown roles are denied | No member-management or household-deletion routes exist yet, so `MANAGE_MEMBERS` and `DELETE_HOUSEHOLD` are defined but unused. Household collaboration, password lifecycle and account export/deletion remain incomplete |
| Recipe catalog | 30 validated recipes and 34 normalized ingredients imported idempotently | Smaller and less dimensional than the final benchmark target |
| Data engineering | Independent `data-engineering/` pipeline with frozen schema v1, a four-condition release gate, and release v1.1 containing 9,282 recipes and 465 canonical ingredients. Deterministic derived dietary tags cover vegetarian (5,625), gluten-free (4,507), dairy-free (3,602) and vegan (1,030) recipes. A first nutrition-mapping pass matches the curated ingredient set (533 entries) against USDA Foundation Foods, SR Legacy and FNDDS with recorded evidence: 213 `mapped`, 209 `needs_review`, 111 unresolved ([progress report](../data-engineering/docs/task-b-nutrition-mapping-progress.md)) | **Not imported into the runtime catalog.** Nutrition remains `not_computed`: the mapping is not yet turned into per-recipe values (no quantity-to-mass conversion or aggregation). Cuisine, meal types, methods, equipment and difficulty remain empty. Derived dietary tags are not reviewed gold labels, and allergen labels remain deterministic-rule-only |
| Home surface | `/` is the product surface: a full-bleed film entry whose command bar becomes a chat on the Agent session API (clarification answers, confirmation, replan preview and confirm/discard). Edge panels open on hover, keyboard focus or pin and move the chat aside: the week with tonight's Top-1 tutorial and cooked check-in on the left; cooked nutrition, per-dinner calories and the shopping list against budget on the right. The shopping list previews as a sheet and exports through the browser's print-to-PDF. Liquid-glass styling uses an edge-lens backdrop filter in Chromium and frosted glass elsewhere. A nutrition sheet (six nutrients, cumulative curve, daily table with cooked/skip/undo) and a recipe sheet (ingredients with allergen labels, steps) open over the surface. The only other pages are `/login`, `/profile` (behind the avatar) and `/system` (service status); login returns to a same-site `?next=` path | Browser-tested at 1280×720 against a stubbed API; a signed-in run against the real backend is not yet recorded. Tutorials come from a four-video sample set (live YouTube search is a scaffold), so only dishes whose name matches a sample video show one, labelled as a sample; the rest say no video is available yet. Price labels read the products actually used, so a live request that fell back to sample data says so. Replan events are recorded by the backend but no longer shown in the interface |
| Agent | Persistent household-scoped sessions, bilingual scope isolation, structured constraints, typed clarification, confirmation, bounded tool authorization, grounded claims, Agent-driven replanning, and synchronous per-action `AgentRun` with authenticated actor/household provenance, input digests, explicit deadlines and budgets, durable checkpoints, ordered tool receipts, idempotent replay and run list/detail/cancel APIs | Default parser is deterministic fixture mode. Plan confirmation is not yet bound to a specific preview: `POST /api/agent/sessions/{id}/confirm` takes no preview id, context version or expiry, generates and saves the plan in one call, and records the generation step as a preview although it already persists the plan; ADR-0016's matched, unexpired confirmation is target work. Runs are synchronous: asynchronous pause/resume/retry, external-tool evidence, natural-language claim extraction and formal live-model evidence are deferred |
| Weekly planning | Seven persisted main meals plus independently callable Planning v2 constraint compilation, bounded Beam Search, conservative nutrition bounds, independent shopping/budget recomputation, and a small exhaustive oracle. Weekly budgets are compared in whole cents on both sides (ADR-0021). In Planning v2 a recipe's meal type is a soft affinity, not a filter (ADR-0024 section 5); the CP-SAT package oracle's tests run in CI | The product API still uses the current baseline path; Beam parameters are untuned and the oracle proves results only for small packets under the fixed shopping policy |
| FairPrice | Live lookup verified against the live site, normalized results, 15-minute PostgreSQL cache, and a live → saved-snapshot → fixture degradation chain with a warning and a `degraded` trace. An empty live result is a typed `no_match`: the ingredient stays unpriced instead of borrowing sample prices. A test generates a live-priced weekly plan with every FairPrice request failing and still gets a Shopping List | The disconnected run is covered by an automated test with the network stubbed out, not yet by a demonstration on a physically disconnected machine |
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

### Held-out v2 authoring progress

Fifty of the planned 80 episodes are authored: 12 `standard`, 12
`clarification`, 10 `budget_package`, 8 `pantry_expiry` and 8
`infeasible_conflict`. Twenty-two have completed eligible human review: 10
reviewed by `backend`, 9 by `dataset` and 3 by `frontend-evaluation`.
Twenty-eight await review: 8 `standard`, 9 `clarification`, 5 `budget_package`,
4 `infeasible_conflict` and 2 `pantry_expiry`. The set is not frozen and must not
yet be treated as final held-out evidence. Authoring is governed by a
cross-authoring rule: no contributor writes or reviews an episode for a category
that evaluates a system they own.

Two limits are recorded here because they bound every claim the set can support.
A paired comparison at the sizes this team can author detects a true difference
of roughly fifteen percentage points or more; smaller differences would need
several hundred episodes. Per-category success rates are not reportable at eight
to twelve episodes a category, so categories serve coverage and error analysis
rather than per-category comparison.

Nutrition targets in gold labels are scored against frozen per-serving catalog
values. Each target must state whether it binds every planned dish or only the
average over the planned slots; there is no default, and the authoring checker
refuses a target that does not say. A daily-total scope is not yet supported,
which does not affect episodes that plan one meal a day.

Episodes may be drafted by an AI agent working from a sealed packet containing
the catalogs, authoring rules and checker but no implementation of any system
under test. Each draft is read and accepted by an eligible human contributor,
whose role is what `authored_by` records.

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

The conditions these numbers were computed over are recorded in
[`conditions-v1.json`](evaluation/workbench/conditions-v1.json): the path and
SHA-256 of all eight inputs, attested by checking that none of them was
committed after the report was generated. This comparison is therefore
attributable to a 30-recipe catalog and a 34-product fixture, and it stays
attributable once those grow. Growing them supersedes these numbers rather than
preserving them; a report generated afterwards carries its own input digests and
is a different report even where a value coincides.

**Read this comparison carefully.** Against the strong reference, MealCraft ties
on scenario expectation rate (`1.0` each), hard-constraint violations (`0` each)
and recorded failure cases (`0` each). The only separation is mean distinct
recipes, `6.1389` against `2.0`. A primary metric that saturates for both systems
measures the difficulty of the evaluation set, not the strength of the planner,
and it cannot by itself isolate Agent causality or support a superiority claim.
Raising the discriminating power of the held-out set is the purpose of
[Comparative Evaluation v2](design/comparative-evaluation-v2.md).

### Offline Agent fixture result

From the [latest workbench report](evaluation/workbench/latest.md):

- Exact-case rate: `18/24 = 0.75`;
- Field precision: `1.0`;
- Field recall: `0.8723`;
- Field F1: `0.9318`;
- Clarification accuracy: `0.875`;
- Medical-boundary accuracy: `1.0`;
- Hallucinated fields: `0`;
- Visible Agent failures: `6`.

Two of the eight earlier failures (stated shellfish and egg allergies) were
fixed as a safety correction after they had been seen, so these numbers are
diagnostic rather than independent evidence. The 42-record failure registry
contains 36 greedy-baseline failures and six Agent failures; it is not a count
of 42 MealCraft product defects.

## Gap to the Final Product Baseline

The initial proposal remains the minimum final-product ambition. Technologies
may be substituted, but the product responsibility should be preserved or
improved.

| Design capability | Status | Remaining work |
| --- | --- | --- |
| Unified planning workspace | Partial | The home surface joins conversation, week, tutorial, recipe detail, nutrition detail and shopping-list export; the earlier separate pages are removed. Remaining: show replan history again, and record a signed-in walkthrough against the real backend |
| Authentication and user separation | Partial | Authentication, non-null household ownership, household-scoped repositories, cross-household denial, per-action household authorization and browser registration/login are merged. Remaining: member-management routes, a wider isolation matrix, household collaboration, password lifecycle and account export/deletion |
| High-dimensional recipe knowledge | Partial | Expand the catalog and complete cuisine, taste, method, equipment, difficulty, nutrition provenance, instruction, source, and media fields |
| Verified recipe benchmark | Partial | Import a gated, enriched data release into the runtime catalog; the recipe count is set by what passes the release gate, not by a fixed range (decision ADR-0024) |
| Validated web-recipe supplementation | Target | Implement search, parsing, normalization, provenance, validation, and trusted fallback |
| Semantic preference retrieval | Target | Combine semantic matching with strict metadata filtering and evaluate its incremental value |
| Recipe execution side panel | Partial | The recipe sheet shows ingredients, allergen labels and steps, and the left panel carries tonight's tutorial. Remaining: attributes, provenance and a tutorial per dish beyond the sample set |
| Final-scope planning and validation | Partial | Constraint compilation, bounded Beam Search, conservative bounds, independent shopping/budget validation and a small exhaustive oracle are executable; integrate them into the production API, add bounded retrieve-repair and mixed-package optimization, tune parameters, and run controlled ablations |
| Nutrition elastic policy | Partial | Complete source-aware target deviation, lower-sodium/lower-sugar policy, tolerance, missing-data behaviour, and dedicated evaluation |
| Grocery grounding robustness | Partial | Measure live/cache/fixture degradation, mapping quality, package parsing, and source freshness |
| Dynamic replanning | Partial | Add broader event semantics, temporary versus persistent preference handling, disruption metrics, and Shopping List consistency stress tests |
| Agent scope, interaction and grounding | Partial | Bilingual scope/mixed-intent isolation, typed UI interaction, stale-answer guard, deny-by-default authorization, structured claim verification and synchronous durable `AgentRun` checkpoints are executable; production classifier evidence, asynchronous pause/resume/retry, the full typed tool graph, external-tool evidence and natural-language claim extraction remain target work |
| Evaluation scale | Partial | Expand toward 150-200 verified requests, a gated imported recipe release, 80-120 planning scenarios, and complete grocery coverage for benchmark demand; preserve frozen splits and digests |
| Multiple baselines | Partial | Strong Rule-only is executable; run frozen Context-matched LLM-only, Plain LLM and Human Manual comparisons only after common outputs and held-out labels are ready |
| Capability-centred Evaluation v2 | Partial | Packet compiler, coverage/leakage gates and visible developer packets are executable; the common output schema and strict-success scorer exist with tests but no runner calls them yet; independent held-out set, repeated model runs, human study and paired statistics remain open |
| User-facing quality | Partial | Typed quick clarification, cumulative-plus-daily Dashboard and the one-surface home journey passed 1280×720 Browser and Playwright acceptance; deepen loading, empty, error, degraded and accessibility coverage |
| Operations and maintainability | Target beyond the original proposal | Add health, data-quality, mapping, trace, and evaluation diagnostics where they reduce maintenance and demo risk |

## Backend Capability Traceability

This compact map identifies the merged evidence behind the backend boundary and
the next incomplete control. It is a navigation aid, not a second status source.

| Capability | Merged evidence | Remaining boundary |
| --- | --- | --- |
| Account and session security | Alembic revisions `20260906_0010` and `20260908_0012`; authentication service and routes; password, session and CSRF tests | Email verification, password reset/change, origin-level rate limiting and account lifecycle |
| Household tenancy | Alembic revision `20260916_0014`; current-household route dependency; household-scoped repositories; private-route authentication and cross-household integration tests | Broaden the endpoint-by-endpoint isolation matrix as private resources are added |
| Household authorization | `backend/app/auth/authorization.py`; action dependencies on the Profile, Plan, Check-in and Agent routes; owner/editor/member/viewer and CSRF-ordering tests in `backend/tests/test_backend_platform.py` | Member-management routes (`MANAGE_MEMBERS`) and system-role enforcement for the Console |
| Operations and Console | `OperationRun` and `AuditEvent` persistence scaffold plus the accepted backend platform design | Durable worker, safe operations APIs, system-role enforcement and Console user interface |

## Current Priorities

1. Record a signed-in run of the home surface against the real backend, and
   show replan history on it again.
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
9. Add member-management routes, expand the cross-household isolation matrix as
   private resources grow, and complete household collaboration plus account
   lifecycle flows.
10. Raise the discriminating power of the held-out evaluation before the final
    comparison. Parameters may be tuned on developer data only, never on
    held-out episodes (decision ADR-0020 as amended by ADR-0029). On the current v1 set the strong Rule-only reference
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
