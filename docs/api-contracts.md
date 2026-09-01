# API Contracts

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

Available endpoints:

- GET /api/health
- GET /api/info
- GET /api/recipes?limit=20&after_id={recipe_id}
- GET /api/recipes/{slug}
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
- POST /api/agent/sessions/{session_id}/confirm

## Recipe Catalog

The recipe list uses keyset pagination. `next_cursor` is the last visible recipe
ID when another page is available; clients pass it back as `after_id`.

A recipe detail contains:

- identity, title, slug, cuisine, meal type, serving count, and preparation time
- dietary tags
- nutrition values per serving
- normalized ingredients, amounts, preparation notes, and allergen labels
- ordered cooking steps

Nutrition values are descriptive planning data. They are not medical advice.

## Recipe Recommendations

`POST /api/recommendations/recipes` accepts a structured planning request with:

- household size and maximum cooking time
- allergens, excluded ingredient IDs, and dietary requirements
- optional health preferences and user-entered nutrition targets
- an optional explicit sodium ceiling
- available ingredients with optional quantities and units
- an optional per-meal budget and `fixture` or `live` pricing mode

Hard filters remove recipes that violate allergens, excluded ingredients,
dietary requirements, cooking-time limits, an explicit sodium ceiling, or a
complete ingredient-use estimate above the user-entered budget.

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

`refresh=true` bypasses a fresh cache entry. If a live lookup fails, the API
returns fixture results with `fallback_used=true` and a warning; the source is
never silently misrepresented.

## Weekly Meal Plans

`POST /api/plans/generate` extends the recipe-constraint request with:

- `start_date` and a fixed MVP `day_count` of 7
- an optional `weekly_budget_sgd`
- the existing optional per-meal budget and fixture/live pricing mode

The response contains seven persisted main-meal entries, per-person weekly
nutrition totals, an aggregated shopping list, package checkout cost,
ingredient-use cost, weekly budget status, and explicit warnings. Known pantry
quantities are deducted once after the seven recipe requirements are combined.

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
nutrition. Plan-external foods are outside the MVP and cannot be entered through
this contract.

## Event-driven Replanning

`POST /api/plans/{plan_id}/replan/preview` accepts an `entry_id`, optional
`reason`, and one event type: `REPLACE_MEAL`, `CANCEL_MEAL`, `LOCK_MEAL`, or
`ITEM_UNAVAILABLE`. The unavailable-item event additionally requires a normalized
`unavailable_ingredient`.

The preview does not modify the active plan. It persists the base revision,
before/after meal snapshots, nutrition delta, package-level Shopping List delta,
and checkout-cost delta. Completed and locked entries are rejected.

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
ID. `POST /api/agent/sessions/{session_id}/messages` appends another turn and
merges only explicitly extracted values into the current state.

The assistant requires household size and resolves any unquantified available
ingredient before confirmation. A user may answer `unknown`; the quantity then
remains null, so the ingredient improves recipe ranking but is never deducted.

`POST /api/agent/sessions/{session_id}/confirm` is accepted only when
`can_confirm=true`. It passes the validated state to the same deterministic
weekly planner used by `/api/plans/generate`, returns the generated plan, and
stores its ID on the agent session. `GET` endpoints allow the frontend to resume
the latest conversation after a reload or container restart.

The default parser is deterministic fixture mode. Optional OpenAI mode uses the
same Pydantic extraction contract. Neither parser makes medical recommendations,
decides allergen safety, or bypasses deterministic planning rules.
