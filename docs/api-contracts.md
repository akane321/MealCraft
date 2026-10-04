# API Contracts

> Backend platform boundary: authentication now protects household-owned
> Profile, Plan, Agent, Shopping List and Dashboard data. The `/api/ops` routes
> behind the operations console at `/ops` are listed below; the console's design is
> in the [Operations Console](design/operations-console.md) (decision ADR-0047).

The system will define the following shared objects:

- UserConstraints
- Recipe
- Ingredient
- Nutrition
- FairPriceProduct
- MealPlan
- ShoppingList
- AgentSession
- AgentMessage
- HouseholdProfile
- HouseholdProfileVersion

Available endpoints:

- GET /api/health
- GET /api/info
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me
- GET /api/auth/sessions
- DELETE /api/auth/sessions/{session_id}
- GET /api/ops/overview
- GET /api/ops/overview/series
- GET /api/ops/tasks
- GET /api/ops/tasks/{kind}/{task_id}
- GET /api/ops/services
- POST /api/ops/services/{name}/check
- GET /api/ops/runs?type={run_type}&status={status}&since={timestamp}&limit={limit}
- POST /api/ops/jobs
- POST /api/ops/jobs/{run_id}/cancel
- POST /api/ops/replay/agent/{run_id}
- POST /api/ops/replay/planning/{run_id}
- GET /api/ops/replays
- GET /api/ops/replays/{replay_id}
- GET /api/ops/config
- GET /api/ops/config/history
- PUT /api/ops/config/{key}
- GET /api/ops/experiments
- GET /api/ops/experiments/compare?ids={run_a},{run_b}
- GET /api/ops/experiments/{run_id}
- POST /api/ops/experiments
- GET /api/ops/users
- GET /api/ops/users/{user_id}
- PATCH /api/ops/users/{user_id}
- DELETE /api/ops/users/{user_id}/conversations
- DELETE /api/ops/users/{user_id}/plans
- DELETE /api/ops/users/{user_id}
- GET /api/ops/data/recipes
- GET /api/ops/data/recipes/{recipe_id}
- PATCH /api/ops/data/recipes/{recipe_id}
- POST /api/ops/data/recipes/{recipe_id}/withdraw
- POST /api/ops/data/recipes/{recipe_id}/restore
- GET /api/ops/data/ingredients
- PATCH /api/ops/data/ingredients/{ingredient_id}
- GET /api/ops/data/mappings
- GET /api/ops/data-quality
- GET /api/ops/data-quality/dropped?reason={reason}&offset={offset}&limit={limit}
- PUT /api/ops/data/mappings/{ingredient}
- DELETE /api/ops/data/mappings/{ingredient}
- GET /api/recipes?limit=20&after_id={recipe_id}
- GET /api/recipes/{slug}
- GET /api/recipes/{slug}/tutorial?live={boolean}&language={language}
- POST /api/recommendations/recipes
- GET /api/products/search?q={query}&live={boolean}&refresh={boolean}
- POST /api/plans/generate
- GET /api/plans
- GET /api/plans/{plan_id}
- PATCH /api/plans/{plan_id}/entries/{entry_id}
- GET /api/plans/{plan_id}/dashboard
- POST /api/plans/{plan_id}/replan/preview
- POST /api/plans/{plan_id}/replan/{event_id}/confirm
- GET /api/plans/{plan_id}/events
- POST /api/agent/sessions
- GET /api/agent/sessions
- GET /api/agent/sessions/{session_id}
- POST /api/agent/sessions/{session_id}/messages
- POST /api/agent/sessions/{session_id}/interactions
- POST /api/agent/sessions/{session_id}/confirm
- POST /api/agent/sessions/{session_id}/replan/confirm
- POST /api/agent/sessions/{session_id}/replan/discard
- GET /api/agent/sessions/{session_id}/runs
- GET /api/agent/sessions/{session_id}/runs/{run_id}
- POST /api/agent/sessions/{session_id}/runs/{run_id}/cancel
- POST /api/household-profiles
- GET /api/household-profiles/current
- GET /api/household-profiles/{profile_id}

## Operations planning experiments

`GET /api/ops/experiments` lists historical runs and the fixed evaluation
registry. `planning-components`, `planning-final-gate` and
`planning-final-gate-composed` have `execution_mode=durable_worker`; the two
older evaluation entries remain `legacy_inline` so their execution semantics
are not mistaken for the durable path.

`POST /api/ops/experiments` accepts only an authenticated administrator
with a valid CSRF token. A durable planning request also requires
an `Idempotency-Key`, `confirm=true`, one registry name, and bounded `repeats`,
`width`, `max_expansions` and (for component ablations) `repair_rounds`.
Dataset paths and runner implementations cannot be supplied by the client.
Held-out data, arbitrary SQL and paid-provider options are not accepted.

