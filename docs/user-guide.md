# MealCraft User Guide

## What the Current Application Does

The current application supports a complete local workflow: household
preferences, a persisted week of the meals the household chose (several dishes a
meal where wanted), a FairPrice-shaped Shopping List, MealCraft-only nutrition
tracking, and previewed changes to single dishes or to the shape of the week.
Administrators have a separate operations console.

This guide describes the verified local application. Capabilities described as
future design targets in [Project Guide](project-guide.md) may not yet appear in
the interface.

## Start the Application

Start the stack as described in [Development](development.md#initial-setup),
then open <http://localhost:3000>. The health endpoint at
<http://localhost:8000/api/health> should return a successful response.

## Recommended Product Walkthrough

The week happens on the home page at <http://localhost:3000>. The other pages
are `/login`, `/profile` (the household), `/browse` (recipes and groceries),
`/history` (past weeks), `/system` (service status) and, for administrators,
`/ops`. The left rail and the header of every other page link to them.

### 1. Sign in and set up the household

The home page asks you to sign in before the first message and brings you back
afterwards; <http://localhost:3000/login> also registers a new account, and each
new account receives its own household. **Household** in the rail opens the
profile.

Record household members and servings, then configure shared defaults such as
budget, maximum cooking time, general preferences, optional user-entered
nutrition targets, and existing ingredients.

Under **Meals and dishes**, tick the meals each day plans (breakfast, lunch,
dinner; dinner only by default) and pick each meal's dishes: a preset (dinner
defaults to one main and one vegetable) or your own mix of mains, vegetables and
a soup, up to six dishes. A dish marked "if one fits" is left out when nothing
suits it.

Important semantics:

- member allergens, prohibited ingredients, and diet requirements are merged
  into the safety boundary for the shared plan;
- an allergen MealCraft cannot check for excludes every recipe rather than
  none, and allergen labels come from ingredient data, so check product labels;
- saving an edit creates a new profile version, and a plan records the exact
  profile version used to generate it;
- only known, unit-compatible pantry quantities may reduce purchase demand;
- an ingredient without a quantity influences ranking only.

### 2. Plan the week in the conversation

Type what the week should look like, in English or Chinese. The assistant
extracts structured constraints and asks a focused question when something is
missing; some questions offer buttons. When the details are complete, **Plan my
week** plans every chosen meal of the seven days.

MealCraft handles meal planning, recipes, groceries, budgets and explicit
dietary constraints. Social, unrelated, disease-treatment and
instruction-bypassing requests receive a scope boundary and do not change
planning state. The assistant does not calculate prices or decide allergen
safety itself; it hands the confirmed request to deterministic services.

The fixture parser works without an API key. With the OpenAI parser configured
(see [Development](development.md)), a model reads the message; if it does not
answer in time, the reply says so and the rule parser reads it instead.

### 3. The week, recipes and tutorials (right panel)

The right panel shows the next meal to cook ("Tonight", "Today's lunch" or
"Next up"), then the **Meals** tab: every day and meal with its dishes, time and
calories. Choosing a dish, or **Recipe & steps**, opens its ingredients,
allergen labels, steps and a how-to video when a key for YouTube is configured.
**Mark as cooked** records a whole meal.

Each dish still to cook offers **Swap**, **Keep**, **Skip** and **Can't buy…**.
Each fills the conversation with a sentence the assistant understands, so the
change is previewed before anything happens.

### 4. Nutrition and the shopping list

The **Groceries** tab shows the total against the weekly budget. The price label
says where prices came from: FairPrice with the date they were fetched, prices
saved earlier when FairPrice did not respond, or sample prices. An ingredient
FairPrice does not stock is listed as not priced. **Preview list** shows the
sheet as it will print; **Export PDF** opens the browser's print dialog.

The **Nutrition** tab leads with what has been eaten: only meals marked cooked
count as actuals, shown per meal and per day. The full view has all six
nutrients per person, a cumulative curve against the plan, and a daily table;
each dish can be marked cooked, skipped or back to planned there. MealCraft does
not know about food eaten elsewhere, so this is not complete dietary monitoring.

### 5. Change the week

Ask in the conversation. Two kinds of change are understood:

- **One dish**: "replace Friday's dinner", "lock tomorrow's lunch", "skip
  Sunday", "I can't buy salmon". If a meal has several dishes, the assistant
  asks which one.
- **The shape of the week**: "also plan lunch", "no breakfast", "dinners with a
  soup", "add a soup on Friday", "今晚不要配菜". Only the meals affected are
  planned again, with the budget the rest of the week leaves; adding a dish keeps
  the meal's other dishes, and taking one away keeps the rest at a larger share.

Every change is shown as a preview first, with the new dishes and the grocery
difference. **Confirm change** applies it; **Keep as is** discards it. Cooked
and locked meals never change, and a stale preview is rejected after another
confirmed change. A week-wide shape change applies to this week only; the
assistant then asks whether new weeks should plan the same way, and saves it to
the profile only if you say so.

### 6. Browse and look back

`/browse` searches recipes by title and course, and FairPrice products from
saved or live prices. `/history` lists every planned week; open one to see its
days, meals and what was cooked.

## The Operations Console

Administrators are fixed accounts listed in the local `.env` as
`ADMIN_ACCOUNTS=email:password:Name;email2:password2:Name2` and created or
updated when the backend starts; all have the same level. Removing an entry does
not remove the account's admin role: change it under **Users** in the console.
On the login page choose **Administrator**; the console at `/ops` offers the
overview, task records, service health, debugging replays, experiments and
runtime settings, users, and catalog data. Every change is recorded in the audit
history. The console cannot change allergen rules or mark a plan the validator
refused as valid.

## Reading Nutrition Information

- Nutrition is descriptive and non-medical.
- User-entered calorie and macronutrient targets may affect planning; a target
  may apply to each meal, to each day, or to the week's average.
- Broad lower-sodium, lower-sugar, or lower-calorie preferences are soft ranking
  signals unless the user enters an explicit limit.
- Missing nutrition data must not be interpreted as a successful validation.
- Nutrition actuals cover meals marked cooked in MealCraft only.

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

The current product supports one profile per authenticated household. Shape
changes in the conversation are read by rules, not by the model. With a tight
budget and several dishes a day, dishes repeat more often. Validated web-recipe
supplementation and broader dynamic stress cases are final-design gaps rather
than verified current capabilities. Security and privacy hardening is out of
scope for the course (no deployment).
