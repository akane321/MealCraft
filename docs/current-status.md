# MealCraft Current Status

> Last verified public snapshot: 2026-09-27
>
> Remote repository: `akane321/MealCraft`
>
> Verified remote `main`: `f1f2f96`

## How to Read This Document

- **Verified** means the capability was merged to remote `main` and supported by
  recorded code or test evidence.
- **Partial** means a working slice exists but does not yet meet the final design
  depth.
- **Target** means the accepted product direction; it is not current behaviour.
- Current code and tests take precedence if this snapshot becomes stale.

## Planning product path

New weekly plans go through `ProductPlanningEngine`
([product adapter](design/planning-product-path.md)): constraint compilation,
bounded `BeamPlanner` search and the independent `FinalPlanningValidator`; a plan
that fails or is indeterminate is not saved, and plan storage and a redacted
`OperationRun` are atomic. `planner_strategy=greedy-baseline` selects the
reference path under the same gate. A week is planned as days × meals (decision
ADR-0046): the household's plan shape names the meals of a day (breakfast, lunch,
dinner; default dinner only) and each meal's dishes (default one main and one
vegetable), and `MealBeamPlanner` fills every (day, meal) slot. `PLANNING_CAPABILITY`
defaults to `full`; `mvp` (one dinner dish a day) remains for reproducing the
recorded evaluations. The candidate recipes are kept in memory for five minutes
(`PLANNING_POOL_CACHE_SECONDS`), so a week on the real catalog takes about 7 s in
the local Docker stack and a change to it 0.1–5 s.

Of ADR-0033's packets, P1 (product path), P2 ([conflict explanations](design/planning-conflict-explanation.md))
and P4 ([nutrition scope](design/planning-nutrition-scope.md)) are wired into the product.
P3 ([diversity rules](design/planning-diversity.md)) and P5 (mixed shopping) exist
as code but are not on the product path; P6 minimal-change replanning, P7 learned
ordering/themes and P8 ablations are not built.

## Verified Product Baseline

