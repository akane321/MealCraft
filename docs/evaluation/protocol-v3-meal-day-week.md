# Evaluation protocol v3-meal-day-week

Status: **draft, developer episodes only.** This protocol evaluates planning a
week of days, each holding the meals the household chose, each meal holding one
or more dishes (decision ADR-0046 section 5). It follows the rules of
[protocol v2-multidish](protocol-v2-multidish.md) wherever this page says
nothing else. The one-dinner week stays a regression case under the earlier
protocols.

## 1. What is evaluated

A household with a plan shape (which of breakfast, lunch and dinner are planned,
and each meal's dish roles) asks for a week. The product must plan every
(day, meal) slot with one dish per role, keep every stated limit across all
slots, and buy what the week needs. In a shape-change episode the household then
asks, in its own words, to change the shape: add a meal, drop a meal, add a dish
to one meal, or take a dish away. Only the affected meals may change.

## 2. Episodes

An episode is a v2-multidish episode (`heldout-episode-v1`) with these changes.

- **`scenario.household_profile.plan_shape`** replaces `meal_composition`: the
  shape of `MealPlanShape`, `{"meals": {meal: [roles]}}`. It is profile context,
  given to the product as structured input.
- **Slots** are `mon-breakfast` ... `sun-dinner`, one per planned meal per day.
- **Nutrition bands** may use scope **`per_day`**: a day's total per person,
  each dish counted at its portion share.
- **A shape-change episode** adds `scenario.shape_change_request` (the
  household's words) and fills `gold.replan_invariants`:
  - `shape_change`: the change it asks for, in the shape of
    `MealPlanShapeChangeRequest` (`meal_type`, `roles` or null to drop,
    `day_indexes` or null for the whole week);
  - `changed_slots`: the slots that may change; every other slot is listed in
    `unchanged_slots` and must stay identical;
  - `kept_dishes`: roles of a changed slot whose dish must stay (taking a dish
    away keeps the others).

A shape-change episode carries no budget, cap on uses or nutrition band, so the
changed meals cannot depend on the rest of the week and its label stays provable.

**Pools** are drawn by `python -m app.evaluation.multidish_pool`, as in
v2-multidish, with two differences for a plan shape. Each course gets
`max(12, 2 × its role-days)` recipes, where a role-day is one role on one day
that admits the course, counting the shape change's roles. The pool's products
also include the prices the product uses in fixture mode:
- the curated fixture file's gram packages for the curated ingredients it
  matches by name first;
- the products of each option of an "A or B" ingredient.

**Labels** are proven by `python -m app.evaluation.multidish_labels` from
catalog facts alone. A feasible label needs a witness week, built day by day
from each slot's cheapest valid meals, that keeps any cap on uses and every
per-day band and is bought within the budget. An infeasible label needs a
proof: a slot with no valid meal, or a budget below the sum of each slot's
cheapest meal. A shape change is proven before and after it, and the gold's
`changed_slots` must be exactly the slots the change touches.

## 3. Categories

| Category | What it tests |
| --- | --- |
| `meals_per_day` | two and three meals a day; breakfast is the thinnest catalog |
| `composition` | each meal type's own roles, including a custom mix (two mains, a vegetable and a soup) |
| `nutrition_per_day` | per-day targets across a day's meals |
| `budget` | one weekly budget over every meal, tight and impossible |
| `safety_diet` | allergens and diets in every meal, breakfast included |
| `variety` | no dish twice anywhere in the week, when the household asks |
| `shape_change` | add a meal, drop a meal, add a dish to one meal, take a dish away |

## 4. The system and its answer

One system is run, **P, the product path**
(`python -m app.evaluation.meal_day_week_runner`). No model is called and every
price is a fixture price.

1. **The pool.** An in-memory database holds only the episode's pool, imported
   by the product's release importer.
2. **The week.** `WeeklyMealPlanService.generate` plans the profile's shape and
   limits. A stated time limit applies to each meal; none stated is sent as the
   product's widest, 240 minutes. A per-day band is sent as the product's
   `per_day` nutrition target (added after the first run, which had to send it as a
   weekly average and missed it on some days). A cap on uses has no request field; the
   product avoids repeats by itself.
3. **The change.** In a shape-change episode the words are read as the
   conversation reads them: one-dish events first, then the day, then
   `read_shape_change`. The change is previewed with `preview_shape`, with
   today set to the week's first day, and confirmed.
4. **The answer.** The final week becomes the common output. Refusing to plan
   is answered as `infeasible`, with the product's message.

## 5. Scoring

Strict success over the final week, as in v2-multidish section 4. Roles,
courses and meal time are checked per slot against that slot's roles after the
change. Shares extend to five and six dishes (0.45 / 0.3 and 0.4 / 0.28). "A or
B" lines are scored as the option the household can eat and buy, the rule the
product states; the scorer holds its own copy of it. Added checks:

| Check | Rule |
| --- | --- |
| `nutrition_per_day` | Every day's total per person is within each per-day band, with the manifest's 2 % tolerance. |
| `shape_request_understood` | The change read from the household's words equals the gold `shape_change`: its meal, roles and days. |
| `unchanged_meals_identical` | Every slot in `unchanged_slots` holds the same dish in every role as before the change. |
| `kept_dishes_identical` | Each role in `kept_dishes` keeps its dish. |
| `shape_change_applied` | Failed when the preview or confirmation refused the change. |

The report also records, beside strict success, the number of dishes and of
distinct recipes, meal fit (dishes whose release meal types include their
slot's meal) and cost. Results are counts per category (ADR-0028).

## 6. Exposure

- **Developer set:** `data/evaluation/dev/v3-meal-day-week/episodes/`. Written by
  the implementation agent. It may be inspected and used to fix code. Its
  results are never held-out evidence. Its report is
  `docs/evaluation/v3-meal-day-week/dev/latest.md`, with the dataset digests and
  the code revision.
- **Held-out set:** none exists yet. It will be drafted from a sealed packet,
  reviewed by the owner and frozen before any system runs on it, as
  v2-multidish's was (section 7). No claim is made before then.
