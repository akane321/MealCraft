# MealCraft Current Status

> Last verified public snapshot: 2026-09-20
>
> Remote repository: `akane321/MealCraft`
>
> Verified remote `main`: `55e6d8a`

## How to Read This Document

- **Verified** means the capability was merged to remote `main` and supported by
  recorded code or test evidence.
- **Partial** means a working slice exists but does not yet meet the final design
  depth.
- **Target** means the accepted product direction; it is not current behaviour.
- Current code and tests take precedence if this snapshot becomes stale.

## Planning P1 and P2 follow-up verification

On 2026-09-21, remote main `a4a56c74ea3da9757e71db0949decf4232548ff6`
contains P1 and P2. The descriptions below cover those merged slices; the
top-of-file snapshot and unrelated module entries have not been reverified.

## Planning P1

The P1 implementation routes new weekly-plan generation through bounded beam
search and independent validation, including the shared profile and Agent entry
points. An explicitly selected greedy baseline uses the same acceptance gate.
Plan storage and a redacted `OperationRun` are atomic; failed or indeterminate
results create no plan. See the [product adapter](design/planning-product-path.md)
and [API contract](api-contracts.md#weekly-meal-plans).

P3 hard variety caps, P4 scoped nutrition, P5 mixed
shopping, P6 minimal-change replanning, P7 learned ordering/themes and P8 console
experiments remain separate packets. Existing legacy nutrition targets remain
soft ranking inputs. This slice does not claim that the whole v2 contract is done.

## Planning P2

P2 builds on P1 with bounded conflict diagnosis and independently
verified numeric proposals. Users apply a proposal by submitting a new request;
failed requests do not save a relaxed plan. Explanations preserve safety
constraints and distinguish a declared-group minimum from a global claim.
See [conflict explanations](design/planning-conflict-explanation.md).

The implementation is bounded to small packets, and may withhold proposals when proof exceeds its limits. It
does not add proposal buttons, a Console view or mixed-package purchasing.

## Planning P3 local packet implementation

The P3 branch adds explicit versioned recipe classification, three hard variety
rules, bounded non-core overlap scoring and independent final checks. Beam,
greedy reference and the fixed/mixed shopping paths consume these packet rules.
See [Planning diversity](design/planning-diversity.md) for the contract and
synthetic fixture.

This slice is local work pending review. It has not enabled P3 on the weekly
product API: the runtime catalog has no explicit primary-protein/core-ingredient
classification. That producer handoff and production adapter remain to be
completed. Legacy packets without a diversity policy keep their existing
behavior and must not be described as satisfying P3. Console integration also
remains separate; there are no new Console endpoints or controls here.

## Verified Product Baseline

| Area | Verified behaviour | Important boundary |
| --- | --- | --- |
| Full-stack environment | FastAPI, PostgreSQL, Nuxt, Docker Compose, migrations, catalog import, and CI (which also lints and tests `data-engineering`) | Local development baseline, not production deployment evidence |
| Household profile | One shared profile, member servings and safety constraints, shared defaults, immutable versions, profile-linked plans. Each ingredient carries an allergen list; an allergen outside the checked vocabulary (`data/ingredients/allergen-vocabulary.json`) excludes every recipe rather than none, and the profile offers only allergens the catalog can check | Does not generate separate dishes for each member. Allergen labels are rule-derived from ingredient data, not verified against products |
| Identity, sessions and tenancy | Argon2id credentials with upgrade-on-login, atomic account and default-household registration, login lockout, digest-only opaque sessions, per-session CSRF, current-actor lookup, session listing, logout and per-device revocation. Private Profile, Plan, Dashboard, Agent, Replanning and Shopping workflows require an active authenticated household; private ownership is non-null, repository queries are household-scoped, cross-household identifiers resolve as not found, and the browser has registration and login flows. Private routes authorize each action through one `HouseholdAction` dependency (`VIEW`, `EDIT_PROFILE`, `CREATE_PLAN`, `CHECK_IN`) in the order authentication, active household, action, CSRF; unknown roles are denied | No member-management or household-deletion routes exist yet, so `MANAGE_MEMBERS` and `DELETE_HOUSEHOLD` are defined but unused. Household collaboration, password lifecycle and account export/deletion remain incomplete |
| Recipe catalog | 30 validated recipes and 34 normalized ingredients imported idempotently | Smaller and less dimensional than the final benchmark target |
| Data engineering | Independent `data-engineering/` pipeline with frozen schema v1, a four-condition release gate, and release v1.1 containing 9,282 recipes and 465 canonical ingredients. Deterministic derived dietary tags cover vegetarian (5,625), gluten-free (4,507), dairy-free (3,602) and vegan (1,030) recipes. A first nutrition-mapping pass matches the curated ingredient set (533 entries) against USDA Foundation Foods, SR Legacy and FNDDS with recorded evidence: 213 `mapped`, 209 `needs_review`, 111 unresolved ([progress report](../data-engineering/docs/task-b-nutrition-mapping-progress.md)). Release v2 (decision ADR-0030) is built: all three enrichment packets are complete (838 ingredient forms, 12,333 recipes), and the build cuts 9,048 released recipes over 29 cuisines with a per-serving energy median of 327 kcal ([quality report](../data-engineering/data/release/v2/quality_report.md), [attribution](../data-engineering/data/release/v2/ATTRIBUTION.md)). Part C was re-enriched item by item on 2026-09-21, replacing the constant fill; the fixed-seed sampled audit, re-judged for part C, accepted 35 of 39 recipes (5 corrections recorded) and 19 of 19 ingredients ([verdicts](../data-engineering/docs/v2-sampled-audit.json)). Release v1 is deleted as ADR-0030 requires; v1.1 remains the source | The re-audit of part C was done by the same producer family (Claude) that re-enriched it, so it is not an independent review. Real course labels now bind the per-bucket side/dessert caps, which is why fewer recipes are released than before. Release v2.1 carries the checks v2 lacked: 220 recipes whose steps use an unlisted allergen food (some RecipeNLG sources list only part of a dish) are dropped after a per-recipe review, ten ingredients carry owner-confirmed stricter allergens, and fish or shellfish rules out vegetarian and vegan ([quality report](../data-engineering/data/release/v2.1/quality_report.md)); a 300-recipe sample the check did not flag found one miss. The owner's fixed-seed audit of 40 review decisions ([audit](../data-engineering/docs/completeness-v2.1-sampled-audit.json)) accepted all 25 kept recipes, 9 of 10 dropped ones and all 5 unflagged ones; the one correction (a listed egg substitute read as a missing egg) keeps a recipe the next release restores. It is imported beside the curated recipes (`python -m app.data.import_release_v2`, run at compose start; see [Data](data/README.md)): 8,967 recipes, upgrading v2 rows in place. Recommendations rank every meal-course recipe (curated, and release `main`/`soup`) and keep the best 500 within budget. Release ingredients are priced through a FairPrice mapping captured and proposed on 2026-09-21 (707 ingredients, 563 mapped, 142 unavailable, water and ice not purchased; mappings under confidence 0.6 are left unpriced), so 4,556 of the 5,680 meal-course recipes can enter weekly plans. The mapping is AI-proposed; the owner's fixed-seed review of 40 ingredients accepted all 40, and four product choices its notes identified as wrong were removed ([review](../data-engineering/docs/fairprice-v2-sampled-review.json)). Nutrition remains `not_computed`: the mapping is not yet turned into per-recipe values (no quantity-to-mass conversion or aggregation). Cuisine, meal types, methods, equipment and difficulty remain empty. Derived dietary tags are not reviewed gold labels, and allergen labels remain deterministic-rule-only |
| Home surface | `/` is the product surface: a full-bleed film entry whose command bar becomes a chat on the Agent session API (clarification answers, confirmation, replan preview and confirm/discard). Edge panels open on hover, keyboard focus or pin and move the chat aside: the week with tonight's Top-1 tutorial and cooked check-in on the left; cooked nutrition, per-dinner calories and the shopping list against budget on the right. The shopping list previews as a sheet and exports through the browser's print-to-PDF. Liquid-glass styling uses an edge-lens backdrop filter in Chromium and frosted glass elsewhere. A nutrition sheet (six nutrients, cumulative curve, daily table with cooked/skip/undo) and a recipe sheet (ingredients with allergen labels, steps) open over the surface. The only other pages are `/login`, `/profile` (behind the avatar) and `/system` (service status); login returns to a same-site `?next=` path | Browser-tested at 1280×720 against a stubbed API; a signed-in run against the real backend is not yet recorded. Tutorials come from a four-video sample set (live YouTube search is a scaffold), so only dishes whose name matches a sample video show one, labelled as a sample; the rest say no video is available yet. Price labels read the products actually used, so a live request that fell back to sample data says so. Replan events are recorded by the backend but no longer shown in the interface |
| Agent | Persistent household-scoped sessions, bilingual scope isolation, structured constraints, typed clarification, confirmation, bounded tool authorization, grounded claims, Agent-driven replanning, and synchronous per-action `AgentRun` with authenticated actor/household provenance, input digests, explicit deadlines and budgets, durable checkpoints, ordered tool receipts, idempotent replay and run list/detail/cancel APIs | Default parser is deterministic fixture mode. Plan confirmation is not yet bound to a specific preview: `POST /api/agent/sessions/{id}/confirm` takes no preview id, context version or expiry, generates and saves the plan in one call, and records the generation step as a preview although it already persists the plan; ADR-0016's matched, unexpired confirmation is target work. Runs are synchronous: asynchronous pause/resume/retry, external-tool evidence, natural-language claim extraction and formal live-model evidence are deferred |
| Weekly planning | Seven persisted main meals plus independently callable Planning v2 constraint compilation, bounded Beam Search, conservative nutrition bounds, independent shopping/budget recomputation, and a small exhaustive oracle. Weekly budgets are compared in whole cents on both sides (ADR-0021). In Planning v2 a recipe's meal type is a soft affinity, not a filter (ADR-0024 section 5); the CP-SAT package oracle's tests run in CI | The product API still uses the current baseline path; Beam parameters are untuned and the oracle proves results only for small packets under the fixed shopping policy. How the engine enters the product, and which deepenings follow, is decided (ADR-0033) and specified in [Planning and Validation v2](design/planning-validation-v2.md); none of it is built yet |
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
- 30 curated recipes and 34 normalized ingredients in the recorded catalog, plus 8,967 release v2.1 recipes imported beside them (slugs prefixed `v2-`).

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

#### The same comparison on the larger catalog

Run again with release v2.1 imported beside the curated recipes
(`python -m app.evaluation.workbench --release data-engineering/data/release/v2.1`,
[report](evaluation/workbench/catalog-v2.1/latest.md),
[conditions](evaluation/workbench/catalog-v2.1/conditions.json)): 8,997 recipes,
the release priced through its FairPrice snapshot. It is a separate condition
and does not replace the numbers above.

| Metric | Greedy baseline | Strong Rule-only | MealCraft |
| --- | ---: | ---: | ---: |
| Scenario expectation rate | 0.95 | 0.95 | 0.95 |
| Adjacent repetitions | 228 | 6 | 6 |
| Mean distinct recipes | 1.0 | 1.9737 | 6.7368 |
| Hard-constraint violations | 0 | 0 | 0 |
| Recorded failure cases | 38 | 2 | 2 |

The two cases every system now fails are held-out episodes written as
infeasible against the 30-recipe catalog (`hold-037`, a five-minute limit, and
`hold-039`, vegetarian dairy-free in five minutes): the release holds microwave
dishes that meet them, so all three systems plan a week and the expectation no
longer holds. Their six repetitions come from those episodes, where one to three
recipes are eligible. The developer set's two matching episodes (`dev-019`,
`dev-020`) fail its gate for the same reason. The episodes are not edited here:
held-out expectations are fixed, and the larger catalog needs its own authored
conditions (authored below). Every other episode's shopping list is complete; the
run first exposed a weekly-aggregation fault that turned one ingredient needed
in two units into an unknown amount, fixed before this report.