| Area | Verified behaviour | Important boundary |
| --- | --- | --- |
| Full-stack environment | FastAPI, PostgreSQL, Nuxt, Docker Compose, migrations, catalog import, and CI (which also lints and tests `data-engineering`) | Local development baseline, not production deployment evidence |
| Household profile | One shared profile, member servings and safety constraints, shared defaults, immutable versions, profile-linked plans. Each ingredient carries an allergen list; an allergen outside the checked vocabulary (`data/ingredients/allergen-vocabulary.json`) excludes every recipe rather than none, and the profile offers only allergens the catalog can check | Does not generate separate dishes for each member. Allergen labels are rule-derived from ingredient data, not verified against products |
| Identity, sessions and tenancy | Argon2id credentials with upgrade-on-login, atomic account and default-household registration, login lockout, digest-only opaque sessions, per-session CSRF, current-actor lookup, session listing, logout and per-device revocation. Private Profile, Plan, Dashboard, Agent, Replanning and Shopping workflows require an active authenticated household; private ownership is non-null, repository queries are household-scoped, cross-household identifiers resolve as not found, and the browser has registration and login flows. Private routes authorize each action through one `HouseholdAction` dependency (`VIEW`, `EDIT_PROFILE`, `CREATE_PLAN`, `CHECK_IN`) in the order authentication, active household, action, CSRF; unknown roles are denied | No member-management or household-deletion routes exist yet, so `MANAGE_MEMBERS` and `DELETE_HOUSEHOLD` are defined but unused. Household collaboration is incomplete; password lifecycle and account export/deletion are out of scope by the owner's decision (2026-09-26, no deployment) |
| Recipe catalog | 30 validated recipes and 34 normalized ingredients imported idempotently | Smaller and less dimensional than the final benchmark target |
| Data engineering | Independent `data-engineering/` pipeline with frozen schema v1, a four-condition release gate, and release v1.1 containing 9,282 recipes and 465 canonical ingredients. Deterministic derived dietary tags cover vegetarian (5,625), gluten-free (4,507), dairy-free (3,602) and vegan (1,030) recipes. A first nutrition-mapping pass matches the curated ingredient set (533 entries) against USDA Foundation Foods, SR Legacy and FNDDS with recorded evidence: 213 `mapped`, 209 `needs_review`, 111 unresolved ([progress report](../data-engineering/docs/task-b-nutrition-mapping-progress.md)). Release v2 (decision ADR-0030) is built: all three enrichment packets are complete (838 ingredient forms, 12,333 recipes), and the build cuts 9,048 released recipes over 29 cuisines with a per-serving energy median of 327 kcal ([quality report](../data-engineering/data/release/v2/quality_report.md), [attribution](../data-engineering/data/release/v2/ATTRIBUTION.md)). Part C was re-enriched item by item on 2026-09-21, replacing the constant fill; the fixed-seed sampled audit, re-judged for part C, accepted 35 of 39 recipes (5 corrections recorded) and 19 of 19 ingredients ([verdicts](../data-engineering/docs/v2-sampled-audit.json)). Release v1 is deleted as ADR-0030 requires; v1.1 remains the source | The re-audit of part C was done by the same producer family (Claude) that re-enriched it, so it is not an independent review. Real course labels now bind the per-bucket side/dessert caps, which is why fewer recipes are released than before. Release v2.1 carries the checks v2 lacked: 220 recipes whose steps use an unlisted allergen food (some RecipeNLG sources list only part of a dish) are dropped after a per-recipe review, ten ingredients carry owner-confirmed stricter allergens, and fish or shellfish rules out vegetarian and vegan ([quality report](../data-engineering/data/release/v2.1/quality_report.md)); a 300-recipe sample the check did not flag found one miss. The owner's fixed-seed audit of 40 review decisions ([audit](../data-engineering/docs/completeness-v2.1-sampled-audit.json)) accepted all 25 kept recipes, 9 of 10 dropped ones and all 5 unflagged ones; the one correction (a listed egg substitute read as a missing egg) keeps a recipe the next release restores. It is imported beside the curated recipes (`python -m app.data.import_release_v2`, run at compose start; see [Data](data/README.md)): 8,967 recipes, upgrading v2 rows in place. Recommendations rank every meal-course recipe (curated, and release `main`/`soup`) and keep the best 500 within budget. Release ingredients are priced through a FairPrice mapping captured and proposed on 2026-09-21 (707 ingredients, 563 mapped, 142 unavailable, water and ice not purchased; mappings under confidence 0.6 are left unpriced), so 4,556 of the 5,680 meal-course recipes can enter weekly plans. The mapping is AI-proposed; the owner's fixed-seed review of 40 ingredients accepted all 40, and four product choices its notes identified as wrong were removed ([review](../data-engineering/docs/fairprice-v2-sampled-review.json)). Release v2.1 is the runtime release: per-serving nutrition is computed (ingredient grams × per-100 g values), and release recipes whose numbers show a lost main line (a main under 150 kcal a serving, or a title protein it does not list; 244 recipes, decision ADR-0045) stay browsable but are never planned. Cuisine, meal types and difficulty are filled by the v2 enrichment and imported (agent-labelled, not reviewed; decision ADR-0038 corrects an earlier statement that they were empty), and the planner reads meal types as a soft affinity; methods and equipment are not in the release. Course labels decide which dish role a recipe may fill (decision ADR-0036), so the owner audited a fixed-seed sample of 80, ten per role course ([audit](../data-engineering/docs/course-v2.1-sampled-audit.json)): 78 accepted, and two desserts that are cookies corrected to `baked_good`, a correction the next release applies. Derived dietary tags are not reviewed gold labels, and allergen labels remain deterministic-rule-only |
| Home surface | `/` keeps the film entry, then opens the kitchen-table workspace (decision ADR-0043, amending ADR-0026): navigation, recent conversations and the household card on the left; the chat on the Agent session API in the centre (week card, swap comparison, clarification, confirmation, replan preview and confirm/discard); tonight, dinners, the shopping list with budget and nutrition on the right. The shopping list previews as a sheet and exports through print-to-PDF; nutrition and recipe sheets open over the workspace; applied replan events are listed with the dinners (`ChangeLog.vue`). The week is shown by day and meal, with "Today"/"Next up" and nutrition per meal and per day; each dish still to cook offers Swap, Keep, Skip and Can't buy, which put the request into the chat for the usual preview. Other pages are `/login`, `/profile` (with a meals-and-dishes editor), `/browse` (recipe search by title and course; FairPrice product search, saved or live prices), `/history` (past weeks by day and meal) and `/system`, all linked from the rail or the page header; no horizontal scroll at 1440/1280/900/390 | A signed-in walkthrough on the real stack was done on 2026-09-26 and its fixes recorded (decision ADR-0045). Tutorials are live YouTube results when a key is configured; named errors fall back to the sample set. Administrators have a separate console at `/ops`; see Operations and maintainability |
| Agent | Persistent household-scoped sessions, bilingual scope isolation, structured constraints, typed clarification, confirmation, bounded tool authorization, grounded claims, Agent-driven replanning, and synchronous per-action `AgentRun` with authenticated actor/household provenance, input digests, explicit deadlines and budgets, durable checkpoints, ordered tool receipts, idempotent replay and run list/detail/cancel APIs | Default parser is deterministic fixture mode; `AGENT_PARSER_PROVIDER=openai` uses the live model with the same templated replies (it failed to build its vocabulary against the database until a fix on 2026-09-26). Plan confirmation is not yet bound to a specific preview: `POST /api/agent/sessions/{id}/confirm` takes no preview id, context version or expiry, generates and saves the plan in one call, and records the generation step as a preview although it already persists the plan; ADR-0016's matched, unexpired confirmation is target work. Runs are synchronous: asynchronous pause/resume/retry, external-tool evidence, natural-language claim extraction and formal live-model evidence are deferred |
| Weekly planning | Seven persisted main meals plus independently callable Planning v2 constraint compilation, bounded Beam Search, conservative nutrition bounds, independent shopping/budget recomputation, and a small exhaustive oracle. Weekly budgets are compared in whole cents on both sides (ADR-0021). In Planning v2 a recipe's meal type is a soft affinity, not a filter (ADR-0024 section 5); the CP-SAT package oracle's tests run in CI. A meal can hold several dishes (ADR-0036): dish roles such as main, vegetable and optional soup, each cooked at a portion share (1.0, 0.75/0.5, 0.6/0.4, 0.5/0.35) with a one-cook meal-time estimate, validated dish by dish and meal by meal and planned by a meal beam search; the API stores dishes per meal, swaps one dish, checks in a whole meal and has the agent ask which dish. Since ADR-0046 a week holds the meals the household chose, each with its own composition of up to six dishes (presets per meal, or a custom mix such as two mains, a vegetable and a soup), set in the profile and changeable in the conversation ("also plan lunch", "add a soup on Friday", "no side dish tonight"; see Replanning); variety is kept across the whole week and a slot prefers dishes of its own meal type | The meal-day-week planner is evaluated on 16 developer episodes only ([protocol](evaluation/protocol-v3-meal-day-week.md), [report](evaluation/v3-meal-day-week/dev/latest.md)): 11 of 16 on the first run, 15 of 16 after two fixes found by it (whole-cent release prices; `per_day` nutrition targets, checked day by day in the meal search), so these are diagnostics, not evidence; the three-meal episode under S$49 still finds no week. A held-out set will be drafted and owner-reviewed before any claim (ADR-0046 section 5). At a tight budget with a main and a vegetable every night, dishes repeat; the five-dish dinner reaches about 20 distinct dishes in 35. They are evaluated under protocol v2-multidish on a frozen 40-episode held-out set ([report](evaluation/v2-multidish/heldout/latest.md), [findings](evaluation/v2-multidish/heldout/findings.md)): with gold constraints, CP-SAT solved 40 of 40 and the beam 34 in the first run, failing exactly the six episodes that state a weekly budget, because the beam never scored cost and the validator then rejected its plans; the beam now prices a partial plan in whole packages and holds the cheapest candidates in reach, developed on four new developer episodes only, and a second run of the same set has both at 40 of 40 (both runs are reported, and the beam's variety fell from 11.9 to 9.9 distinct recipes). The rule-parser arms reach 17 to 21 of 40, mostly by answering with a plan where the request is infeasible or needs a question. The live-model arms have run on the owner's key (`gpt-5.4-mini`, a token cap per run). Every failure of the arms where the model reads and a solver plans is a misreading of the request, never the solver: A (beam) and B (CP-SAT) fail the same episodes in every pass. Giving the model the catalog's vocabulary, developed on developer episodes, took them from 31-32 to 37-38 of 40 over four passes; the model planning unaided (D) stays at 14-18. The set has now been looked at four times, so these are checks, not unseen evidence. A recipe line that allows either of two ingredients ("butter or margarine") is cooked, per household, with its first option the household can eat and the planner can buy, so a no-butter household keeps those 205 recipes; the choice drives eligibility, cost and the shopping list alike. The product agent parser now gets the same vocabulary (the database's ingredient ids and the checked allergens); a word it cannot match is asked about instead of being applied as a constraint that matches nothing. That question now offers up to four catalog ingredients as one-tap choices, an exact name or model-generated other name first and then the closest by embedding (ADR-0041); nothing is applied until the household picks, and the pick lands in the field the word came from. On a 63-term developer set written by the same session that tuned it, an acceptable ingredient was among the four for 56 of 62 terms (spelling alone: 26); on a frozen held-out set written by a teammate it was 15 of 21 unseen terms (spelling: 11), every miss a short Chinese word ([results](evaluation/embedding-heldout-results.md)). When a household asks to replace a meal and says what they want instead ("fish instead", "来点辣的"), the replacement is now chosen, among the candidates that already hold every constraint, by embedding similarity to what was described plus shared words (ADR-0042); with nothing described, or without the live model, the swap orders by score as before. On 20 developer requests checked on catalog facts it picked what was asked for in 80% of trials against 10% before; on 21 frozen held-out requests written by a teammate, 69% against 8% (shared words alone: 50%), weakest on Chinese and abstract requests ([results](evaluation/embedding-heldout-results.md)). Catalog Chinese names (`data/ingredients/aliases-zh-v1.json`) and English glosses for Chinese swap words were then developed on new Chinese developer sets (`data/evaluation/agent/*-zh-dev.json`; developer-only: ingredient top-4 26/57 to 58/58 after fitting, swaps 55% to 89% with the model); a new Chinese held-out set awaits a teammate author ([prompt](evaluation/chinese-heldout-prompt.md)). Excluded ingredients are expanded by the [ingredient hierarchy](design/ingredient-hierarchy.md) (ADR-0039) before eligibility is checked, in the recommendation engine and in the planning product path, so "no tofu" also removes `firm_tofu` and "no pork" removes bacon; the agent's vocabulary offers hierarchy groups such as `group:alcohol`. All 716 catalog ingredients are decided (15 curated-only, 320 animal, drink and prepared-food, 381 plant and pantry), with groups for alcohol and the onion-garlic family. The product path is described under [Planning product path](#planning-product-path); Beam parameters are untuned and the oracle proves results only for small packets under the fixed shopping policy |
| FairPrice | Live lookup verified against the live site, normalized results, 15-minute PostgreSQL cache, and a live → saved-snapshot → fixture degradation chain with a warning and a `degraded` trace. An empty live result is a typed `no_match`: the ingredient stays unpriced instead of borrowing sample prices. A test generates a live-priced weekly plan with every FairPrice request failing and still gets a Shopping List | The disconnected run is covered by an automated test with the network stubbed out, not yet by a demonstration on a physically disconnected machine |
| Shopping List | Aggregated demand, known-quantity deduction, package rounding, price and budget results | Unknown pantry quantities are never deducted |
| Check-in and Dashboard | Planned/completed/skipped states, completed cumulative nutrition KPIs and curves, current-plan comparison, labelled daily detail, completion coverage | Cumulative actuals count completed MealCraft dishes only; planned rows are previews and skipped rows are not counted |
| Replanning | Preview, confirm/discard, plan revision, event history, local meal changes, price and Shopping List deltas. Shape changes by request (ADR-0046 section 2): add or drop a meal for the rest of the week, change a meal's dishes, or add or take away a dish in one meal. Only the affected meals are planned again, with the budget the rest of the week leaves; adding a dish to one meal keeps the dishes it has and chooses only the new one, and taking a dish away keeps the others at their larger share; cooked and locked meals never change. A week-wide change applies to this week, and the assistant then asks whether new weeks should plan the same way, saving it to the profile only on a yes | Shape changes are read by rules (English and Chinese), not by the model. A week-wide change ("dinners with a soup") plans those meals again from scratch. Broader preference and stress-event semantics remain partial |
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
`infeasible_conflict`. Twenty-nine have completed eligible human review: 10
reviewed by `backend`, 9 by `dataset`, 7 by `planning` and 3 by `frontend-evaluation`.
Twenty-one await review: 8 `standard`, 5 `budget_package`, 4 `infeasible_conflict`,
2 `clarification` and 2 `pantry_expiry`. The set is not frozen and must not
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
`dev-111`, one eligible dish each), which is why its gate fails.

