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
`/history` (past weeks), `/system` (service status: what works right now and
which prices the shopping list uses; administrators also see the version and
their links there) and, for administrators,
`/ops`. The left rail and the header of every other page link to them.

### 1. Sign in and set up the household

The home page asks you to sign in before the first message and brings you back
afterwards; <http://localhost:3000/login> also registers a new account, and each
new account receives its own household. **Household** in the rail opens the
profile.

Record household members and servings, then configure shared defaults such as
budget, maximum cooking time, general preferences, optional user-entered
nutrition targets, and existing ingredients.

Each member has an age group, sex, activity and goal. **Portions a meal** is
either **Auto**, which is that member's daily energy need from HPB's Recommended
Dietary Allowances over an adult reference, or a number you set (0.25 to 3).
Untick **Usually eats at home** for someone who joins only sometimes, such as
grandparents on weekends. Allergies, diets and foods a member will not eat are
kept per member.

MealCraft plans around the allergens it can check recipes for, so it only offers
those and turns down any other name: one it cannot check it cannot plan around.
Give each person their own name as well, since a rule, a warning and the plan
all say who they mean by it.

An allergen is avoided in every dish by the whole household, because one
kitchen can cross-contact. If an allergy is only one person's and cooking it for
the others is safe, tick **Only {name} avoids {allergen}** under that member's
allergens on the profile page. It warns that cooking in the same kitchen can
cause cross-contact, and asks you to turn it on only if that is safe for them.
Then only that member's dishes leave it out. This switch is on the profile page
only: an allergy you name in the conversation is still the whole household's.
Diets and foods a member will not eat always apply to that member's dishes only.

Under **Who's home and cooking time**, write one sentence in English or Chinese:
for example "The kids have lunch at school on weekdays", "我周三晚上加班不回来" or
"Weekday dinners within 30 minutes". MealCraft shows what it understood, and
nothing is added until you choose **Add this rule**. The rule is kept when you
save. Each meal is then cooked for the people home at that meal, and each meal
keeps its own time limit.

Under **Basics at home**, salt, sugar, cooking oil, soy sauce, garlic, ginger
and the other listed basics are assumed to be in your kitchen. They are left off
the shopping list unless you tick one as run out. Allergen checks still apply to
them: a dish with soy sauce is never planned for a soy allergy.

**Keep sodium within a daily limit** turns on a hard daily cap for each person.
It defaults to HPB's 2,000 mg for adults. The meals you plan keep within their
share of it: dinner only is 35% of the day.

Under **Meals and dishes**, tick the meals each day plans and pick each meal's
dishes. A household that has not chosen gets the **full default**: breakfast
(one dish), lunch (a protein main, a vegetable dish and a staple) and a dinner
that grows with the people at it, each lunch and dinner with its staple:

| People at dinner | Dinner |
|---|---|
| 1 to 2 | 1 protein main, 1 vegetable dish, soup |
| 3 to 4 | 2 protein mains, 1 vegetable dish, soup |
| 5 to 6 | 2 protein mains, 2 vegetable dishes, soup |
| 7 or more | 3 protein mains, 2 vegetable dishes, soup |

"People at dinner" counts who is home that evening, so a weekend dinner with
grandparents gets more dishes. It counts people, not portions: two adults and
three small children are five at dinner, however little the children eat (the
portions still decide how much of each dish is cooked and bought). The editor
shows each meal's dish count for the people usually home, and a dish marked
"From N people" only from that many on. A protein main may be a meat, fish,
tofu, egg or bean dish. The **staple** is rice by default, or noodles, bread or flatbread to
suit the meal's cuisine; it is on the shopping list, in the price, the nutrition
and the cooking time (cooking unattended, like a rice cooker). A one-bowl dish
such as fried rice, laksa or chicken rice carries its own staple, and may come
without a vegetable dish. A household that saved its own dishes keeps them; the
editor offers the full default as the recommended preset.

Every lunch and dinner is a real meal: a protein main with its staple or a
one-bowl dish, never a snack, dessert, sauce or drink, a salad only as the
vegetable dish and a soup only as the soup, no protein twice among the mains
(chicken and duck count as different), and at least a quarter of each person's
daily energy. Dishes of one cuisine group, and at most one deep-fried dish, are
preferred. The counts are defaults: the planner may leave out one dish when the
budget, the time or the dishes cannot fit it. A count you choose yourself is
kept as chosen.

A vegetable dish is a side dish or salad made mostly of vegetables, with no
meat or fish (eggs, cheese and sauces such as fish sauce are fine); a pasta,
rice or bean side does not count as one, and neither does a chicken salad.

Under **Kitchen**, tick the equipment you do not have (oven, air fryer,
steamer, microwave, blender); a recipe that needs it is never planned. A recipe
that works in an oven or an air fryer is still planned while you have one of
them.

Important semantics:

- a dish is served when at least one member home for that meal can eat it, and
  every member home for a lunch or dinner gets a filling meal of dishes they
  can eat (a protein main with the staple, or a one-bowl dish, and a vegetable
  dish they can eat whenever the meal has one) that reaches their own share of
  their daily energy; each dish is cooked and bought for the members who can eat
  it;