#### Scenario sets written for the larger catalog

Conditions for the larger catalog were then authored
([report](evaluation/workbench/catalog-v2.1-scenarios/latest.md),
[conditions](evaluation/workbench/catalog-v2.1-scenarios/conditions.json)):

- the v1 scenarios relabelled from the catalog alone by
  `scripts/derive_catalog_labels.py`, which runs no system under test
  ([record](evaluation/catalog-v2.1-labels.json)): `dev-019`, `dev-020`,
  `hold-037` and `hold-039` become feasible, and every other label stands,
  since a larger catalog can only add feasible scenarios;
- 13 developer scenarios for what the larger catalog can express (fish,
  tree-nut and nine-allergen requests, excluded meats, 10-15 minute dinners),
  chosen not to overlap the held-out ones;
- 20 held-out scenarios drafted by an AI agent in a sealed packet (catalog
  facts, request schema and authoring rules; no code, results or other held-out
  cases) and accepted by the owner in two rounds, four revised in between
  ([review](../data/evaluation/heldout/planning-catalog-v2.1-new.review.json)).
  None is infeasible: written as household requests first, the two that were
  meant to be came out feasible, and realistic zero-match requests are rare on
  this catalog. Infeasibility is covered by v1's `hold-038` and `hold-040`.

| Held-out, 60 scenarios | Greedy baseline | Strong Rule-only | MealCraft |
| --- | ---: | ---: | ---: |
| Scenario expectation rate | 1.0 | 1.0 | 1.0 |
| Adjacent repetitions | 348 | 6 | 6 |
| Mean distinct recipes | 1.0 | 1.9828 | 6.6897 |
| Hard-constraint violations | 0 | 0 | 0 |
| Recorded failure cases | 58 | 1 | 1 |