The owner then decided that a repetition the catalog forces is not a planning
failure (protocol v1.1, decision ADR-0035,
[protocol section 8](evaluation/protocol-v1.md)). The rule was decided after
these results were seen and is not pre-registered. It is a new protocol
version, so the v1 report above is unchanged; the same sets rescored under
v1.1 are reported beside it
([report](evaluation/workbench/catalog-v2.1-scenarios-v1.1/latest.md),
[conditions](evaluation/workbench/catalog-v2.1-scenarios-v1.1/conditions.json)).
The forced count comes from the catalog alone
([record](evaluation/catalog-v2.1-labels.json)): one eligible dish forces six
repetitions a week, and a budgeted scenario is recorded as forcing none.

| Held-out, 60 scenarios, v1.1 | Greedy baseline | Strong Rule-only | MealCraft |
| --- | ---: | ---: | ---: |
| Adjacent repetitions (raw) | 348 | 6 | 6 |
| Forced by the catalog | 6 | 6 | 6 |
| Avoidable repetitions | 342 | 0 | 0 |
| Recorded failure cases | 57 | 0 | 0 |

The developer gate passes under v1.1: its 12 repetitions are all forced. The
rule removes the same failure from the Strong Rule-only reference as from
MealCraft, so it does not separate them; mean distinct recipes still does.

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

