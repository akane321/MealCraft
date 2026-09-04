# MealCraft User Guide

## What the Current Application Does

The current application supports a complete local workflow from household
preferences to a persisted seven-day plan, FairPrice-shaped Shopping List,
MealCraft-only nutrition tracking, and previewed meal changes.

This guide describes the verified local application. Capabilities described as
future design targets in [Project Guide](project-guide.md) may not yet appear in
the interface.

## Start the Application

From the repository root:

```bash
cp .env.example .env
docker compose up --build --detach
docker compose ps
```

PowerShell users can replace the first command with:

```powershell
Copy-Item .env.example .env
```

Open <http://localhost:3000>. The health endpoint at
<http://localhost:8000/api/health> should return a successful response.

## Recommended Product Walkthrough

### 1. Create or update the household profile

Open <http://localhost:3000/profile>.

Record household members and servings, then configure shared defaults such as
budget, maximum cooking time, general preferences, optional user-entered
nutrition targets, and existing ingredients.

Important semantics:

- member allergens, prohibited ingredients, and diet requirements are merged
  into the safety boundary for the shared plan;
- saving an edit creates a new profile version;
- a plan records the exact profile version used to generate it;
- only known, unit-compatible pantry quantities may reduce purchase demand;
- an ingredient without a quantity influences ranking only.

### 2. Use the planning assistant

Open <http://localhost:3000/assistant> and describe the request in English or
Chinese. The Assistant persists the conversation, extracts structured fields,
and asks a focused clarification when required.

Review the structured constraint summary before confirmation. The Agent does
not independently calculate prices or decide whether allergens are safe; it
delegates the confirmed request to deterministic services.

The default fixture parser works without an API key. Model-based parsing is an
explicit local configuration described in [Development](development.md).

### 3. Generate and inspect the weekly plan

Open <http://localhost:3000/weekly-plan> directly or follow the result from the
profile or Assistant flow.

Inspect:

- the seven planned main meals;
- recipe and serving information;
- per-person nutrition;
- constraints and budget outcome;
- consolidated grocery demand;
- package quantities and prices;
- pantry deductions.

The weekly planner avoids consecutive repetition when alternatives are
available. If the request is infeasible, the product should report the conflict
instead of returning a plan that silently violates hard constraints.

### 4. Inspect recipes and products

Use <http://localhost:3000/recipes> to browse the validated internal catalog and
open recipe details. Use <http://localhost:3000/products> to search FairPrice
products.

Product results may come from:

- `live`: a current FairPrice lookup;
- cache: a recent result stored in PostgreSQL;
- fixture: stable FairPrice-shaped development data.

Use fixture mode for reproducible demonstrations and tests. Live data may change
or become temporarily unavailable.

### 5. Record plan execution

Open <http://localhost:3000/dashboard>. Each planned meal can be marked:

- `planned`;
- `completed`;
- `skipped`.

Only completed MealCraft dishes contribute to actual nutrition totals and weekly
trends. The Dashboard does not know about food eaten outside MealCraft and must
not be interpreted as complete dietary monitoring.

### 6. Preview a plan change

Use the available replanning action from the weekly plan or Assistant. A change
is first stored as a preview. Review the replacement recipe, nutrition changes,
Shopping List changes, price delta, and validation result before confirming or
discarding it.

Confirmed changes update the plan revision and event history. Completed and
locked meals are protected, and a stale preview is rejected after another
confirmed change.

## Structured Planning Form

The form at <http://localhost:3000/plan> provides direct constraint matching
without a conversation. It is useful for inspecting deterministic recommendation
behaviour and comparing structured input with Agent-parsed input.

## Reading Nutrition Information

- Nutrition is descriptive and non-medical.
- User-entered calorie and macronutrient targets may affect planning.
- Broad lower-sodium, lower-sugar, or lower-calorie preferences are soft ranking
  signals unless the user enters an explicit limit.
- Missing nutrition data must not be interpreted as a successful validation.
- Dashboard actuals cover completed MealCraft dishes only.

## Common Recovery Steps

### A page cannot reach the backend

```bash
docker compose ps
docker compose logs --follow backend
```

Confirm that <http://localhost:8000/api/health> is available.

### FairPrice live lookup fails

Retry without forcing a refresh or use fixture mode. The application should
degrade visibly rather than presenting old or fixture data as current live data.

### The database schema is behind

```bash
docker compose exec backend uv run --no-sync alembic upgrade head
```

### Local data should be preserved while stopping

```bash
docker compose down
```

Do not add `--volumes` unless the PostgreSQL development volume is intentionally
being discarded.

## Current Limitations

The current product primarily supports one shared household and one main meal
per day for seven days. The validated recipe catalog and browser-test coverage
remain smaller than the final design target. Authentication, a unified recipe
execution side panel, validated web-recipe supplementation, semantic retrieval,
and broader dynamic stress cases are final-design gaps rather than verified
current capabilities.