The request creates an append-only `OperationRun` and queue audit event. The
worker records the code revision, protocol and source digest, dataset registry
key plus file and semantic SHA-256 digests, product snapshot digest, normalized
parameters and digest, seed, repeats, duration, failure mechanisms and explicit
zero paid-model usage. A retry with the same idempotency key returns the same
run; attempt fencing prevents an expired worker from replacing a completed
artifact. Planning results are developer diagnostics and are not held-out
claims.

`GET /api/ops/experiments/{run_id}` is read-only and returns the stored
case-level report plus a machine-derived reproducibility assessment. A record
is complete only when the succeeded run contains its code and parameter
digests, fixed dataset path plus file and semantic digests, runner/source,
product snapshot, explicit seed, repeats, duration, paid-usage declaration and
claim scope. Legacy rows remain inspectable but are labelled incomplete rather
than silently treated as citable. The endpoint never reads an arbitrary path;
it returns only the artifact already attached to the selected experiment row.

`GET /api/ops/experiments/compare?ids={run_a},{run_b}` compares exactly two
distinct experiment records. It reports evidence-context matches,
configuration changes, metrics and failure-mechanism counts. Numeric metric
deltas are emitted only when both runs succeeded and their complete dataset,
runner, code, product-snapshot, seed, repeat and developer-claim scope fields
match; otherwise `compatible=false` explains the mismatch and every delta is
null. This is a developer diagnostic comparison, not the separate held-out
final-comparison action.
- PUT /api/household-profiles/{profile_id}
- GET /api/household-profiles/{profile_id}/versions
- POST /api/household-profiles/{profile_id}/plans
- POST /api/household-profiles/{profile_id}/plans/{plan_id}/replan

## Authentication

`POST /api/auth/register` creates an active `User`, Argon2id credential,
default `Household`, owner membership and opaque browser session in one
transaction. `POST /api/auth/login` verifies the maintained Argon2id policy,
upgrades an older valid hash opportunistically, applies bounded failed-login
locking, records the successful login and issues a separate device session.

The raw session token is returned only as an `HttpOnly`, `SameSite=Lax` cookie.
PostgreSQL stores its SHA-256 digest. Secure cookies are automatic outside the
development and test environments. A separate browser-readable CSRF token is
returned in the response and cookie while only its digest is stored; logout
and device revocation require the matching `X-CSRF-Token` header.

`GET /api/auth/me` resolves the active user and first active household
membership. `GET /api/auth/sessions` lists only the caller's unexpired,
non-revoked sessions. `DELETE /api/auth/sessions/{session_id}` can revoke only
a session owned by the current user, and revoking the current session clears
both cookies. Missing, expired, revoked and suspended-user sessions fail
closed. Login failures use the same response for unknown email and incorrect
password.

Household Profile, Plan and Agent endpoints require an authenticated session and
an active household membership. Their root records carry non-null
`household_id` ownership, and repositories include that household in every
lookup. A resource owned by another household is reported as HTTP 404 rather
than revealing its existence. Mutating household routes also require the
session's `X-CSRF-Token`; public catalog and recommendation reads remain
available without a session.

Private routes authorize through one parameterized `HouseholdAction`
dependency. Reads require `VIEW`; profile creation and updates require
`EDIT_PROFILE`; plan generation, replanning and Agent-session mutations require
`CREATE_PLAN`; meal-entry status changes require `CHECK_IN`. The current role
matrix is:

| Household role | View | Edit profile | Create or replan | Check in | Manage members |
| --- | ---: | ---: | ---: | ---: | ---: |
| owner | yes | yes | yes | yes | yes |
| editor | yes | yes | yes | yes | no |
| member | yes | no | yes | yes | no |
| viewer | yes | no | no | no | no |

Authorization failures follow one stable boundary:

- missing, expired or revoked authentication returns HTTP 401;
- an authenticated user without an active membership returns HTTP 403;
- a valid membership without the required action returns HTTP 403;
- a private identifier outside the active household returns HTTP 404;
- an authorized mutation with a missing or invalid CSRF token returns HTTP 403.

Unknown or future database role values fail closed as HTTP 403. Routes never
accept a client-supplied `household_id`; services receive the household scope
only from the authenticated active membership.

The tenancy migration preserves pre-authentication rows by assigning them to a
reserved, suspended migration household with no login credential. Those rows
remain inaccessible to normal users until an administrator explicitly reassigns
them; they are never attached to the first account that logs in.

## Operations Console