The one failure MealCraft and the Strong Rule-only reference share is
`hold-039`, where exactly one dish meets the constraints, so a week of seven
must repeat it; the protocol counts that as a failure and it is reported as
one. The same holds for the developer set's two failures (`dev-020`,
`dev-111`, one eligible dish each), which is why its gate fails. The scoring
rule is not changed here: changing it after seeing these results would be
fitting the evaluation to them (priority 2).

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
| Unified planning workspace | Partial | The home surface joins conversation, week, tutorial, recipe detail, nutrition detail and shopping-list export; the earlier separate pages are removed. Applied replan history is listed again in the week panel. Remaining: record a signed-in walkthrough against the real backend |
| Authentication and user separation | Partial | Authentication, non-null household ownership, household-scoped repositories, cross-household denial, per-action household authorization and browser registration/login are merged. Remaining: member-management routes, a wider isolation matrix, household collaboration, password lifecycle and account export/deletion |
| High-dimensional recipe knowledge | Partial | Expand the catalog and complete cuisine, taste, method, equipment, difficulty, nutrition provenance, instruction, source, and media fields |
| Verified recipe benchmark | Partial | Import a gated, enriched data release into the runtime catalog; the recipe count is set by what passes the release gate, not by a fixed range (decision ADR-0024) |
| Validated web-recipe supplementation | Target | Specified in [External Recipe Intake](design/external-recipe-intake.md) (decision ADR-0032): parsing, duplicate check, ingredient mapping, the user-confirmed allergen question, source tiers and an admission gate equal to the release gate. Not built |
| Semantic preference retrieval | Target | Combine semantic matching with strict metadata filtering and evaluate its incremental value |
| Recipe execution side panel | Partial | The recipe sheet shows ingredients, allergen labels and steps, and the left panel carries tonight's tutorial. Remaining: attributes, provenance and a tutorial per dish beyond the sample set |
| Final-scope planning and validation | Partial | Constraint compilation, bounded Beam Search, conservative bounds, independent shopping/budget validation and a small exhaustive oracle are executable. The integration and its deepenings are specified as eight packets in [Planning and Validation v2](design/planning-validation-v2.md) (decision ADR-0033): wire the engine and the independent validator into the product path, explain infeasibility with a minimal conflicting set and a numeric relaxation, bound variety against ingredient overlap, compile nutrition scope, purchase across the whole slot set, replan with minimal perturbation, add a reorder-only learned ranking that ships off, and run the ablations |
| Nutrition elastic policy | Partial | Complete source-aware target deviation, lower-sodium/lower-sugar policy, tolerance, missing-data behaviour, and dedicated evaluation |
| Grocery grounding robustness | Partial | Measure live/cache/fixture degradation, mapping quality, package parsing, and source freshness |
| Dynamic replanning | Partial | Add broader event semantics, temporary versus persistent preference handling, disruption metrics, and Shopping List consistency stress tests |
| Agent scope, interaction and grounding | Partial | Bilingual scope/mixed-intent isolation, typed UI interaction, stale-answer guard, deny-by-default authorization, structured claim verification and synchronous durable `AgentRun` checkpoints are executable; production classifier evidence, asynchronous pause/resume/retry, the full typed tool graph, external-tool evidence and natural-language claim extraction remain target work |
| Evaluation scale | Partial | Expand toward 150-200 verified requests, a gated imported recipe release, 80-120 planning scenarios, and complete grocery coverage for benchmark demand; preserve frozen splits and digests |
| Multiple baselines | Partial | Strong Rule-only is executable; run frozen Context-matched LLM-only, Plain LLM and Human Manual comparisons only after common outputs and held-out labels are ready |
| Capability-centred Evaluation v2 | Partial | Packet compiler, coverage/leakage gates and visible developer packets are executable; the common output schema and strict-success scorer exist with tests but no runner calls them yet; independent held-out set, repeated model runs, human study and paired statistics remain open |
| User-facing quality | Partial | Typed quick clarification, cumulative-plus-daily Dashboard and the one-surface home journey passed 1280×720 Browser and Playwright acceptance. Each drawer now distinguishes loading (skeleton with `aria-busy`), failed (with a working retry) and empty, and the three overlays behave as dialogs: Escape from anywhere, focus moved in and restored, Tab trapped, background locked. Remaining: degraded-state coverage beyond price provenance, and a wider accessibility pass |
| Operations and maintainability | Target beyond the original proposal | Specified in [Operations Console](design/operations-console.md) (decision ADR-0031): a role-gated internal `/ops` surface for health, task runs, data quality, the planning-run inspector, retrieval and agent traces, and the experiment and ablation module with its recorded conditions. Not built |

