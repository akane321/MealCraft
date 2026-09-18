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

Everything below happens on the home page at <http://localhost:3000>. Besides
it there are only three pages: `/login`, `/profile` (the household settings
behind the avatar) and `/system` (service status).

### 1. Sign in and set up the household

The home page asks you to sign in before the first message and brings you back
afterwards; <http://localhost:3000/login> also registers a new account, and each
new account receives its own household. The avatar opens the household profile.

Record household members and servings, then configure shared defaults such as
budget, maximum cooking time, general preferences, optional user-entered
nutrition targets, and existing ingredients.

Important semantics:

- member allergens, prohibited ingredients, and diet requirements are merged
  into the safety boundary for the shared plan;
- an allergen MealCraft cannot check for excludes every recipe rather than
  none, and allergen labels come from ingredient data, so check product labels;
- saving an edit creates a new profile version, and a plan records the exact
  profile version used to generate it;
- only known, unit-compatible pantry quantities may reduce purchase demand;
- an ingredient without a quantity influences ranking only.

A week generated from the profile page shows up on the home page.

### 2. Plan the week in the conversation

Type what the week should look like, in English or Chinese. The page turns into
a conversation: the assistant extracts structured constraints and asks a focused
question when something is missing. Household-size and pantry-quantity questions
may appear as buttons; each answer is tied to the displayed conversation
version, so a stale choice cannot overwrite newer constraints. When the details
are complete, **Plan my week** generates seven dinners.

MealCraft handles meal planning, recipes, groceries, budgets and explicit
dietary constraints. Social, unrelated, disease-treatment and
instruction-bypassing requests receive a scope boundary and do not change
planning state; for a mixed request only the supported segment is processed. The
assistant does not calculate prices or decide allergen safety itself; it hands
the confirmed request to deterministic services.

The default fixture parser works without an API key. Model-based parsing is an
explicit local configuration described in [Development](development.md).

### 3. The week, recipes and tutorials (left edge)

Move the pointer to the left edge, or choose **See the week**. The panel lists
the seven dinners with calories, time and status, and tonight's dinner with a
how-to video when one matches the dish. Choosing a dish, or **Recipe & steps**,
opens its ingredients, allergen labels and steps. **Mark as cooked** records the
dinner. The conversation moves aside while a panel is open, and the pin button
keeps it open.

Tutorials currently come from a small sample set and are labelled as samples;
most dishes say that no video is available yet.

### 4. Nutrition and the shopping list (right edge)

Move the pointer to the right edge, or choose **Groceries & nutrition**.

Nutrition leads with what has actually been eaten: only dinners marked cooked
count as actuals. **All six nutrients & daily detail** opens the full view:
calories, protein, carbohydrate, fat, sodium and sugar per person, a cumulative
curve comparing cooked dinners with the current plan, and a daily table that
labels each dinner as actual, planned or not counted. Each dinner can be marked
cooked, skipped, or back to planned there. MealCraft does not know about food
eaten elsewhere, so this is not complete dietary monitoring.

The shopping list shows the total against the weekly budget and the costliest
lines. The price label says where prices came from: FairPrice with the date they
were fetched, prices saved earlier when FairPrice did not respond, or sample
prices. An ingredient FairPrice does not stock is listed as not priced rather
than given a made-up price. **Preview list** shows the sheet as it will print;
**Export PDF** opens the browser's print dialog, where you can save it as a PDF.

### 5. Change a dinner

Ask in the conversation, for example to replace Friday's dinner. The change is
first shown as a preview: the replacement recipe, the calorie and grocery
differences, and that other dinners are unchanged. **Confirm change** applies
it and updates the plan revision; **Keep as is** discards it. Completed and
locked dinners are protected, and a stale preview is rejected after another
confirmed change.

## Reading Nutrition Information

- Nutrition is descriptive and non-medical.
- User-entered calorie and macronutrient targets may affect planning.
- Broad lower-sodium, lower-sugar, or lower-calorie preferences are soft ranking
  signals unless the user enters an explicit limit.
- Missing nutrition data must not be interpreted as a successful validation.
- Nutrition actuals cover dinners marked cooked in MealCraft only.

## Common Recovery Steps

### The home page cannot reach the backend

```bash
docker compose ps
docker compose logs --follow backend
```

Confirm that <http://localhost:8000/api/health> is available.

### FairPrice live lookup fails

The shopping list falls back to prices saved earlier, then to sample prices, and
its price label says which. Retry later for current prices.

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

The current product supports one profile per authenticated household and one
main meal per day for seven days. The validated recipe catalog and browser-test
coverage remain smaller than the final design target. Live YouTube tutorial
search, validated web-recipe supplementation, semantic retrieval, and broader
dynamic stress cases are final-design gaps rather than verified current
capabilities.