Every `/api/ops` route requires a signed-in administrator. There are two kinds of
account, ordinary users and administrators, and every administrator has the same,
highest level (decisions ADR-0047 section 1 and ADR-0051); administrators are the
fixed accounts in `ADMIN_ACCOUNTS`. The database still accepts the older
`data_reviewer` and `operator` values, but neither role grants Console access.
Household roles are independent, so household ownership grants no Operations
access. A signed-in non-administrator receives the same HTTP 404 body as an
unknown route. Missing authentication continues to use the common HTTP 401
session response. Every non-GET Console request also requires the session's
`X-CSRF-Token`; authorization is checked first so a rejected account still gets
the non-disclosing 404 response.

The route groups have these effects:

| Group | Endpoints | Effect |
| --- | --- | --- |
| Overview and task evidence | `GET /overview`, `/overview/series`, `/runs`, `/tasks`, `/tasks/{kind}/{id}`, `/services` | Read-only summaries and stored evidence |
| Debugging | `POST /services/{name}/check`, `POST /replay/*`, `GET /replays*` | Bounded provider probes or a replay recorded as a new run; no saved product plan or conversation |
| Experiments and configuration | `GET /config*`, `PUT /config/{key}`, `GET/POST /experiments` | Registered settings only; setting changes are audited and experiments create recorded runs |
| Accounts | `GET/PATCH /users*`, `DELETE /users/*` | The account workflows accepted by ADR-0047; mutations are confirmed in the UI and audited |
| Catalog data | `GET/PATCH /data/recipes*`, recipe withdraw/restore, `GET/PATCH /data/ingredients*`, `GET/PUT/DELETE /data/mappings*` | Registered catalog fields and overrides only; mutations are audited and allergens remain read-only |

Every Operations route is mechanically checked for the matching administrator
dependency: GET routes use the read gate and all POST, PUT, PATCH and DELETE
routes use the administrator-plus-CSRF gate. Response schemas are also checked
against credential, token, cookie, API-key and plaintext-health-profile field
names. Dynamic trace content still passes through the endpoint-specific
minimization and key-redaction tests.

The overview reports API and database availability, application version, queued
and running counts, failures and provider modes recorded during the preceding
24 hours, and the latest non-null code, catalog and product-snapshot versions
found in `OperationRun`. A version with no recorded evidence is `null`; the API
does not inspect a Git checkout or invent deployment metadata.

The run list accepts optional exact `type` and `status` filters, an inclusive
`since` creation timestamp, and a bounded `limit` from 1 to 200 (default 50).
Rows are ordered by creation time and ID, newest first. `total` is the complete
number matching the filters before the limit is applied.

Each list item contains the numeric run ID, trace ID, type, status, attempt
count, triggering user ID, input digest, safe version and provider fields,
error classification, timestamps and a derived duration when both start and
finish are known. It deliberately omits
`error_detail`, warnings and artifact references. Both endpoints are read-only
and neither creates an `AuditEvent` nor changes an `OperationRun`.

## Operations job actions

`POST /api/ops/jobs` accepts only the registered `catalog_import` job, one of
the fixed `reference` or `release_v2` sources, and `confirm: true`. It requires
an `Idempotency-Key` header plus the session CSRF token. Replaying the same key
and input returns the stored job without another audit event; reusing the key
for different input returns HTTP 409. No command, SQL, module, URL or filesystem
path is accepted.

`POST /api/ops/jobs/{run_id}/cancel` also requires `confirm: true` and CSRF. It
can cancel only a durable job that is still queued or running. A cancellation
clears the live lease and appends a separate `job_cancellation` operation and
audit event; it never deletes the target or rewrites a terminal run. Completed
jobs return HTTP 409 and non-job identifiers return HTTP 404. The attempt count
fences an older worker from completing a run after cancellation.
## Release data-quality evidence

The data-quality summary reads the server-registered release artifact; callers
cannot provide a filesystem path. It reports the release and schema versions,
generation time, released counts, cuisine/course/source distributions, nutrition
completeness, the separate estimated shares for servings, times and ingredient
amounts, dropped-reason counts and pending allergen rules. Artifact metadata
contains only registered filenames, SHA-256 digests, sizes and timestamps, never
server absolute paths. A missing, malformed or contract-incompatible summary is
returned as `degraded` with the affected metrics set to `null`, rather than as
invented zeroes.

The dropped-candidate endpoint accepts an exact reason filter and bounded
pagination (`offset >= 0`, `1 <= limit <= 200`). Unknown reason strings remain
valid data. Invalid JSONL rows or rows missing required fields are skipped and
counted, making the page `degraded` without returning the raw line; a missing
artifact has `total: null`, which is distinct from a valid empty file with
`total: 0`.

## Household Profiles

