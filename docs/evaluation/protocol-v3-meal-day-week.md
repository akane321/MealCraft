# Evaluation protocol v3-meal-day-week

Status: **in use; runs after held-out run 1 are [protocol v3.1](#protocol-v31).** This protocol evaluates planning a
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

Since 2026-09-28 the witness keeps the product's own rules, so a label never
needs a week the product cannot plan: a role takes only dishes for its meal
when there are as many as the planner keeps per role (ADR-0044, ADR-0046
"Meal fit"), and each ingredient is bought as the product buys it in fixture
mode, one product in whole packages. Before, the witness could mix package
sizes the product never buys and put a dinner-only dish at lunch. The same
day, developer episode `mdw-dev-008` changed: its budget of S$49 (S$1.17 a
person a planned meal) was below any week the product can buy and below the
S$2.50 floor the held-out set uses, and is now S$105. Developer reports before
that date are on the earlier episode.

Since 2026-10-01 the witness also keeps the product's time limit and candidate
rules (ADR-0049). A household that states no time limit is planned by the
runner with 240 minutes (`NO_TIME_LIMIT`), and the product holds every dish and
every meal within it (`meal_beam.dish_eligible`, `meal_permitted`); the tool
now does the same, where it had read no limit as none, so a witness could use a
445-minute soup. A dish is also one the product can carry as a candidate. The
tool mirrors the product's rules, not its ranking: the planning pool
(`RecipeRepository.list_for_planning`, run over the episode's pool imported as
the runner imports it) leaves out a recipe the release import skips (under two
lines or no instruction), one with a line the product cannot price, a withdrawn
one (`data/recipes/withdrawn.json`) and one whose own numbers say it lost a
line (`recipe_quality.incomplete`, since #170); the recommendation step leaves
out one whose name states an ingredient or allergen the household avoids
(`title_mentions`). A dish that merely ranks low, or falls outside the packet
the product keeps per course, stays eligible: a label proves that a week exists
under the rules, not that the product's search finds it. Protocol v2 labels are
unchanged.

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
   weekly average and missed it on some days). A stated cap on uses
   (`repetition_requirements.max_uses_per_recipe`) is sent as the request's
   `max_uses_per_recipe`, a hard rule (before it existed, the product only avoided
   repeats by itself).
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
- **Held-out set:** `data/evaluation/heldout/v3-meal-day-week/`, 60 episodes
  (47 feasible, 13 infeasible; 30 English, 30 Chinese). Drafted by a sealed agent
  from a packet of catalog facts, reviewed by the owner in three rounds and
  revised only on their written notes, then frozen before any system ran on it.
  `provenance.json` says what the drafter could see and where independence does
  not hold; `review.json` holds every verdict; `verification.json` every check
  run on the final set; `witnesses.json` each feasible episode's witness week and
  shopping list. Two things differ from the developer set, by the owner's
  decisions: budgets are feasible only (an impossible budget at a realistic
  amount cannot be proven with whole packages), and a budget is at least S$2.50
  per person per planned meal. Do not tune against its results.
  Runs and findings are in `docs/evaluation/v3-meal-day-week/heldout/`: run 1, before
  any product change, scored 44 of 60.
  Run 2 (v3.1, a diagnostic) found no regression on the episodes run 1 passed.

## Protocol v3.1

Since the first held-out run, the evaluated arm changed twice: the runner sends
the gold cap on uses of a recipe as the request's `max_uses_per_recipe` (#194),
and the product's rule reader reads shape changes that name several days
(#188). Both changes were made after the run 1 results were seen, so runs from
then on are **protocol v3.1** (ADR-0037 section 4, ADR-0049 section 2). The
runner's reports say `v3.1-meal-day-week`; run 1 stays under v3 and is never
re-labelled.

The v3 held-out set is spent for the shape-change reader: run 1's findings
quoted held-out wording, and #188 then added that wording to the rule reader.
The other fixes were also chosen after reading run 1, so a v3.1 run on the held-out set
is a **diagnostic** in every category, reported beside run 1 and never as a
held-out score. A held-out score for this family needs a fresh set, drafted,
reviewed and frozen before any system runs on it (ADR-0049 section 1).
