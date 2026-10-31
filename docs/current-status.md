# MealCraft Current Status

> Last verified public snapshot: 2026-10-25 (targeted integration delta, not a new full-product acceptance)
>
> Remote repository: `akane321/MealCraft`
>
> Verified remote `main`: `33b49492` (reviewed product integration and aggregate-only evaluation apparatus)

### Verified integration delta (2026-10-25)

- #326/#328: maintenance and household-rule parsing fixes are merged; a sentence
  joining different answers asks for clarification rather than widening a rule.
- #337/#338: evidence-based role refinements and release v2.2 unit corrections
  are merged. Data completeness is not independent truth verification.
- #342/#345: review attestations bind to content; the reviewer-table batch remains
  gated until explicit owner acceptance. Merging the review tools did not accept
  the batch or make its unreviewed values available to planning.
- #347: synthetic conversation adapter phase one, paired with Knowledge #195.
  It tests message transport and output normalization with invented inputs only;
  shared formal contracts, product transport, freeze and run admission remain
  pending. It is not a formal evaluation run or score.
- #327 incorporates the reviewed #339/#340/#341/#343/#344 algorithm chain.
  Offline arms measure member variety over filled meals, retain exact-price and
  minimum-kind references, and add whole-horizon CP-SAT neighborhood repair.
  Generated developer comparisons retain their original source and environment.
  Synthetic prices, bounded meal-option domains and unreviewed grouping prevent
  product-scale, retail-savings or formal baseline claims. Product defaults have
  not switched to LNS or the offline member-mean objective.
- #349: the product beam can be followed by a validated simulated-annealing
  improvement. It keeps the product's meal and week checks, including actual
  checkout budgets and required variety; if adjacent repetition increases, it
  retains the verified beam plan. This is not a switch to the offline objective
  or a claim of a globally optimal week. All required checks passed on the exact
  reviewed head before merge.