The current implementation maintains one profile per authenticated household.
Each member supplies a name, one to
three planned servings, allergens, prohibited ingredient IDs, and dietary
requirements. The backend deterministically sums servings and merges every
member's safety constraints into the shared-plan hard constraints.

Shared defaults include cooking time, per-meal and weekly budgets, general
health preferences, user-entered nutrition targets, an optional sodium target,
available ingredients, and fixture/live pricing mode. Each is only what the
household enters: an omitted budget, target, sodium ceiling or health preference
is none, and an omitted cooking time is no limit, stored as the widest the
planner accepts (240 minutes, `NO_COOKING_TIME_LIMIT`). A conversation with no
saved profile starts from the same empty state. Creating a profile writes
version 1. `PUT` requires `expected_version`; a successful edit appends an
immutable version, while a stale edit returns HTTP 409.

`POST /api/household-profiles/{profile_id}/plans` compiles a selected profile
version into the existing `WeeklyMealPlanRequest`. It accepts temporary
overrides for non-safety planning defaults but never removes member allergens,
prohibited ingredients, or dietary requirements. The persisted plan records
the profile ID, profile version, and complete effective-constraint snapshot.

The replan endpoint leaves the original plan unchanged and generates a linked
replacement from the requested profile version. Its response contains the old
plan ID and a deterministic, field-level list of changed constraints.

## Recipe Catalog

The recipe list uses keyset pagination. `next_cursor` is the last visible recipe
ID when another page is available; clients pass it back as `after_id`.

A recipe detail contains:

- identity, title, slug, cuisine, meal type, serving count, and preparation time
- dietary tags
- nutrition values per serving
- normalized ingredients, amounts, preparation notes, and each ingredient's
  `allergens` list
- ordered cooking steps

Nutrition values are descriptive planning data. They are not medical advice.

`GET /api/recipes/{slug}/tutorial` constructs a deterministic query from the
canonical recipe and returns at most one selected tutorial. `live=false` uses
the reproducible fixture provider. The current `live=true` adapter is an
explicit extension point and degrades to fixtures with a warning; it is not a
claim that live YouTube search is complete. Candidate lists and raw provider
payloads are intentionally absent from this user-facing contract.

## Recipe Recommendations

> Design boundary: `backend/app/schemas/planning_v2.py` is an internal
> final-scope algorithm contract. It does not create or change an HTTP endpoint
> in the current release. A production API and persistence migration must be
> reviewed separately before the final-scope planner replaces current planning
> behaviour.

`POST /api/recommendations/recipes` accepts a structured planning request with:

- household size and maximum cooking time (omitted: no limit, as for a profile
  and a conversation; the planning evaluation scenarios keep the 60 minutes they
  were written with, `SCENARIO_UNSTATED_TIME_LIMIT`)
- allergens, excluded ingredient IDs, and dietary requirements
- optional health preferences and user-entered nutrition targets
- an optional explicit sodium ceiling
- available ingredients with optional quantities and units
- an optional per-meal budget and `fixture` or `live` pricing mode

Hard filters remove recipes that violate allergens, excluded ingredients,
dietary requirements, cooking-time limits, an explicit sodium ceiling, or a
complete ingredient-use estimate above the user-entered budget.

Allergens follow one rule everywhere: every catalog ingredient lists each
allergen it contains out of the checked vocabulary in
`data/ingredients/allergen-vocabulary.json`, and an empty list means checked and
none. A requested allergen outside that vocabulary cannot be shown absent, so it
excludes every recipe with the reason "Cannot confirm it is free of: ...".
Unknown is excluded, not admitted.

Eligible recipes receive an explainable weighted score:

- nutrition alignment: 45%
- available-ingredient coverage: 30%
- cooking time: 25%

Inactive score dimensions are removed from the denominator. Low-sodium uses a
flexible 700 mg per-meal benchmark and gradually reduces the nutrition score up
to 1400 mg; it does not remove a recipe unless the user enters a hard ceiling.

Each retained recommendation contains a grocery estimate with the matched
product, required packages, checkout total, ingredient-use total, pantry
deduction, surplus quantity, mapping completeness, and budget result.

## Product Search

`GET /api/products/search` supports two explicit modes:

- `live=false`: deterministic FairPrice-shaped fixtures for tests and demos
- `live=true`: current FairPrice catalogue lookup with a 15-minute PostgreSQL cache

`refresh=true` bypasses a fresh cache entry. A live lookup degrades in a fixed
order: live, then the most recent cached FairPrice snapshot of any age (mode
`cache`, status `degraded`, with the date it was saved), then fixture results.
Every fallback sets `fallback_used=true` and a warning; the source is never
silently misrepresented. When FairPrice answers with no products, the response
is empty with status `no_match`: that ingredient is left unpriced rather than
given sample prices.

