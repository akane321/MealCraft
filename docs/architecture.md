# Architecture

The MVP uses a modular monolith architecture.

## Components

- Nuxt frontend
- FastAPI backend
- PostgreSQL database
- Deterministic planning engine
- LLM constraint parser
- FairPrice grocery provider adapter

## Responsibilities

The agent interprets user language and produces structured constraints.

The planning engine applies deterministic hard constraints and soft-preference
scoring.

The grocery provider retrieves and normalizes FairPrice product information.

The database stores recipes, plans, products, and meal records.

## Recipe Data Flow

The recipe catalog follows the same modular-monolith boundary intended for the
remaining features:

1. FastAPI routes validate HTTP input and output.
2. The recipe service defines pagination and response assembly.
3. The repository performs eager-loaded SQLAlchemy queries.
4. PostgreSQL stores recipes, per-serving nutrition, normalized ingredients,
   recipe quantities, and ordered cooking steps.
5. Nuxt consumes the list and detail contracts without direct database access.

## Constraint Recommendation Flow

The constraint parser ultimately produces the same validated fields represented
by `RecipeRecommendationRequest`. The form can produce that structure directly,
while the assistant reaches it through a persistent multi-turn workflow without
changing the deterministic engine.

The recommendation flow is:

1. FastAPI validates normalized constraints.
2. The repository batch-loads recipes, nutrition, and ingredient relationships.
3. Hard constraints produce explicit exclusion reasons.
4. Eligible recipes receive nutrition, pantry, and time scores.
5. The grocery estimator maps scaled ingredient demand to product packages,
   deducting pantry stock only when a compatible quantity is known.
6. Complete ingredient-use estimates enforce the optional meal budget.
7. Nuxt renders rankings, grocery costs, package counts, and exclusions.

The LLM never determines allergen safety or the final constraint result.

## Persistent Planning Assistant Flow

1. Nuxt creates or resumes an agent session and displays both the conversation
   and the current structured constraint state.
2. The repository copies the persisted state and recent messages into a plain
   snapshot, then closes the read transaction before any external model call.
3. A LangGraph workflow runs two explicit nodes: constraint extraction, then
   state merge and clarification assessment.
4. The default fixture parser provides reproducible bilingual MVP behavior. An
   optional OpenAI parser uses a Pydantic structured-output schema and never
   invents absent values.
5. A short database transaction appends the user and assistant messages and
   updates constraints, missing fields, questions, and readiness.
6. Unknown pantry quantities remain explicit. After the user acknowledges an
   unknown quantity, the ingredient affects recipe ranking but is not deducted
   from the shopping list.
7. Disease-specific requests trigger a non-medical boundary message and are not
   converted into medical planning constraints.
8. Only a `ready` session can be confirmed. Confirmation calls the existing
   deterministic weekly-planning service and persists the resulting plan ID on
   the session.

The database, rather than an in-memory agent checkpoint, is the authoritative
conversation state. Container restarts therefore do not erase a planning thread.

## FairPrice Product Flow

1. The product route receives a normalized search query and pricing mode.
2. Fixture mode reads stable local product records for reproducible development.
3. Live mode first checks a time-bounded PostgreSQL cache, then parses the
   current FairPrice catalogue response when refresh is required.
4. Normalized snapshots are upserted by source, query, and external product ID.
5. A deterministic matcher ranks compatible products by ingredient tokens,
   package unit, and name similarity.
6. The estimator calculates both actual package checkout cost and prorated
   ingredient-use cost. The latter is used for the per-meal budget constraint.
7. Any live-provider failure is exposed and falls back to fixtures so the
   planning flow remains demonstrable.

## Weekly Planning Flow

1. The recommendation engine applies hard constraints and scores eligible recipes.
2. Per-meal product estimates enforce the optional meal budget without repeatedly
   consuming the same pantry stock.
3. A deterministic selector fills seven dates, avoids the previous day's recipe,
   adds a diversity penalty for repeated use, and uses the weekly budget as a
   feasibility guard when costs are complete.
4. Ingredient quantities from all selected recipes are converted to base units
   and aggregated.
5. Known pantry quantities are deducted once from the weekly total; unknown
   quantities remain a ranking signal only.
6. Unique ingredients are mapped to products once, then package counts, checkout
   cost, ingredient-use value, and excess quantities are recalculated at week level.
7. One short database transaction persists the plan, seven entries, nutrition
   snapshots, and consolidated grocery rows.
8. Nuxt renders the schedule, summary, warnings, and shopping list from the same
   persisted response contract.

## Meal Execution and Dashboard Flow

1. Each persisted meal-plan entry starts in the `planned` state.
2. The dashboard loads a selected weekly plan and its aggregated nutrition
   snapshot through separate read contracts.
3. A check-in updates exactly one entry to `planned`, `completed`, or `skipped`
   in a short database transaction.
4. The backend records a completion timestamp only for the `completed` state;
   repeated updates to the same state do not create duplicate records.
5. The dashboard service derives completed nutrition from the immutable
   nutrition snapshots already stored with the plan. It never infers or records
   food outside MealCraft.
6. Nuxt refetches the authoritative dashboard after each check-in and displays
   daily totals, weekly trends, completion progress, and the seven meal states.

## Event-driven Replanning Flow

1. The user selects one non-completed, non-locked meal and submits a structured
   event: replacement, cancellation, lock, or unavailable ingredient.
2. The deterministic recommendation service applies the plan's existing hard
   constraints and selects an alternative with penalties for extra repetition
   and disruption to adjacent days.
3. The backend rebuilds only the prospective recipe set and derives a fresh
   consolidated grocery estimate. It compares this estimate with the persisted
   Shopping List to produce package and price deltas.
4. A `previewed` event stores the base plan revision, before/after meal snapshots,
   nutrition delta, Shopping List delta, and proposed grocery state. The active
   plan is unchanged.
5. Confirmation uses optimistic concurrency: the event applies only if its base
   revision still equals `meal_plans.revision`. Otherwise the API returns HTTP
   409 and requires a new preview.
6. One transaction applies the target change, replaces derived grocery rows,
   increments the revision, and marks the event `applied`. Completed nutrition
   remains historical and completed or locked meals are never replaced.
7. Nuxt reloads the authoritative dashboard and displays the persistent event
   history so the reason and effect of each revision remain explainable.