- Exact-case rate: `24/24 = 1.0`;
- Field precision, recall and F1: `1.0`;
- Clarification and medical-boundary accuracy: `1.0`;
- Hallucinated fields and Agent failures: `0`.

The failures were fixed after they had been seen on this visible developer set,
so these numbers are diagnostic rather than independent evidence. The report's
36 recorded failure cases are all greedy-baseline failures, not MealCraft
product defects.

## Gap to the Final Product Baseline

The initial proposal remains the minimum final-product ambition. Technologies
may be substituted, but the product responsibility should be preserved or
improved.

| Design capability | Status | Remaining work |
| --- | --- | --- |
| Unified planning workspace | Partial | The kitchen-table workspace joins conversation, week, tutorial, recipe detail, nutrition detail, shopping-list export and applied replan history; the real-backend walkthrough is recorded (ADR-0045). Remaining: meal + day + week planning with per-day meal choice and editable per-meal composition, recipe/product search, plan history, whole-meal check-in, and entry points for lock/cancel/unavailable and `/system` |
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
| Capability-centred Evaluation v2 | Partial | Packet compiler, coverage/leakage gates and visible developer packets are executable; the common output schema and strict-success scorer exist with tests but no runner calls them yet; paired statistics over the recorded v2-multidish runs are reported ([paired](evaluation/v2-multidish/heldout/paired.md)), but that set was used for two fixes, so they are not pre-registered; an unseen held-out set and a human study remain open |
| User-facing quality | Partial | Typed quick clarification, cumulative-plus-daily Dashboard and the one-surface home journey passed 1280×720 Browser and Playwright acceptance. Each drawer now distinguishes loading (skeleton with `aria-busy`), failed (with a working retry) and empty, and the three overlays behave as dialogs: Escape from anywhere, focus moved in and restored, Tab trapped, background locked. Remaining: degraded-state coverage beyond price provenance, and a wider accessibility pass |
| Operations and maintainability | Partial | The console at `/ops` (decision ADR-0047, amending ADR-0031): fixed admin accounts from `ADMIN_ACCOUNTS` sign in through the same login page; overview charts, task records, service health with live checks, debugging replays (agent and planning, with parser or planner overrides, compared side by side), experiments and runtime settings (a registry stored in the database, change history, developer evaluation runs and A/B), users, and catalog data (recipes, ingredient names and aliases, product mappings; allergens view only). Every change writes an audit row. Remaining: a durable worker, and runtime settings the product does not read yet (they are labelled "Stored only" in the console) |