Every product response also carries a retrieval trace with requested source,
provider used, `live`/`cache`/`fixture` mode, `success`/`no_match`/`degraded` status,
query, fetch time, parser version, candidate count and warnings. Live lookup is
triggered only for the current product or Shopping List demand; broad catalog
crawling is outside this contract.

## Weekly Meal Plans

New-plan requests can supply `nutrition_constraints`, a list of metric/bound
objects whose omitted scope means a per-person average across selected meals;
`scope: "per_serving"` applies to each meal. `nutrition_guard_band` (0–1,
default 0.25) controls the soft guard around average targets. Successful
responses explain scope in persisted `warnings`. Legacy `nutrition_targets`
remain ranking-only. See [Product nutrition scope](design/planning-nutrition-scope.md)
for bounds, compatibility, examples and the Agent handoff.

`POST /api/plans/generate` extends the recipe-constraint request with:

- `start_date` and a currently fixed `day_count` of 7
- an optional `weekly_budget_sgd`
- the existing optional per-meal budget and fixture/live pricing mode
- `planner_strategy`: `beam` (default) or the explicit `greedy-baseline`
- an optional `max_uses_per_recipe` (1–7): how often one dish may appear in the
  week, a hard rule the search holds and the validator checks; 1 is no dish
  twice. Unstated, repeating stays a soft cost the planner avoids by itself.
- an optional `avoid_recipe_ids` (up to 200): recipes a new week leaves out,
  each course only while a week's worth of its other dishes remain; the
  conversation sets it to last week's dishes when the household asks for a new,
  more varied week.

- an optional `plan_shape` (decision ADR-0046): which meals of each day are
  planned and each meal's dish roles; the older `meal_composition` (dinner only)
  is still accepted, but not both.
  A role whose id is `vegetable` (a second one `vegetable-2`, and so on) takes
  only a dish of its courses that is led by vegetables and holds no meat or
  fish, as `backend/app/planning/vegetable_led.py` defines it (owner,
  2026-10-02); when none fits, an optional vegetable stays empty and a required
  one leaves the meal without a plan. Other roles take any dish of their
  courses.

The response holds the week as days × meals: one persisted entry per dish, each
with its `day_index`, `meal_type`, `role_id` and `portion_share`, plus the
`plan_shape` it was planned with, per-person weekly nutrition totals, an
aggregated shopping list, package checkout cost, ingredient-use cost, weekly
budget status, and explicit warnings. Known pantry quantities are deducted once
after every planned dish's requirements are combined.

New plans must pass independent validation before storage. The weekly budget
caps whole-package checkout cost; the legacy per-meal budget still caps
ingredient-use cost without pantry deduction. Both comparisons use whole cents;
sub-cent budgets require clarification. A missing price or unverified demand
cannot produce a successfully validated plan; a dish outside its usual meal
types is reported as a soft check and leaves the week's cost known. Under a
weekly budget, when every ranked week fails, the planner tries last the weeks of
its cost-led cheapest-week search: the strongest budget-led search, run under
the least whole-dollar budget it still completes a week within, bisected under
the cheapest week found so far to 5%, every week it found kept. That search
never reads the requested budget, so a week it finds at S$C is tried again
under any budget of S$C or more; failed attempts of it are marked
`cheapest_search` in the trace. It is the cheapest week a search found, not a
proof that no cheaper week exists. A shape with a meal of four or more dishes
does without it: there that search takes 5 to 16 s on the release catalog, and
minutes with no dish twice, past a plan's 10 s (ADR-0046).

Non-plans return HTTP 422 with one actionable `detail` sentence. Internal status
and proof scope are recorded in `OperationRun`, not added to the product view.
See the [Planning product adapter](design/planning-product-path.md) for trace
fields and the distinction between a search limit and infeasibility.

For proven infeasibility within the candidate packet, `detail` can include up
to three independently verified time or weekly-budget adjustments. These are
proposals: choosing one requires a new request and the same validation gate.
Safety restrictions are never offered for relaxation. Bounded search exhaustion
produces no adjustment suggestions. See [conflict explanations](design/planning-conflict-explanation.md)
for the declared-group minimality and resource limits.

`GET /api/plans/{plan_id}` returns the persisted snapshot. `GET /api/plans`
returns recent plan summaries for later history and dashboard integration.

## Meal Check-in and Nutrition Dashboard

`PATCH /api/plans/{plan_id}/entries/{entry_id}` accepts one status:
`planned`, `completed`, or `skipped`. A successful response returns the complete
updated weekly plan. Repeating the current status is idempotent; no additional
meal record or duplicate nutrition contribution is created.

