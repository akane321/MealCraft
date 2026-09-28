# v3 meal-day-week held-out set: findings

The set is `data/evaluation/heldout/v3-meal-day-week/` (60 episodes, frozen digest
`81faec54…`). The system is the product path (`python -m app.evaluation.meal_day_week_runner`),
fixture prices, no model calls. Each run's report is `run-N.{json,md}`; `latest.*` is the newest.

## Exposure

| Run | Code | Result | What had been seen before it |
| --- | --- | ---: | --- |
| 1 | `1c01c1b` (product code as merged in `62b30df`; only the report header changed) | **44/60** | Nothing: no product change was made between the freeze and this run. The implementation agent had read the episodes while preparing the owner's review pages (`provenance.json`). |

Every run after a product change is made after looking at the previous run's failures, and
is reported as such. Fixes are developed on developer episodes and synthetic cases only; the
held-out episodes are never used to test a fix before its run is reported.

## Run 1: 44 of 60

| Category | Strict success | Failed checks |
| --- | ---: | --- |
| shape_change | 1/12 | shape_request_understood 11, meal_roles_filled 9, required_slots_assigned 2 |
| meals_per_day | 9/9 | |
| composition | 9/9 | |
| budget | 7/9 | plan_present 2, status_matches_class 2 |
| safety_diet | 9/9 | |
| nutrition_per_day | 5/7 | plan_present 2, status_matches_class 2 |
| variety | 4/5 | repetition_requests_met 1 |

Planning the week itself held on every episode of the three planning categories (27/27),
including all 13 infeasible episodes, which the product refused with a reason. Every failure
is one of four mechanisms.

### 1. A shape change that names several days (5 episodes)

The conversation's reader takes one day from a request. "Saturday and Sunday", "Monday to
Friday", "Tuesday and Thursday", "weekends" become one day or none, so the change is previewed
for the wrong days (or read as something else) and the week's other slots are wrong.
Episodes: 002, 003 (also mechanism 2), 004, 007, 009.

### 2. The verb follows the meal, or is not in the reader's list (7 episodes)

The reader looks for a verb directly followed by a meal or dish ("no breakfast", "add a
soup", "不要配菜"). Chinese often puts the meal or dish first and the verb after ("汤都不用煮了",
"早餐就不用排了", "午饭也帮我们安排上"), and uses verbs the list lacks (煮、排、做、安排上);
English uses "take X off" and "won't need X". Counting a dish ("只做一道主菜") was not read
either. Episodes: 001, 003, 005, 008, 010, 011, 012. In every case the reader returned nothing,
so the product answered the unchanged week.

### 3. The composed-meal search completes no week under a hard limit (4 episodes)

With a weekly budget (033: four people, two mains, a side and a soup, S$100 against a S$84
witness; 036: a couple, main, side and soup, S$47 against S$39) or a per-day nutrition band
(049: three meals a day, protein ≥ 60 g; 053: two meals, fat ≤ 40 g and protein ≥ 30 g),
the meal beam returns no complete week (`weeks_tried: 0`) and the product says it could not
find one. The same mechanism fails developer episode `mdw-dev-008`. The other seven budget
episodes and five nutrition episodes passed, so it is a matter of the search's pruning and
breadth, not of the constraint handling.

### 4. A no-repeat request is soft (1 episode)

The product avoids repeating a dish but the request has no field for "no dish twice", so the
household's explicit rule is not enforced; 060 (six people, two mains and a side every night,
90 minutes) used one recipe twice. The planning schema already supports a hard cap
(`repetition_rules.max_uses_per_recipe`).

## What the numbers support

- On the unseen set the product plans and refuses correctly across meals per day, compositions
  and safety (27/27) and mostly under budgets and per-day targets (12/16).
- Changing the shape by asking is the weak part: the rule-based reader understood 1 of 12
  requests written the way households write them. This is a reader limit, not a planning
  limit: where the change was read, the replanning was right.
- These are counts on 5 to 12 episodes a category (ADR-0028); they locate mechanisms and do
  not support per-category rates.