## Backend Capability Traceability

This compact map identifies the merged evidence behind the backend boundary and
the next incomplete control. It is a navigation aid, not a second status source.

| Capability | Merged evidence | Remaining boundary |
| --- | --- | --- |
| Account and session security | Alembic revisions `20260906_0010` and `20260908_0012`; authentication service and routes; password, session and CSRF tests | Out of scope by the owner's decision (2026-09-26, no deployment): email verification, password reset/change, rate limiting and account lifecycle are not planned |
| Household tenancy | Alembic revision `20260916_0014`; current-household route dependency; household-scoped repositories; private-route authentication and cross-household integration tests | Broaden the endpoint-by-endpoint isolation matrix as private resources are added |
| Household authorization | `backend/app/auth/authorization.py`; action dependencies on the Profile, Plan, Check-in and Agent routes; owner/editor/member/viewer and CSRF-ordering tests in `backend/tests/test_backend_platform.py` | Member-management routes (`MANAGE_MEMBERS`) are out of scope by the owner's decision |
| Operations and Console | `OperationRun` and `AuditEvent` persistence; `/api/ops/*` routes and services; migrations `20260927_0023` (runtime settings) and `20260928_0025` (catalog edits); `backend/tests/test_operations_*.py`; the `/ops` pages | Durable worker |

## Current Priorities

1. Draft, review and freeze a held-out set for meal + day + week planning
   (ADR-0046 section 5); look into the tight three-meal budget on developer data.
2. Prepare the Sprint 1 demonstration in OpenAI parser mode with rule fallback.
   Security and privacy hardening is out of scope (the course does not require
   deployment).
3. Complete nutrition-target and elastic-preference semantics and evidence.
4. Test FairPrice live/cache/fixture degradation against real changes.
5. Wire the remaining ADR-0033 packets (P3, P5) into the product path and build
   P6-P8, without overstating global optimality or infeasibility.
6. Extend the merged synchronous `AgentRun` into asynchronous pause/resume/retry
   with bounded external-tool adapters, then build an independent held-out
   orchestration set and the common v2 output validator before any explicitly
   authorized, budget-capped live-model comparison.
7. Expand dynamic-replanning stress cases and measure unnecessary disruption.
8. Increase browser coverage and prepare a repeatable demonstration path.
9. Expand the cross-household isolation matrix as private resources grow
   (member management is out of scope by the owner's decision).
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