`GET /api/plans/{plan_id}/dashboard` returns:

- planned-meal and completed-meal nutrition totals
- per-day planned and completed nutrition values
- planned, completed, and skipped entry counts
- weekly completion rate
- the user-entered nutrition targets stored with the plan

Only completed dishes from the selected MealCraft plan contribute to completed
nutrition. Plan-external foods are outside the current baseline and cannot be entered through
this contract.

## Event-driven Replanning

`POST /api/plans/{plan_id}/replan/preview` accepts an `entry_id`, optional
`reason`, and one event type: `REPLACE_MEAL`, `CANCEL_MEAL`, `LOCK_MEAL`, or
`ITEM_UNAVAILABLE`. The unavailable-item event additionally requires a normalized
`unavailable_ingredient`.

The preview does not modify the active plan. It persists the base revision,
before/after meal snapshots, nutrition delta, package-level Shopping List delta,
and checkout-cost delta. Completed and locked entries are rejected. Every preview,
including a shape change (`POST /api/plans/{plan_id}/shape/preview`), returns
`over_budget_sgd`: how far a change that raises the checkout total takes the
week over its weekly budget, or null within it and for a change that costs
nothing or saves (keeping or skipping a dish). A shape change is planned within
what the rest of the week leaves of the budget at the checkout (whole packages).
A dish added to a meal keeps the dishes the meal has on each day; when no plan
that keeps them fits what is left, the change is planned over the budget with
them kept, before any plan that replaces them is tried. A week is planned to
use most of its budget, so an addition to a budgeted week usually goes over it.
Over the budget the change is offered rather than refused. Two plans are found,
one from dishes the week does not have and one from every candidate, each the
cheapest week its search finds (a repeated dish counted at one meal's share of
the budget, and of the weeks costing no more than that, the one with the fewest
empty optional dishes, then the most distinct dishes). The one offered costs the
week less at the checkout with the rest of the week (a package both use is
bought once), each repeat of a dish anywhere in the week again counted at one
meal's share. A household's cap on uses ("no dish twice") counts the uses in the
rest of the week. The household confirms or discards the change. In the
preview's `shape_change`, a dish that stays on its day is in neither `removed`
nor `added`; `kept` counts them.

`POST /api/plans/{plan_id}/replan/{event_id}/confirm` applies a preview only when
its base revision still matches the active plan. Confirmation updates the target
entry, recalculates the consolidated grocery rows, increments the plan revision,
and marks the event as applied. A stale preview returns HTTP 409 instead of
overwriting a newer decision.

`GET /api/plans/{plan_id}/events` returns the persistent audit trail in reverse
chronological order.

## Persistent Planning Assistant

`POST /api/agent/sessions` accepts an initial natural-language `message` and
returns the persisted messages, parser provider, current structured constraints,
missing fields, clarification questions, readiness, and optional generated plan
ID. The response also returns `context_version`, `last_scope_decision`, and an
optional typed `pending_interaction`. `POST
/api/agent/sessions/{session_id}/messages` appends another turn and merges only
explicitly extracted values into the current state.