- #329 integrates the individually reviewed preference, routing, food-question,
  substitution, external-intake and offline algorithm-wiring slices. Preferences
  can be edited, saved, cancelled and undone without changing hard constraints;
  current household restrictions and stale-preview guards remain enforced.
  Halal planning was declined then (ADR-0091; supported since #404, ADR-0104), and HTTP halal declarations
  are required rather than silently defaulted. Numeric and safety answers use
  catalog evidence; ordinary cooking knowledge may use attributed web sources.
- External intake normalizes reviewed vocabulary, ingredient and role evidence,
  household safety, provenance and recipe identity before household-private
  admission; failures have a catalog fallback. Unknown evidence is not verified
  safe. Live extraction quality and independent human accuracy remain unverified.
- The new algorithm comparison wiring is offline developer tooling only. It uses
  the current common outputs and scorer, exposes no paid entry, and is not formal
  baseline registration or held-out run admission. The separate unbudgeted live
  developer entry remains disabled, including inside the backend container.
- #352 adds a pure supplied-outcome aggregate report by category, language and
  source. Its reviewed head passed all required checks
  ([CI run](https://github.com/akane321/MealCraft/actions/runs/40202445306)); 37
  local synthetic aggregate/adapter tests passed. This is apparatus, not an actual
  held-out result, a scorer or run admission. Expected-manifest validation and
  small-cell disclosure policy remain required before formal export; see the
  [aggregate contract](evaluation/heldout-aggregate-report.md).
- Issue #315 is closed against its stated engineering acceptance, not against
  live-model or independent human-quality targets. Issue #310 remains open for
  independent near-duplicate labels, matched exact/real-price evidence, composed
  parameter calibration and mixed-purchase/product acceptance still missing.

The integrated #327 head passed all required CI checks before merge; the combined
targeted synthetic/SQLite regression also passed. This verification did not open
protected held-out inputs, labels or results, call paid models, or use Docker
locally. Formal evaluation, real-participant studies and live-model rehearsal
have not been newly completed. The final #329 head passed backend, frontend,
migrations, docs, compose and knowledge-record before merge
([CI run](https://github.com/akane321/MealCraft/actions/runs/40197542323)). The initial
container failure was a missing deliberately disabled script; packaging and root
resolution were corrected without weakening its refusal tests or enabling paid
calls. This is scoped integration evidence, not full live-provider or final-product
acceptance. Chat-based confirmation of a pending preview is accepted design only;
that new behavior has not been implemented.

### Historical integration snapshot (#302-#325, 2026-10-23)


Merged since the last snapshot, each with its paired knowledge record:

- #302: the shared-dish model (ADR-0071): each member's own allergens, diets and
  foods they will not eat, a covered plate for every member home at every lunch
  and dinner, and dish servings for the members home who can eat it.
- #303: the isolated Sprint 2 held-out authoring toolkit (guide, author brief,
  freeze procedure, schema and format checker); it holds no questions.
- #304: offline planning algorithm comparisons (shared objective, greedy, GRASP,
  local search, simulated annealing, experimental beam, exhaustive and CP-SAT
  references) with developer reports; the product algorithm is unchanged.
- #305: `vue-tsc` 3.3.13 and a typed kitchen summary.
- #306: shared-dish variety restored, a last bounded widening step so no meal is
  left empty while eligible dishes remain, and confirm runs that never fail on
  the wall budget after planning (ADR-0080).
- #307: replanning across shopping trips (one a week, ADR-0072): retained
  dishes' stock first, package surplus kept within its trip, the budget held per
  trip (ADR-0084).
- #308: recipe-tag residual repair (task 6), described under
  [Recipe-tag residual repair](#recipe-tag-residual-repair-task-6-308).
- #309: the post-search variety pass has no wall-clock deadline, and the plan
  buttons say a large household on a tight budget can take a few minutes.
- #311: evidence-based homemade staples, seasoning-meat vegetable dishes and
  protein-led sides (ADR-0082); CI timeouts raised to 60 minutes.
- #313: speed-only planning cuts removed (ADR-0080): every plan shape gets the
  readiness check, the cheapest-week search (exact to the dollar) and the
  half-household offer; the meal-combination cap stays 16,384 after a
  developer-data sweep.
- #314: maintenance batch 1 (stale docs, agent guidance, parity tests,
  owner-only CODEOWNERS).
- #317 and #318: per-trip budgets and feasibility checks in the offline
  algorithm arms, and timing comparisons qualified with their benchmark
  environment.
- #320: evidence-only role refinements for the 119-recipe review and mixed tuber
  vegetables (ADR-0085).
- #321 and #322: price-first exact references in the offline algorithm arms, and
  a minimum number of dish kinds enforced in the exact price search; the product
  planner is unchanged.
- #323: the baseline scoring layer (ingredient mapping with review flags, unknown
  allergens never safe, per-dish coverage, the product's validator) and the
  pure-LLM baseline runner (dry run by default, paid calls only with `--live`,
  US$5 per arm, ADR-0086); it supersedes #312 and #319. No paid run has been
  made.
- #324: Like, Dislike and Never again on each planned dish (ADR-0087): Never
  again is a whole-household hard filter in the planner and the validator until
  undone, any member may set or undo it, and the profile lists the dishes with
  Undo. Like and Dislike are stored only; ranking use is later work.
- #325: up to two reason tags under a dish (fits a preference, one of the
  week's cheapest mains, quick to cook), each shown only when its fact holds,
  with a facts panel (time, kcal, sodium, cost to buy); no model call.

The three dated blocks below are historical snapshots kept for their evidence
links; their timing statements predate ADR-0079 and ADR-0080.

### Historical: latest-main integration and offline rehearsal (2026-10-08)

The owner merged #244 (result-preserving fixture-ranking reuse) and #245
(demonstration workflow repairs); their paired knowledge records #102 and #103
are also merged. The latest main-push CI succeeded
([run 37652153430](https://github.com/akane321/MealCraft/actions/runs/37652153430)).
#243 remained open with changes requested and behind main at this snapshot (it was merged on 2026-10-09): merging its knowledge
record #101 did not merge that heavy-composition performance proposal.

Docker was restarted and the latest-main source was rehearsed against an
isolated PostgreSQL copy and matching production frontend, without changing
the original checkout or database. The scoped offline path passed at both
desktop sizes: English planning, groceries and daily/meal nutrition, Sunday
main-only preview/confirmation, one-dish replacement, and Chinese low-budget
refusal followed by execution of the offered budget choice. A strengthened
run also checked every overview-card daily count after asynchronous refresh.
Arithmetic and environment details are generated in the
[latest-main rehearsal report](evaluation/sprint1-demo-flow/2026-10-08/main-rehearsal.md).

This is **offline workflow QA, not complete demo acceptance or Agent capability
evaluation**. No new paid requests or protected held-out inputs were used.
OpenAI-mode and live FairPrice behavior were not revalidated; the response-time
gate remains open. Known missing recipe components remain assigned to the data
team, not fixed or filtered here. The
[earlier workflow report](evaluation/sprint1-demo-flow/2026-10-07/report.md)
preserves the previous live-model results and their limits.

### Historical: earlier WP1 price and integration slices (to 2026-10-08)

The owner merged the first WP1 price-strategy slice (#240). Candidate selection,
affordability/refusal calculations and replanning previews now explicitly use
fixture products plus reviewed release mappings, even when the requested final
basket mode is `live`. Seven focused regressions passed and fail with the
corresponding fixes removed; the scoped backend suite passed (1,586 tests,
six optional migration tests skipped). Protected held-out episodes, labels and
metrics were not used for implementation decisions, and their reports were not
changed. The paired knowledge record was merged.

The owner also merged #242: final-basket repricing refreshes only the already
selected products, with at most eight concurrent lookups and one shared
three-second deadline. Each line reports its source, lookup outcome and time;
an item without a real product ID is distinguished from a timed-out lookup.
Live repricing does not replace dishes or products to hide an over-budget total.
The exact fields and fallback semantics are in [API contracts](api-contracts.md).

The reviewed integration additionally merged #236 (planning-pool refresh
backoff), #237 (retry after a transient ingredient-override load failure), #238
(catalog-import refresh markers across processes), and #241 (planning/display
regression guards). Their required GitHub checks passed before merge. The
paired knowledge records were merged; no frontend implementation, migration
or search-policy change was added in this review.

The six-second end-to-end figure for steps 2 and 6 was the Sprint 1 demo
target (ADR-0059, amended by ADR-0061) and is historical: under ADR-0079 and
ADR-0080 planning time is reported, never a cutoff or a pass/fail gate.

### Historical: walkthrough snapshot (2026-10-06)

That snapshot added the fixes for what the 2026-10-04 real-stack walkthrough
found: a typed instruction is no longer swallowed by an open question, a whole
meal can be kept, a liquid measured in grams by one dish and millilitres by
another is bought once, catalog titles are cleaned where they are shown, a week
replaced by a newer plan is marked and shown read-only, **Plan my week** saves
the week the reply already checked, "the dishes are boring" swaps the week's
repeated dishes within its budget, and a swap takes a dish of the slot's meal that
keeps the week within its budget when one does. Every pull request must link its
knowledge record (`knowledge-record`, a required check on `main`). Its
[CI](https://github.com/akane321/MealCraft/actions/runs/37346614534) passed all
five jobs.

Each of these fixes has tests that fail without it. On the real demo stack at
this snapshot (2026-10-06, demo build, sample prices), the reply that plans a week
took 6.7–6.9 s in OpenAI mode and about 5 s in rule mode, and **Plan my week**
then showed the week in about 1 s. The held-out reports
are unchanged.

The earlier reviewed integration preserves dish locks in search and candidate packets,
and keeps the cheapest-mode flag separate from local candidate lists. A shape
change reports added checkout cost separately from how far the resulting week
exceeds the actual budget; it still requires confirmation before application.
Recorded developer experiments use the current runner, fixed registry and
worker context. Source or evidence-condition mismatches suppress numeric deltas,
and missing revision evidence is not silently treated as citable. Real
PostgreSQL concurrency/migration and Compose checks are CI evidence, not a claim
that the live full stack was run locally.

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
ADR-0046): the household's plan shape names the meals of a day and each meal's
dishes, and `MealBeamPlanner` fills every (day, meal) slot. A household that
chose no shape plans the **full default** (ADR-0070, layer 08 PR-3): breakfast,
lunch (protein main, vegetable dish, staple) and a dinner that grows with the
members present at it, counted as people rather than portions (1-2: one
protein main, a vegetable dish and soup; 3-4: two mains; 5-6: two vegetable
dishes; 7+: three mains), each lunch and dinner with a staple; the planner
(`household_slots.slot_people`), the profile editor and the user guide all
count the members home, and portions only size the dishes. Roles of the full
default admit recipes by their meal-role tag (`meal_roles`); every structured
lunch and dinner holds the hard real-meal rules in the search and the
validator (filling core, no non-meal dish, distinct
protein sources, an energy floor of 25% of the day per serving, at most one dish
moved from the default) and soft cuisine-group, deep-fry and staple-kind terms
(`data/planning/meal-structure-v1.json`, `data/recipes/cuisine-groups.json`).
Saved shapes and requests of `courses` roles plan exactly as before, so the
protocol reports are unchanged. A plan may be 1 to 14 days; past 7 days it shops
twice (before day 1 and day 8, the budget per trip), and with household rules on
a perishable dish is cooked within 3 days of its trip and a recipe needing
missing equipment is never planned. Turning the perishable rule on for every
household block is an intended change for existing households: the
[household-rules report](evaluation/household-rules/latest.md)'s week with the
block now buys S$171.75 instead of S$186.20, because nine of its fourteen
meals changed so that its salmon, tuna and spinach dishes are cooked within 3
days of the trip (with the window set to 14 days the report is byte-identical
to the one before PR-3). The
[full-default report](evaluation/full-default/latest.md) plans five fixed
households (one of seven people on under five portions, whose dinners twice use
the one allowed move) and lists every meal; it fails when any case refuses, and
works out dish counts, people present and equipment itself rather than through
the planner's helpers. Its [timing](evaluation/full-default/timing.md) records
the machine, code revision and repeated warm timings, reads each case against
the ADR-0079 guidance (a simple request within about 4 s, a complex one up to
about 60 s) as descriptive reporting, not a pass/fail test or a planning
deadline, and gives the cause of every case past the quick figure. The owner's
direction (ADR-0080) forbids trading quality or simplifying the workflow for
speed; a slow completed plan must not become an error. The plan buttons on the
home and household pages say a large household on a tight budget can take a few
minutes (the slowest report case, six-tight-budget, takes about 2.3 minutes on
the development machine; the meal-combination cap that bounds a meal's search is
a search-breadth parameter, 16,384, calibrated by plan quality on developer data
in [the cap sweep](evaluation/combination-cap-sweep/README.md)); nothing on the way times out first (the browser request has no time
limit and an agent run's wall budget of 120 s is checked only before the
planner starts, not on records written after it returns, ADR-0080 section 3).
Deferred: adding a vegetable dish when
vegetables fall short (no per-meal or per-day vegetable intake measure yet; the
dish-level vegetable-led share exists, ADR-0054/0082), CP-SAT for structured meals, day references 8-14 in the
conversation, and a curated plain Chinese steamed rice (the release has none). `PLANNING_CAPABILITY`
defaults to `full`; `mvp` (one dinner dish a day) remains for reproducing the
recorded evaluations. The candidate recipes are kept in memory, loaded at
startup and again in the background every two and a half minutes, so none is
older than five minutes (`PLANNING_POOL_CACHE_SECONDS`). The week the
conversation's readiness check finds is kept for that exact request while the
pool is current, and **Plan my week** saves it without searching again. Response times on
the real stack are recorded in dated reports, the latest being the
[2026-10-17 demo-path timing](evaluation/sprint1-demo-flow/2026-10-17/timing.md)
(rule parser only); earlier local Docker timings are historical.

### Recipe-tag residual repair (task 6, #308)

The follow-up rules recognise listed flatbread/wrap carriers, require both a
grain/bowl title and corresponding listed grain in the existing 5–15% grey
range, and distinguish protein-led fillings from cheese-led fillings and
toppings. A pizza listing only batter is a component, not a completed main.
No ingredient, amount or nutrition value is added. The generated
[tag report](../data-engineering/docs/recipe-tags-v1-report.md) is the source
for coverage; the original audit packet is unchanged. Unreviewed critical model
fields retain their values, provenance and gate even if a new rule could
classify the recipe. The swap no-repeat check and full-default diagnostic
reject unknown sources rather than treating them as a known empty set.
No model batch is claimed to have passed human review.

Of ADR-0033's packets, P1 (product path), P2 ([conflict explanations](design/planning-conflict-explanation.md))
and P4 ([nutrition scope](design/planning-nutrition-scope.md)) are wired into the product.
P3 ([diversity rules](design/planning-diversity.md)) and P5 (mixed shopping) exist
as code but are not on the product path. P5, P6 and P7 also have offline modules
that the product path does not call: `purchasing_comparison.py` and
`mixed_purchase_handoff.py` (P5, a fixed-menu purchasing comparison and a mixed
basket handoff, #182), `fixed_menu_refresh.py` (P6, repricing a confirmed fixed
menu against a new product snapshot and checking local replan invariants, #183),
and `feedback_ranking.py` and `theme_parameters.py` (P7, default off, #184), all
under `backend/app/planning/`. P8 developer diagnostics are executable: component
ablations, independent-gate comparisons, purchasing, feedback and theme
experiments, with a developer-suite runner. See
[Planning developer experiments](design/planning-developer-experiments.md).
These offline modules are not evidence that every component is on the product
path, and they do not replace a fresh independent final comparison.

## Verified Product Baseline

| Area | Verified behaviour | Important boundary |
| --- | --- | --- |
| Full-stack environment | FastAPI, PostgreSQL, Nuxt, Docker Compose, migrations, catalog import, and CI (which also lints and tests `data-engineering`) | Local development baseline, not production deployment evidence |
| Household profile | One shared profile, member servings and safety constraints, shared defaults, immutable versions, profile-linked plans. Members carry an age group, sex, activity and goal, and their portions are either Auto or a set decimal; Auto is the HPB energy need (`data/nutrition/hpb-reference-v1.json`). Who-is-home and per-meal cooking-time rules are read from one sentence by the model, with a rule-based fallback, and stored only after the household confirms the restatement. Each meal is cooked for the members home at that meal, with per-dish servings stored, and each meal keeps its own time limit. 164 pantry basics (`data/ingredients/basic-seasonings-v2.json`: the 13 basic seasonings, rice, vinegars, small-amount sauces and condiments, spices, dried herbs, stock cubes, starches and flours, by the owner's decision of 2026-10-29) are assumed at home and left off the shopping list and unpriced unless marked as run out, and a dish made only of them buys nothing; the list note gives counts by category; the profile page groups them in collapsed categories with a filter and a count of items marked; allergen checks still read them. An opt-in daily sodium cap per person is a hard per-day band, pro-rated by the meals planned. The [household-rules report](evaluation/household-rules/latest.md) plans one fixed household with and without these rules, and the [shared-dish report](evaluation/shared-dish/latest.md) plans ten fixed households with the old merged union and with the shared-dish model (a dish served when a member home can eat it, each dish cooked for the members who can eat it, a `not_for` list on each dish naming the members who cannot). Each ingredient carries an allergen list; an allergen outside the checked vocabulary (`data/ingredients/allergen-vocabulary.json`) excludes every recipe rather than none, and the profile offers only allergens the catalog can check | Does not generate separate dishes for each member: a dish may be served when at least one member home can eat it, every member home for a lunch or dinner is covered (a filling core, a vegetable dish they can eat when the meal has one, and their own energy floor), every other meal leaves nobody at it with nothing they can eat, and a request no plan can cover for every member is refused, naming who could not be covered, with no allergen, diet or exclusion relaxed and no extra dish cooked. Allergens are still avoided by the whole household unless a member marks one as only theirs on the profile page. Allergen labels are rule-derived from ingredient data, not verified against products. HPB publishes no protein table by age and no child sodium limit, so those are not used. The protocol and workbench reports send no household rules |
| Identity, sessions and tenancy | Argon2id credentials with upgrade-on-login, atomic account and default-household registration, login lockout, digest-only opaque sessions, per-session CSRF, current-actor lookup, session listing, logout and per-device revocation. Private Profile, Plan, Dashboard, Agent, Replanning and Shopping workflows require an active authenticated household; private ownership is non-null, repository queries are household-scoped, cross-household identifiers resolve as not found, and the browser has registration and login flows. Private routes authorize each action through one `HouseholdAction` dependency (`VIEW`, `EDIT_PROFILE`, `CREATE_PLAN`, `CHECK_IN`) in the order authentication, active household, action, CSRF; unknown roles are denied | No member-management or household-deletion routes exist yet, so `MANAGE_MEMBERS` and `DELETE_HOUSEHOLD` are defined but unused. Member management, household collaboration, password lifecycle and account export/deletion are out of scope by the owner's decision (2026-09-26, no deployment; ADR-0051) |
| Recipe catalog | The curated catalog and the versioned v2.2 release are imported idempotently as the runtime catalog; its current composition is owned by the [data handoff](data/README.md) and the linked release quality report | Coverage and review limitations are recorded with the release rather than duplicated here |
| Data engineering | Independent `data-engineering/` pipeline with frozen schema v1, a four-condition release gate, and release v1.1 containing 9,282 recipes and 465 canonical ingredients. Deterministic derived dietary tags cover vegetarian (5,625), gluten-free (4,507), dairy-free (3,602) and vegan (1,030) recipes. A first nutrition-mapping pass matches the curated ingredient set (533 entries) against USDA Foundation Foods, SR Legacy and FNDDS with recorded evidence: 213 `mapped`, 209 `needs_review`, 111 unresolved ([progress report](../data-engineering/docs/task-b-nutrition-mapping-progress.md)). Release v2 (decision ADR-0030) is built: all three enrichment packets are complete (838 ingredient forms, 12,333 recipes), and the build cuts 9,048 released recipes over 29 cuisines with a per-serving energy median of 327 kcal ([quality report](../data-engineering/data/release/v2/quality_report.md), [attribution](../data-engineering/data/release/v2/ATTRIBUTION.md)). Part C was re-enriched item by item on 2026-09-21, replacing the constant fill; the fixed-seed sampled audit, re-judged for part C, accepted 35 of 39 recipes (5 corrections recorded) and 19 of 19 ingredients ([verdicts](../data-engineering/docs/v2-sampled-audit.json)). Release v1 is deleted as ADR-0030 requires; v1.1 remains the source | The re-audit of part C was done by the same producer family (Claude) that re-enriched it, so it is not an independent review. Real course labels now bind the per-bucket side/dessert caps, which is why fewer recipes are released than before. Release v2.1 carries the checks v2 lacked: 220 recipes whose steps use an unlisted allergen food (some RecipeNLG sources list only part of a dish) are dropped after a per-recipe review, ten ingredients carry owner-confirmed stricter allergens, and fish or shellfish rules out vegetarian and vegan ([quality report](../data-engineering/data/release/v2.1/quality_report.md)); a 300-recipe sample the check did not flag found one miss. The owner's fixed-seed audit of 40 review decisions ([audit](../data-engineering/docs/completeness-v2.1-sampled-audit.json)) accepted all 25 kept recipes, 9 of 10 dropped ones and all 5 unflagged ones; the one correction (a listed egg substitute read as a missing egg) keeps a recipe the next release restores. It is imported beside the curated recipes (`python -m app.data.import_release_v2`, run at compose start; see [Data](data/README.md)): 8,967 recipes, upgrading v2 rows in place. Recommendations admit the courses selected by the household's configured roles. Composed requests keep up to 500 recommendations per course before the role-aware ranked/cheap/family-diverse planning packet; one-dish requests retain the global limit. Locked dishes are preserved in that packet. Release ingredients are priced through a FairPrice mapping captured and proposed on 2026-09-21 (707 ingredients, 563 mapped, 142 unavailable, water and ice not purchased; mappings under confidence 0.6 are left unpriced), the legacy main/soup subset had 4,556 priceable recipes out of 5,680. That historical count is not coverage of all currently supported role courses; a new all-role count has not been recorded. The mapping is AI-proposed; the owner's fixed-seed review of 40 ingredients accepted all 40, and four product choices its notes identified as wrong were removed ([review](../data-engineering/docs/fairprice-v2-sampled-review.json)). Release v2.2 (v2.1 with whole-item and container unit weights corrected, 2026-10-23; [quality report](../data-engineering/data/release/v2.2/quality_report.md)) is the runtime release: per-serving nutrition is computed (ingredient grams × per-100 g values), and release recipes whose numbers show a lost main line (a main under 150 kcal a serving, or a title protein it does not list; 244 recipes, decision ADR-0045) stay browsable but are never planned. Cuisine, meal types and difficulty are filled by the v2 enrichment and imported (agent-labelled, not reviewed; decision ADR-0038 corrects an earlier statement that they were empty), and the planner reads meal types as meal fit: a slot takes only dishes of its own meal when enough fit (ADR-0044 section 1, ADR-0046 section 3), and otherwise prefers them; methods and equipment are not in the release. Course labels decide which dish role a recipe may fill (decision ADR-0036), so the owner audited a fixed-seed sample of 80, ten per role course ([audit](../data-engineering/docs/course-v2.1-sampled-audit.json)): 78 accepted, and two desserts that are cookies corrected to `baked_good`, a correction the next release applies. Derived dietary tags are not reviewed gold labels, and allergen labels remain deterministic-rule-only |
| Home surface | `/` keeps the film entry, then opens the kitchen-table workspace (decision ADR-0043, amending ADR-0026): navigation, recent conversations and the household card on the left; the chat on the Agent session API in the centre (week card, swap comparison, clarification, confirmation, replan preview and confirm/discard); "Today" (the next meal to cook), the week by day and meal, the shopping list with budget and nutrition on the right (ADR-0048). The shopping list previews as a sheet and exports through print-to-PDF; nutrition and recipe sheets open over the workspace; applied replan events are listed with the meals (`ChangeLog.vue`). The week is shown by day and meal, with "Today"/"Next up" and nutrition per meal and per day; each dish still to cook offers Swap, Keep, Skip and Can't buy, which put the request into the chat for the usual preview. Other pages are `/login`, `/profile` (with a meals-and-dishes editor), `/browse` (recipe search by title and course; FairPrice product search, labelled "Sample prices", "FairPrice prices from <date>" or "FairPrice prices now" per ADR-0026 section 4), `/history` (past weeks by day and meal) and `/system`, all linked from the rail or the page header; desktop only (ADR-0010): no horizontal scroll at 1440 and at the 1280×720 minimum. The rail's recent list keeps each row's height and scrolls at 1280×720; the change log names the dish's own day and meal; the nutrition sheet lists meals by day, then breakfast, lunch and dinner, with a Meal column; a printed list is light on every page; a lock preview offers Keep it locked / Cancel. A week that a newer plan covers on any of its days is marked "Replaced by a newer plan" in `/history`, and its conversation shows it read-only with a link to the current week. `/system` is "Service status" in household words (what works, and which prices the list uses); version, environment, API docs, the raw health check and the `/ops` link show only to administrators. Recipe titles and preparation notes are cleaned where they are shown (API responses and replies), while the catalog, search and matching keep the catalog's text (ADR-0057 section 3); the interface stays English (ADR-0057 section 2) | A signed-in walkthrough on the real stack was done on 2026-09-26 and its fixes recorded (decision ADR-0045). Tutorials are live YouTube results when a key is configured; named errors fall back to the sample set. Administrators have a separate console at `/ops`; see Operations and maintainability |
| Agent | Persistent household-scoped sessions, bilingual scope isolation, structured constraints, typed clarification, confirmation, bounded tool authorization, grounded claims, Agent-driven replanning, and synchronous per-action `AgentRun` with authenticated actor/household provenance, input digests, explicit deadlines and budgets, durable checkpoints, ordered tool receipts, idempotent replay and run list/detail/cancel APIs. While a question is open, only a clear answer (a tap, or a reply that is only yes, no or just this week) answers it; any other typed instruction is handled as a new request, and an open "should new weeks plan this way?" question then lapses as this week only. A greeting or a question about the plan is recorded as `committed`, a question back as `needs_clarification`, and `degraded` only for a model fallback, a turn the scope gate turned away, or a replan the planner refused (`REPLAN_REFUSED`). An impossible weekly budget is refused with what it comes to a person a meal and the cheapest week found; fewer people are offered only when their own week costs less | Default parser is deterministic fixture mode; `AGENT_PARSER_PROVIDER=openai` uses the live model with the same templated replies (it failed to build its vocabulary against the database until a fix on 2026-09-26). Plan confirmation is not yet bound to a specific preview: `POST /api/agent/sessions/{id}/confirm` takes no preview id, context version or expiry, saves in one call the week the readiness check found for that exact request (or plans one when none is kept), and records the generation step as a preview although it already persists the plan; ADR-0016's matched, unexpired confirmation is target work. Runs are synchronous: asynchronous pause/resume/retry, external-tool evidence, natural-language claim extraction and formal live-model evidence are deferred |
| Weekly planning | A week of days × meals (ADR-0046), persisted one entry per dish, plus independently callable Planning v2 constraint compilation, bounded Beam Search, conservative nutrition bounds, independent shopping/budget recomputation, and a small exhaustive oracle. Weekly budgets are compared in whole cents on both sides (ADR-0021). A slot takes only dishes of its own meal type when at least as many fit as the planner keeps per role, and falls back to preferring them only when the catalog runs short (meal fit, ADR-0044 section 1, ADR-0046 section 3); the CP-SAT package oracle's tests run in CI. A meal can hold several dishes (ADR-0036): dish roles such as main, vegetable and optional soup, each cooked at a portion share (1.0, 0.75/0.5, 0.6/0.4, 0.5/0.35) with a one-cook meal-time estimate, validated dish by dish and meal by meal and planned by a meal beam search; the API stores dishes per meal, swaps one dish, checks in a whole meal and has the agent ask which dish. Since ADR-0046 a week holds the meals the household chose, each with its own composition of up to six dishes (presets per meal, or a custom mix such as two mains, a vegetable and a soup), set in the profile and changeable in the conversation ("also plan lunch", "add a soup on Friday", "no side dish tonight"; see Replanning); variety is kept across the whole week and meal fit applies to every slot. Among composed weeks that pass validation, the fewest empty optional dishes come first, then the most distinct dishes, then the fewest times the most-served dish comes, then the fewest of one kind: a week with its optional dishes filled is chosen before one with a dish or two more of variety (owner decision 2026-10-02, amending ADR-0045's most varied first for composed weeks). Under a weekly budget a composed week is drawn from the best 500 recommendations of each course (not of all courses together), half of each kind of dish's candidates are the cheapest, one of each dish family comes before a second, and the most varied and the cheapest weeks found are then improved one dish at a time within the budget, so a new dish sharing packages the week already buys replaces a repeat ("菜很单调", 2026-10-02 walkthrough: 12 distinct dishes of 21 with one soup five times became 17 with none more than twice, S$100) A plan may be shorter than a week in the chat (owner decision 2026-10-29): "one dinner for 1 person tomorrow", "dinner tonight", "today", "this weekend", "the next 3 days" (and the Chinese forms) plan only those days and meals, with the shopping list and budget of just them; an amount stated for the plan is its budget, else a saved weekly budget is pro-rated by planned meals, and the reply says so. A named day outside such a plan is answered "not in this plan", and an older plan is replaced only when newer plans together cover every one of its (date, meal) places, so a dinner planned inside a week leaves the week current; the plans list and the nutrition dashboard carry `day_count`. The chat part is covered by `backend/tests/test_short_plans.py`. | The meal-day-week planner is evaluated on 21 developer episodes ([protocol](evaluation/protocol-v3-meal-day-week.md), [report](evaluation/v3-meal-day-week/dev/latest.md)): 21 of 21, after fixes found on them, so these are diagnostics, not evidence. On the frozen held-out set, run 1 (before any change) scored 44 of 60; run 2, a protocol v3.1 diagnostic after looking, 57 of 60 with no regression ([findings](evaluation/v3-meal-day-week/heldout/findings.md)). A 60-episode held-out set is frozen ([set](../data/evaluation/heldout/v3-meal-day-week/set-manifest.json)): drafted in a sealed packet and revised over three owner review rounds. The product path then ran once on it at the earlier code revision recorded in [run 1](evaluation/v3-meal-day-week/heldout/run-1.json), not current `main`, before any fixes chosen from it ([findings](evaluation/v3-meal-day-week/heldout/findings.md)): **44 of 60**. Meals per day, compositions and safety held on every episode (27/27, the 13 infeasible ones refused with a reason); budgets 7/9 and per-day targets 5/7, where the composed-meal search completed no week under the limit; variety 4/5, where a no-repeat request was not yet a hard rule (it now is: `max_uses_per_recipe`, #194); shape changes by asking 1/12, where the rule reader took one day of several or did not read a verb placed after the meal. Fixes are developed on developer data only. Because the fixes were chosen after reading run 1, and the shape-change reader took held-out wording (#188), the v3 held-out set is spent for the shape-change reader: later runs are protocol v3.1 diagnostics, reported beside run 1 and never as a held-out score (ADR-0049; [protocol v3.1](evaluation/protocol-v3-meal-day-week.md#protocol-v31)). At a tight budget with a main and a vegetable every night, dishes repeat. Variety across synthetic shapes, household sizes and budgets, counted by recipe and by dish kind (differently named fried rices are one kind), is in the [variety sweep](evaluation/v3-meal-day-week/variety-sweep/latest.md), a developer diagnostic. They are evaluated under protocol v2-multidish on a frozen 40-episode held-out set ([report](evaluation/v2-multidish/heldout/latest.md), [findings](evaluation/v2-multidish/heldout/findings.md)): with gold constraints, CP-SAT solved 40 of 40 and the beam 34 in the first run, failing exactly the six episodes that state a weekly budget, because the beam never scored cost and the validator then rejected its plans; the beam now prices a partial plan in whole packages and holds the cheapest candidates in reach, developed on four new developer episodes only, and a second run of the same set has both at 40 of 40 (both runs are reported, and the beam's variety fell from 11.9 to 9.9 distinct recipes). The rule-parser arms reach 17 to 21 of 40, mostly by answering with a plan where the request is infeasible or needs a question. The live-model arms have run on the owner's key (`gpt-5.4-mini`, a token cap per run). Every failure of the arms where the model reads and a solver plans is a misreading of the request, never the solver: A (beam) and B (CP-SAT) fail the same episodes in every pass. Giving the model the catalog's vocabulary, developed on developer episodes, took them from 31-32 to 37-38 of 40 over four passes; the model planning unaided (D) stays at 14-18. The set has now been looked at four times, so these are checks, not unseen evidence. A recipe line that allows either of two ingredients ("butter or margarine") is cooked, per household, with its first option the household can eat and the planner can buy, so a no-butter household keeps those 205 recipes; the choice drives eligibility, cost and the shopping list alike. The product agent parser now gets the same vocabulary (the database's ingredient ids and the checked allergens); a word it cannot match is asked about instead of being applied as a constraint that matches nothing. That question now offers up to four catalog ingredients as one-tap choices, an exact name or model-generated other name first and then the closest by embedding (ADR-0041); nothing is applied until the household picks, and the pick lands in the field the word came from. On a 63-term developer set written by the same session that tuned it, an acceptable ingredient was among the four for 56 of 62 terms (spelling alone: 26); on a frozen held-out set written by a teammate it was 15 of 21 unseen terms (spelling: 11), every miss a short Chinese word ([results](evaluation/embedding-heldout-results.md)). When a household asks to replace a meal and says what they want instead ("fish instead", "来点辣的"), the replacement is now chosen, among the candidates that already hold every constraint, by embedding similarity to what was described plus shared words (ADR-0042); with nothing described, or without the live model, the swap orders by score as before. On 20 developer requests checked on catalog facts it picked what was asked for in 80% of trials against 10% before; on 21 frozen held-out requests written by a teammate, 69% against 8% (shared words alone: 50%), weakest on Chinese and abstract requests ([results](evaluation/embedding-heldout-results.md)). Catalog Chinese names (`data/ingredients/aliases-zh-v1.json`) and English glosses for Chinese swap words were then developed on new Chinese developer sets (`data/evaluation/agent/*-zh-dev.json`; developer-only: ingredient top-4 26/57 to 58/58 after fitting, swaps 55% to 89% with the model); a new Chinese held-out set awaits a teammate author ([prompt](evaluation/chinese-heldout-prompt.md)). Excluded ingredients are expanded by the [ingredient hierarchy](design/ingredient-hierarchy.md) (ADR-0039) before eligibility is checked, in the recommendation engine and in the planning product path, so "no tofu" also removes `firm_tofu` and "no pork" removes bacon; the agent's vocabulary offers hierarchy groups such as `group:alcohol`. All 716 catalog ingredients are decided (15 curated-only, 320 animal, drink and prepared-food, 381 plant and pantry), with groups for alcohol and the onion-garlic family. The product path is described under [Planning product path](#planning-product-path); Beam parameters are untuned and the oracle proves results only for small packets under the fixed shopping policy |
| FairPrice | Live lookup verified against the live site, normalized results, 15-minute PostgreSQL cache, and a live → saved-snapshot → fixture degradation chain with a warning and a `degraded` trace. An empty live result is a typed `no_match`: the ingredient stays unpriced instead of borrowing sample prices. A test generates a live-priced weekly plan with every FairPrice request failing and still gets a Shopping List | The disconnected run is covered by an automated test with the network stubbed out, not yet by a demonstration on a physically disconnected machine. **Cart:** the groceries tab's FairPrice cart panel shows the person's real FairPrice cart inside MealCraft (pictures, unit prices, quantities, fees and total), adds the trip's re-checked FairPrice lines, changes quantities and removes items through the MealCraft browser extension, and leaves only checkout and payment to FairPrice ([design](design/fairprice-cart.md)). Reading and writing the cart are confirmed on the owner's FairPrice account (2026-10-30) |
| Halal | A household's `requires_halal` switch, or "halal"/"清真" in chat (with an offer to save it), plans only halal dishes. A meat line, and any ingredient that is doubtful or a person could not settle without the product (soy sauce, vinegar, cheese, bread, gelatin, sausage ...), is bought only as a product FairPrice marks Halal; such a pantry basic is bought, not assumed at home (ADR-0104, ADR-0108, [design](design/halal.md)). 716 ingredient labels by rule, then a person's review; unknown is never halal. Swaps, can't-buy replans and new weeks keep it; the validator re-checks it; the scorer fails unknown. 4792 of 8997 shared recipes are plannable for a halal household ([pool](evaluation/halal-pool/latest.md)) | A person reviewed 255 labels on 2026-10-31: 114 kept, 141 undetermined (now needing a Halal-marked product), none shown wrong; the 28 the rules left uncertain need one too. 60 of the 207 ingredients that need one have a Halal-marked snapshot product; mayonnaise, ketchup, mustard, hoisin and rice vinegar have none, so their dishes are not planned for a halal household. Certification is FairPrice's attribute only (no MUIS list); snapshot facts were observed once (2026-10-31). No halal substitute for alcohol ingredients |
| Shopping List | Aggregated demand, known-quantity deduction, package rounding, price and budget results. A liquid measured in grams by one dish and millilitres by another is one line bought by weight from one product, using densities sourced from the release's cup weights (`backend/app/data/units.py`); planning, the weekly list, replanning and pantry deduction use the same rule | Unknown pantry quantities are never deducted. Densities exist for 14 liquids (milk, cream, yogurt, coconut milk, six oils, soy sauce, three broths); any other ingredient measured in two units stays one line per unit |
| Check-in and Dashboard | Planned/completed/skipped states, completed cumulative nutrition KPIs and curves, current-plan comparison, labelled daily detail, completion coverage | Cumulative actuals count completed MealCraft dishes only; planned rows are previews and skipped rows are not counted |
| Replanning | Preview, confirm/discard, plan revision, event history, local meal changes, price and Shopping List deltas. Shape changes by request (ADR-0046 section 2): add or drop a meal for the rest of the week, change a meal's dishes, or add or take away a dish in one meal. Only the affected meals are planned again, with the budget the rest of the week leaves at the checkout (whole packages); when nothing that keeps the meal's present dishes fits it, the change is still offered with those dishes kept (a week is planned to use most of its budget, so an addition to a budgeted week usually goes over it, even where replacing those dishes would fit), planned as cheaply as the planner finds with the rest of the week (a dish the week already has counts as a repeat, and a package both use is bought once), and the preview and the reply say how far over the weekly budget it takes the week (only for a change that costs more), for the household to confirm or discard, as with a swap (owner decision 2026-10-02; a new week keeps its budget as a hard limit). A household's cap on uses ("no dish twice") holds across the whole week. Adding a dish to a meal, on one day or on every day ("dinners with a soup"), keeps the dishes each day has in their places (also a second dish of the same kind, such as another soup, read from the dishes that day has) and chooses only the new one, and taking a dish away keeps the others at their larger share; cooked and locked meals never change. A week-wide change applies to this week, and the assistant then asks whether new weeks should plan the same way, saving it to the profile only on a yes. "The dishes are boring" (菜很单调) swaps the week's repeated dishes in one preview (ADR-0057 section 1): of a dish served more than once the first (or a cooked or locked one) stays, and each other one still to cook takes a dish of its role the week does not serve that keeps the week within its budget at the checkout, one dish a meal per preview; when none fits, the reply says how much more the closest swap needs. A swap or can't-buy replacement takes a dish of the slot's meal when one fits, and the first in its order that keeps the week within its budget (or no further over it), else the one least over, with its overage; a swap that says what it wants chooses so among the ten candidates most like the request. Over the budget, the cheaper weeks found also swap repeats for different dishes before one is chosen. "Don't change Monday's dinner" keeps every dish of that meal in one preview, and naming a dish keeps only that dish. Adding a dish of a kind the meal already has asks first whether to add another or swap it. A skip preview says what it takes off the groceries, or which dishes still need those packages | Shape changes are read by rules (English and Chinese), not by the model. A change that is neither an addition nor a removal (a meal's dishes changed) plans those meals again from scratch. Over the budget each search prices the new dishes on their own; only the choice between its two plans counts the packages the rest of the week buys. Broader preference and stress-event semantics remain partial |
| Evaluation | Developer, held-out, Agent, scope and grounding fixtures; greedy and Strong Rule-only references; matched-information v2 developer packets; failure registry; state and 1280×720 desktop browser tests | Visible orchestration/v2 packets validate contracts but are not independent held-out comparative evidence |

## Recorded Evaluation Snapshot

### Datasets

- 20 developer planning scenarios;
- 40 held-out planning scenarios: 36 feasible and 4 infeasible;
- 24 offline Agent fixtures;
- 36 bilingual scope developer cases and 12 typed grounding developer cases;
- two fully covered, leakage-resistant matched-information Evaluation v2 developer packets;
- 30 curated recipes and 34 normalized ingredients in the recorded catalog, plus 8,967 release v2.2 recipes imported beside them (slugs prefixed `v2-`).

### Archived held-out v2 authoring progress

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

The earlier v2 authoring format above required an explicit per-slot or average
scope and did not support daily totals. This is historical, not the current
product/scorer limit: v3 supports `per_day`, per-slot and horizon-average targets
under its versioned protocol. Nutrition is always recomputed from frozen facts.

Episodes may be drafted by an AI agent working from a sealed packet containing
the catalogs, authoring rules and checker but no implementation of any system
under test. Each draft is read and accepted by an eligible human contributor,
whose role is what `authored_by` records.

### Historical v1 planner comparison

The following table is the earlier condition attested by `conditions-v1.json`,
not a restatement of the newly generated workbench. For the current generated
condition use [latest.md](evaluation/workbench/latest.md); its input digests and
values may differ. Historical reports are not silently rewritten to match it.

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
and recorded failure cases (`0` each). In that historical condition, the only
separation is mean distinct recipes. For exact current values use the linked
generated report. A primary metric that saturates for both systems
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
| Unified planning workspace | Partial | The kitchen-table workspace joins conversation, days × meals planning with editable per-meal composition, "Today", tutorial, recipe detail, nutrition detail, whole-meal check-in, Swap/Keep/Skip/Can't buy entry points, shopping-list export and applied replan history; `/browse`, `/history` and `/system` are linked from it (ADR-0048); the real-backend walkthrough is recorded (ADR-0045). The scoped offline demonstration path is now repeatable (see the latest-main rehearsal above); full live-model, price and timing acceptance remains open |
| Authentication and user separation | Partial | Authentication, non-null household ownership, household-scoped repositories, cross-household denial, per-action household authorization and browser registration/login are merged. Member-management routes, a wider isolation matrix, household collaboration, password lifecycle and account export/deletion are out of scope by owner decision (ADR-0051) |
| High-dimensional recipe knowledge | Partial | Expand the catalog and complete cuisine, taste, method, equipment, difficulty, nutrition provenance, instruction, source, and media fields |
| Verified recipe benchmark | Partial | Import a gated, enriched data release into the runtime catalog; the recipe count is set by what passes the release gate, not by a fixed range (decision ADR-0024) |
| Validated web-recipe supplementation | Partial | Typed search/extraction, normalization, reviewed ingredient mapping, source policy, household-private persistence, admission checks, trace inspection and catalog fallback are implemented; see [API contracts](api-contracts.md). Independent human accuracy, live extraction evidence, unknown-ingredient enrichment and promotion into the shared catalog remain open; this is not demonstrated full release-gate parity |
| Semantic preference retrieval | Target | Combine semantic matching with strict metadata filtering and evaluate its incremental value |
| Recipe execution side panel | Partial | The recipe sheet shows ingredients, allergen labels and steps, and the plan panel's "Today" view carries the Top-1 tutorial for the next meal (ADR-0048). Remaining: attributes, provenance and a tutorial per dish beyond the sample set |
| Final-scope planning and validation | Partial | Constraint compilation, bounded Beam Search, conservative bounds, independent shopping/budget validation and a small exhaustive oracle are executable. The integration and its deepenings are specified as eight packets in [Planning and Validation v2](design/planning-validation-v2.md) (decision ADR-0033). The engine and the independent validator are wired into the product path (P1), as are conflict explanations (P2) and nutrition scope (P4). Remaining: explain infeasibility with a minimal conflicting set and a numeric relaxation, bound variety against ingredient overlap, compile nutrition scope, purchase across the whole slot set, replan with minimal perturbation, add a reorder-only learned ranking that ships off, and add integrated-product evidence to the existing developer ablations |
| Nutrition elastic policy | Partial | Complete source-aware target deviation, lower-sodium/lower-sugar policy, tolerance, missing-data behaviour, and dedicated evaluation |
| Grocery grounding robustness | Partial | Measure live/cache/fixture degradation, mapping quality, package parsing, and source freshness |
| Dynamic replanning | Partial | Add broader event semantics, temporary versus persistent preference handling, disruption metrics, and Shopping List consistency stress tests |
| Agent scope, interaction and grounding | Partial | Bilingual scope/mixed-intent isolation, typed UI interaction, stale-answer guard, deny-by-default authorization, structured claim verification and synchronous durable `AgentRun` checkpoints are executable; production classifier evidence, asynchronous pause/resume/retry, the full typed tool graph, external-tool evidence and natural-language claim extraction remain target work |
| Evaluation scale | Partial | Expand toward 150-200 verified requests, a gated imported recipe release, 80-120 planning scenarios, and complete grocery coverage for benchmark demand; preserve frozen splits and digests |
| Multiple baselines | Partial | Strong Rule-only is executable; run frozen Context-matched LLM-only, Plain LLM and Human Manual comparisons only after common outputs and held-out labels are ready |
| Capability-centred Evaluation v2 | Partial | Packet compiler, coverage/leakage gates and visible developer packets are executable; the common output schema and strict-success scorer are called by the v2-multidish and v3 meal-day-week runners (`multidish_runner.py`, `meal_day_week_runner.py`); paired statistics over the recorded v2-multidish runs are reported ([paired](evaluation/v2-multidish/heldout/paired.md)), but that set was used for two fixes, so they are not pre-registered; an unseen held-out set and a human study remain open |
| User-facing quality | Partial | Typed quick clarification, cumulative-plus-daily Dashboard and the one-surface home journey passed 1280×720 Browser and Playwright acceptance. The plan panel (ADR-0043) distinguishes loading (skeleton with `aria-busy`), failed (with a working retry) and empty, and the three overlays behave as dialogs: Escape from anywhere, focus moved in and restored, Tab trapped, background locked. Remaining: degraded-state coverage beyond price provenance, and a wider accessibility pass |
| Operations and maintainability | Partial | The console at `/ops` (decision ADR-0047, amending ADR-0031): fixed admin accounts from `ADMIN_ACCOUNTS` sign in through the same login page; overview charts, task records, service health with live checks, debugging replays (agent and planning, with parser or planner overrides, compared side by side), experiments and runtime settings (a registry stored in the database, change history, developer evaluation runs and A/B), users, and catalog data (recipes, ingredient names and aliases, product mappings; allergens view only). Every change writes an audit row. The PostgreSQL worker, fenced leases, bounded retries, idempotent enqueue and cancellation are integrated, with database race tests. Remaining: additional registered business handlers and runtime settings the product does not read yet (they are labelled "Stored only" in the console) |

## Backend Capability Traceability

This compact map identifies the merged evidence behind the backend boundary and
the next incomplete control. It is a navigation aid, not a second status source.

| Capability | Merged evidence | Remaining boundary |
| --- | --- | --- |
| Account and session security | Alembic revisions `20260906_0010` and `20260908_0012`; authentication service and routes; password, session and CSRF tests | Out of scope by the owner's decision (2026-09-26, no deployment): email verification, password reset/change, rate limiting and account lifecycle are not planned |
| Household tenancy | Alembic revision `20260916_0014`; current-household route dependency; household-scoped repositories; private-route authentication and cross-household integration tests | A wider isolation matrix is out of scope by owner decision (ADR-0051); existing tests stay |
| Household authorization | `backend/app/auth/authorization.py`; action dependencies on the Profile, Plan, Check-in and Agent routes; owner/editor/member/viewer and CSRF-ordering tests in `backend/tests/test_backend_platform.py` | Member-management routes (`MANAGE_MEMBERS`) are out of scope by the owner's decision |
| Operations and Console | `OperationRun` and `AuditEvent` persistence; `/api/ops/*` routes and services; migrations `20260927_0023` (runtime settings) and `20260928_0025` (catalog edits); `backend/tests/test_operations_*.py`; the `/ops` pages | Registered handlers only; cancellation cannot roll back an already committed import |

## Current Priorities

1. The v3 held-out set is spent (ADR-0049): the second run, a protocol v3.1
   diagnostic, found no regression on what run 1 passed
   ([findings](evaluation/v3-meal-day-week/heldout/findings.md)). Its three
   remaining mechanisms (a weekday-only shape request read as every day; a budget
   week and a no-repeat week refused although feasible) were fixed on new developer
   episodes (#201, #202) and are not measured on that set. A held-out score needs a
   fresh set. Planning time has no hard limit and a slow plan never becomes an
   error (ADR-0079, ADR-0080): time is reported, never a cutoff; the latest
   real-stack measurement is the
   [2026-10-17 demo-path timing](evaluation/sprint1-demo-flow/2026-10-17/timing.md),
   rule parser only, against the earlier demo budgets (ADR-0059, ADR-0061).
2. Prepare the Sprint 1 demonstration in OpenAI parser mode with rule fallback,
   following the owner-approved skeleton at
   `MealCraft-Knowledge/operations/sprint1-work-packages/demo-skeleton.md`.
   Security and privacy hardening is out of scope (the course does not require
   deployment).
3. Complete nutrition-target and elastic-preference semantics and evidence.
4. Test FairPrice live/cache/fixture degradation against real changes.
5. Wire the remaining ADR-0033 packets (P3, and the offline P5-P7 modules) into
   the product path, then extend the implemented P8 developer diagnostics to
   the integrated path without overstating global optimality or infeasibility.
6. Extend the merged synchronous `AgentRun` into asynchronous pause/resume/retry
   with bounded external-tool adapters, then build an independent held-out
   orchestration set. The live-model arms have already run on the v2-multidish
   set (see Weekly planning), so any further live-model comparison needs a fresh,
   unseen set.
7. Expand dynamic-replanning stress cases and measure unnecessary disruption.
8. Complete the real-environment gate for the owner-approved demonstration
   skeleton. The latest-main real-backend offline rehearsal is recorded above;
   it does not establish the OpenAI/live-price gate (timing is reported only,
   ADR-0080). The existing mocked
   Playwright suite also does not establish that gate.
9. Raise the discriminating power of the held-out evaluation before the final
   comparison. Parameters may be tuned on developer data only, never on
   held-out episodes (decision ADR-0020 as amended by ADR-0029). On the current v1 set the strong Rule-only reference
   matches MealCraft on task success, hard-constraint violations and failure
   count; a saturated primary metric cannot support a superiority claim.
10. Progressively close the final-design gaps documented above rather than
    treating the current MVP as the finished product.

## Verification Boundary

This file records the last merged and verified snapshot. Before updating it:

1. inspect remote `main` and current tests;
2. distinguish implementation from roadmap;
3. update the date and commit;
4. link the relevant evidence;
5. do not describe an unmerged branch as a product capability.