- at every other meal, breakfast included, and at a meal you have cut down to a
  single dish, the rule still holds in its simplest form: nobody at that table
  is left with nothing they can eat;
- allergens are avoided by the whole household, for every meal, even one that
  member is away for, unless the member marked one as "only I avoid it"; diets
  and foods a member will not eat apply to that member's dishes only;
- when no plan can cover every member, MealCraft says who could not be covered
  and offers a larger budget, more cooking time or more dishes a meal. It never
  relaxes an allergen, diet or excluded food, and never cooks an extra dish for
  one person;
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
week** plans every chosen meal of the seven days. A plan from the household
profile may be 1 to 14 days long (**Days to plan**, beside the plan button on
the Household page). A plan longer than a week shops twice: before
day 1 and before day 8, with the weekly budget holding on each trip. Leafy
greens, bean sprouts and pea shoots, fresh fish and fresh shellfish are cooked
within 3 days of the trip they are bought on, and the shopping list marks them
"Use within 3 days".

Most plans take a few seconds. A large household on a tight budget takes longer,
a few minutes, while the planner searches for a week that fits the
budget; the button says "Planning…" until the plan is ready. How long is
acceptable follows how hard the request is: a simple week comes back quickly, a
complex one is allowed the longer wait rather than being cut short.

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
calories. A dish some of the people at the meal cannot eat shows small text
beside it, for example "Not for Mei". Choosing a dish, or **Recipe & steps**,
opens its ingredients, allergen labels, steps and a how-to video when a key for
YouTube is configured.
**Mark as cooked** records a whole meal.

Each dish still to cook offers **Swap**, **Keep**, **Skip** and **Can't buy…**.
Each fills the conversation with a sentence the assistant understands, so the
change is previewed before anything happens. A swap keeps every member covered,
and the new dish is cooked for the people who can eat it.

### 4. Nutrition and the shopping list

The **Groceries** tab shows the total against the weekly budget. Perishable
items (leafy greens, bean sprouts and pea shoots, fresh fish and fresh shellfish)
are marked **Use within 3 days**: the planner cooks them within three days of the shopping trip
that buys them, and assumes everything else keeps until its day. In a plan
longer than a week the list is split by trip, under **Shop before day 1** and
**Shop before day 8**. The price label
says where each item's price came from: a current FairPrice check, a saved
FairPrice observation with its date, or a sample price. A sample item with no
matching FairPrice product is explicitly marked as not checked; that is different
from a check that timed out or returned no selected product. Hover over a price
note to see the observation and check-attempt times. A known unavailable product
is labelled unavailable; an ingredient without a priced product remains not
priced; water and ice are not bought and are not listed. A saved price that could not be checked live in time is
labelled "Saved FairPrice price ... not checked live in time", never as a sample. Above the list a line gives the time of
the last live check and how many items are live, saved or sample ("Prices checked at 15:40 · 15 live · 19 saved · 3 sample").
**Preview list** includes these source notes on the
sheet as it will print; **Export PDF** opens the browser's print dialog.

The **Nutrition** tab leads with what has been eaten: only meals marked cooked
count as actuals. Choose a day, and a meal when that day has several, to compare
all six nutrients in **Actual** and **Current plan**. Skipped dishes count in
neither; Current plan includes cooked dishes. Groceries and Nutrition have their
own panel space; the next-meal card stays on Meals. The full view has all six
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
  If the budget has no room for the change with your dishes kept, it is still
  offered, with how far it takes the week over the budget; you decide. The
  preview lists only the new dishes; the ones that stay are not shown again.

Every change is shown as a preview first, with the new dishes and the grocery
difference. With live pricing this is an estimate: only selected products are
checked again on confirmation, so the confirmed cost may differ without changing
the dishes. **Confirm change** applies it; **Keep as is** discards it. A lock's
preview offers **Keep it locked** and **Cancel**. The week's change list dates
each changed dish by its own day and meal ("Thu dinner"). Cooked
and locked meals never change, and a stale preview is rejected after another
confirmed change. A week-wide shape change applies to this week only; the
assistant then asks whether new weeks should plan the same way, and saves it to
the profile only if you say so.

### 6. Browse and look back

`/browse` searches recipes by title and course, and FairPrice products. Prices
are samples unless you tick **Ask FairPrice now**; under the results the page
says "Sample prices", "FairPrice prices from <date>" or "FairPrice prices now",
and adds "FairPrice didn't respond" when it had to fall back. `/history` lists every planned week; open one to see its
days, meals and what was cooked. A week whose days you planned again is marked
"Replaced by a newer plan". Reopening the conversation of a replaced week shows
it read-only, with **Open the current week**.

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

Shopping and nutrition totals use the recipe's recorded ingredients and
quantities. They do not prove that the source recipe lists every ingredient:
some recipes describe a filling, stock or frying oil only in the steps. Check
the ingredients against the steps before cooking or treating a total as complete.

The current product supports one profile per authenticated household. Shape
changes in the conversation are read by rules, not by the model. With a tight
budget and several dishes a day, dishes repeat more often. Validated web-recipe
supplementation and broader dynamic stress cases are final-design gaps rather
than verified current capabilities. Security and privacy hardening is out of
scope for the course (no deployment).