## Backend Capability Traceability

This compact map identifies the merged evidence behind the backend boundary and
the next incomplete control. It is a navigation aid, not a second status source.

| Capability | Merged evidence | Remaining boundary |
| --- | --- | --- |
| Account and session security | Alembic revisions `20260906_0010` and `20260908_0012`; authentication service and routes; password, session and CSRF tests | Email verification, password reset/change, origin-level rate limiting and account lifecycle |
| Household tenancy | Alembic revision `20260916_0014`; current-household route dependency; household-scoped repositories; private-route authentication and cross-household integration tests | Broaden the endpoint-by-endpoint isolation matrix as private resources are added |
| Household authorization | `backend/app/auth/authorization.py`; action dependencies on the Profile, Plan, Check-in and Agent routes; owner/editor/member/viewer and CSRF-ordering tests in `backend/tests/test_backend_platform.py` | Member-management routes (`MANAGE_MEMBERS`) and system-role enforcement for the Console |
| Operations and Console | `OperationRun` and `AuditEvent` persistence scaffold, the accepted backend platform design, and the [console contract](design/operations-console.md) | Durable worker, safe operations APIs, system-role enforcement and Console user interface; no `/ops` route exists yet |

## Current Priorities

1. Record a signed-in run of the home surface against the real backend.
2. Decide, independently of the larger-catalog results, whether a repetition
   the catalog forces (one eligible dish) should count as a planning failure;
   the protocol counts every adjacent repetition today.
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