Every message first passes through the deterministic reference scope gate.
Supported meal-planning input may reach constraint parsing. Social, off-topic,
disease-treatment and adversarial requests receive a bounded response without
changing constraints, clarification state, pending interaction or context
version. A sum of money ("S$10 total", "$10 a week", 总共10块, 一百块) makes a message a
planning message, however it is phrased. An unclear message ("something nice",
我想吃点好的) is not a dead end: its bounded reply offers choices as a
`pending_interaction` (planning a week before a plan exists, changing a dish
once one does). Boredom with the dishes ("the dishes are boring", "too
repetitive", 菜很单调) is a wish for variety in either language: before a plan
it offers a week with no dish twice; with a plan it offers a new week with
different dishes or a swap of a dish that repeats. The new week is planned in
the turn with `avoid_recipe_ids` set to the week's dishes: no dish twice without
a weekly budget (or when the household asks for that), else the most varied
week the planner finds within the budget. It takes the session's week's place,
which stays saved, only with more different dishes, or as many and some new;
otherwise the week stays as it is and the reply says why (the budget with the
cheapest such week found, too few dishes, or the count of different dishes),
with a swap offered instead. A mixed request sends only
its supported segment to the parser. The persisted `last_scope_decision` makes
this routing visible to clients and tests. Every templated reply is written in
the language of the household's message, or, for a message with no words to
tell by (a number, "ok"), of their last one that had some
(`backend/app/agent/replies.py`). That includes the reason the planner or a
change to a saved week gives for turning a request down; one with no Chinese
wording yet is said in general terms rather than in English.

The assistant requires household size and resolves any unquantified available
ingredient before confirmation. A user may answer `unknown`; the quantity then
remains null, so the ingredient improves recipe ranking but is never deducted.
Asking for no repeats ("no dish twice", 不要重复, 一周不重样) sets
`max_uses_per_recipe` to 1 in the constraint state; confirmation passes it to
the planner as the hard rule described under Weekly Meal Plans.

Before the session becomes ready, the stated limits are checked against a floor
under the cost of any week the planner could build from its own candidates
(`backend/app/planning/week_floor.py`: the cheapest price per unit of each
ingredient, each dish at its smallest portion share, a role's days at its
cheapest dishes each served at most `max_uses_per_recipe` times, no search). A
per-meal budget below the floor, a required dish no candidate fills, or no
repeats with fewer different dishes than the week needs is refused with the
number that shows it. A weekly budget under the floor is refused with the cost
of the cheapest week the search finds, or, when the search finds none, with the
floor itself and no amount offered. The floor ignores whole packages, and no
multiple of it bounds them (on the release catalog the cheapest week the planner
finds costs 1.6 to 122 times it, most for one person's breakfasts with no dish
twice), so any other weekly budget is planned up front exactly as **Plan my
week** would plan it, nothing saved, and what that refuses is refused now. A budget refusal names the amount a person a meal and the cheapest
week the search found ("S$10 for 4 people is S$0.36 a person a meal over 7 meals.
The cheapest week I could plan costs about S$38.16: the cheapest my search found,
not a proof that none is cheaper."). The session keeps collecting and offers
choices a real week backs: "Use S$39 for the week" (that week fits it, so it
plans), and, for one meal a day, half the people at their own cheapest week
("2 people at S$26 a week", or "Plan for 2 people" when that fits the budget as
it is); for more meals a day that second search would take the reply past its
time limit, so it is not offered. A meal of four or more dishes takes the
planner's searches 5 to 26 s on the release catalog, past the reply's time
limit, so for such a shape nothing is searched before the session is ready:
only what the floor proves is refused (a weekly budget under it names the floor,
with no amount offered, since no week backs one yet), and **Plan my week**
answers the rest. Plan does not run the cheapest-week search for such a shape
either, so a budget its search runs into is named ("the search found no week
that meets the S$20 weekly budget") with no amount offered. No amount is
ever a guess. After a refusal, a bare amount ("S$50", 那就50新币吧) answers the
budget it asked about. A per-meal amount is offered only when a week plans with
it. When prices cannot be read, the check is skipped and Plan answers for itself.

When clarification can be represented structurally, the response includes a
`pending_interaction` with a stable `question_id`, `field_path`, option IDs and
`context_version`. `POST /api/agent/sessions/{session_id}/interactions` accepts
the matching IDs rather than localized button labels. The backend rejects
expired, stale, forged, duplicate or mixed option/free-text answers with HTTP
409. The first runtime slice supports household-size buttons and pantry
quantity input; other questions continue to work through the messages endpoint.
An interaction whose `field_path` is `message` offers sentences the household
could have typed (make the weekly budget S$39, Day 2, 第2天): the chosen option's
value, or free text, is sent as their message. A replanning question (which
kind of change, which day, which dish) comes with such choices.

`POST /api/agent/sessions/{session_id}/confirm` is accepted only when
`can_confirm=true`. It passes the validated state to the same deterministic
weekly planner used by `/api/plans/generate`, returns the generated plan, and
stores its ID on the agent session. When the planner finds no week, the response
is HTTP 422 and its detail names the limit the planner's trace shows the search
ran into (never a claim that no week exists); a budget it ran into is answered
as before planning, with the same backed choices when the cheapest-week search
found a week only the budget turned down. When it found none, the budget is
still named if every week the search ranked failed the budget alone, or the
search ran out of weeks on the budget; no amount is offered. A request the
planner turned down before searching (a budget in fractions of a cent, allergen
data it lacks) is passed on in the planner's own words, in the household's
language. The sentence is added to the
conversation and the session returns to collecting, so the client replaces its
Plan card with it. A slow search or missing data that may yet arrive leaves the
session ready to try again. `GET` endpoints let the frontend resume after a reload or container restart:
the home page reopens the newest conversation
whose `plan_id` is the household's current (newest) plan, the one that planned it
or last took it on (below); else the newest one
still ready to plan (`can_confirm`), so an interrupted first plan resumes; else a
fresh conversation beside that week. A conversation that has planned nothing
shows the current week in the plan panel.

The default parser is deterministic fixture mode. Optional OpenAI mode uses the
same Pydantic extraction contract. Neither parser makes medical recommendations,
decides allergen safety, or bypasses deterministic planning rules.

A week no open conversation planned (one planned on the profile page, or shown
beside an unrelated conversation) is changed the same way: the create and
messages endpoints accept an optional `plan_id`, the household's week the message
changes. A conversation with no plan of its own takes that week on (its
`plan_id` is set, `status` becomes `planned`, and any planning question it was
still asking is dropped), and the message goes to the replanning loop below. A
conversation that already has another week returns HTTP 409, and a week outside
the household HTTP 404.

The home page sends `plan_id` only for a dish's Swap, Keep, Skip or Can't buy,
or a follow-up chip, on such a week, and only while the message still starts
with that button's words. If a conversation in the recent list holds that week,
the page reopens it and sends the message there without `plan_id`, so normally
one conversation holds a week. Only when none is at hand does the open
conversation take the week on; one planning a new week of its own (ready to
plan with **Plan my week**, or still asking a planning question) asks first. The
question lasts only while the conversation is planning that new week and the
composer still holds the dish's words: once it plans one or stops, the question
and the dish's words go, and once other words replace them, the question goes.
The dish's words change only the week they came from, and keep it across a
reload, a new sign-in or a visit to another page. Once another week is shown or
opening (the conversation plans its own with **Plan my week**, or the week was
replanned on the profile page meanwhile), the words go, even if that week fails
to load, so they never reach a week that lacks the dish. Sent from the landing
box, they first reopen the week and its conversation, as **Open my week** does,
so they reach the conversation holding the week; nothing is sent until the week
and its conversations are back.

After a session has produced a plan, the messages endpoint switches to the
replanning loop. It accepts one user-triggered meal event at a time, resolves a
day or date and an unavailable ingredient when required, and asks one focused
question when the request is incomplete. A complete request calls the existing
deterministic replanning service and exposes the persisted preview as
`pending_replan`; it does not mutate the plan. A change that adds a meal or a
dish is planned within the budget the rest of the week leaves, without the
cheapest-week search; when nothing fits it, the cheapest dishes that search
finds with no budget are previewed instead, and the reply names the week's new
total and how far over the weekly budget it is, for the household to confirm or
discard.

`POST /api/agent/sessions/{session_id}/replan/confirm` applies the linked preview
with the same revision check as the plan API. `discard` clears the session link
and draft without modifying the plan. The draft and event link survive reloads
and container restarts.

### Orchestration runs, recovery and remaining target

The `backend/app/orchestration/` package supplies the scope gate, structured
interaction validator, capability registry, deny-by-default tool authorization
decision, action receipts, typed claim verification and a persistent per-action
run lifecycle. Every message, interaction, confirmation or replanning decision
creates an `AgentRun` with an input digest, explicit state, bounded budgets,
deadline and terminal outcome. Checkpoints and ordered tool-execution receipts
are stored separately so a client or evaluator can reconstruct what happened
without treating free-form assistant text as an audit trail.

After a session exists, state-changing Agent endpoints accept an optional
`Idempotency-Key` header. Reusing the same key with the same completed request
replays the persisted result without repeating a plan commit or conversation
mutation. Reusing it with a different payload, or while the first request is
still in progress, returns HTTP 409. Session creation itself does not advertise
cross-session idempotency.

`GET /api/agent/sessions/{session_id}/runs` returns recent runs and
`GET /api/agent/sessions/{session_id}/runs/{run_id}` returns its checkpoints and
tool receipts. `POST .../cancel` records a fail-closed cancellation for a
cancellable non-terminal run; completed runs cannot be rewritten. Tool-call,
LLM-call, retrieval-retry, planning-attempt, elapsed-time and API-cost budgets
are checked before usage is persisted. Budget or deadline exhaustion terminates
the run instead of committing partial state.

These remain deterministic foundations: the current scope classifier is a
transparent bilingual lexical reference, not a production multilingual model,
and the full asynchronous LangGraph execution graph is still a target.

Future tool execution is capability-gated. Read and preview tools may be called
only for a supported intent and authorized household. Commit tools additionally
require an unexpired confirmation linked to the matching preview and revision.
Scope, authorization, tool, grounding and action-receipt records belong to an
Agent run; they are not free-form assistant messages. The current synchronous
slice records logical parser, planner and persistence boundaries. Later
external adapters must add source timestamps, retries and evidence references
to the same receipt model rather than inventing a parallel log format.

A factual claim must exactly match its referenced typed evidence. A claim that
data is `live` additionally requires a timestamped `live_retrieval` fact. A
claim that an action was saved or applied requires a successful `commit`
receipt whose result kind and value match the claim; a successful preview is
not enough. Natural-language atomic-claim extraction and response-level
evidence linking remain future work.
