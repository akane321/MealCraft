# Sprint 2 Schema Foundation

Migration `20261018_0030` (after `20261012_0029`) adds every column and table the
Sprint 2 layers need, in one revision, so that feature work does not have to
write competing migrations. It changes no behaviour.

**Status.** The columns, the table and the types below are a **verified
baseline**: they are defined by migration `20261018_0030` and covered by
`backend/tests/test_sprint2_foundation_types.py` and
`backend/tests/migrations/test_sprint2_foundation_migration.py`. What reads and
writes them is an **accepted target**: nothing in the planner, the API or the
importer uses them yet. A feature PR that starts using a column also wires its
API field, its behaviour and any regenerated evaluation report.

**Wired so far.** Layer 08 PR-1 (household member fields and rules) wires, with
their behaviour and the [API Contracts](../api-contracts.md):

- the member keys `age_band`, `sex`, `goal`, `default_present` and the decimal
  or null `servings_per_meal` (HPB defaults from
  `data/nutrition/hpb-reference-v1.json`);
- `household_profile_versions.presence_rules`, `cooking_time_rules`,
  `missing_basics` and `nutrition_limits` (sodium only);
- `meal_plan_entries.servings`, written for plans whose request carries a
  household block and NULL otherwise;
- the types `AgeBand`, `Sex`, `PersonalGoal`, `Weekday`, `PresenceRule`,
  `CookingTimeRule` and `NutritionLimit`, with the new `HouseholdPlanning`.

The basic seasonings are a data file, `data/ingredients/basic-seasonings-v1.json`;
`ingredients.basic_seasoning` stays unwritten until the first tagging PR copies
the file into it with importer version `6`. Still unwired:
`self_only_allergens`, `missing_equipment` and every `recipes` tag column,
`FlavorBoost` and `PlanningPreferences`, and the other columns below. The
evaluation reports did not change: their requests carry no household block.
`python -m app.evaluation.household_rules` (in CI) measures the rules instead:
`docs/evaluation/household-rules/latest.md`.

## Rules of this foundation

- **Nothing reads or writes the new columns.** The planner, the importer and
  every endpoint behave as before. The generated OpenAPI document is identical
  before and after the migration.
- **Every new column is nullable, and NULL is today's behaviour.** Each column
  below says what NULL means.
- **A JSON column's `null` and SQL `NULL` mean the same.** The ORM may write a
  JSON `null` when it copies a row; readers treat both as "not set".
- **Constraints were only widened.** Plans may hold 1 to 14 days; requests still
  ask for 7.
- **No data was backfilled**, and the importer version stays `5`, so a compose
  start does not re-import the catalog.
- **Safety fields take effect only when enforced.** A halal or member-level
  allergen or diet option becomes selectable only in the PR that makes the
  planner and validator enforce it.

## Tables and columns

### `household_profile_versions`

| Column | Type | Content | NULL means |
| --- | --- | --- | --- |
| `presence_rules` (wired) | JSON list of `PresenceRule` | who is away or added at which weekdays and meals | every member at every meal |
| `cooking_time_rules` (wired) | JSON list of `CookingTimeRule` | cooking-time limits per weekday and meal | only `max_cooking_time_minutes` applies |
| `missing_equipment` | JSON list of `Equipment` | equipment the household says it lacks | all equipment is at home |
| `missing_basics` (wired) | JSON list of ingredient `normalized_name` | basic seasonings the household says it has run out of | every basic seasoning is at home |
| `nutrition_limits` (wired) | JSON list of `NutritionLimit` | upper limits the household switched on | only `max_sodium_mg_per_meal` applies |

The household-wide union columns (`allergens`, `excluded_ingredients`,
`dietary_preferences`, `planning_household_size`) stay and are still written,
for compatibility. Shopping days are not stored: the plan's first day and day 8
are derived.

**Member JSON keys** (no migration needed; a feature PR adds them to
`HouseholdMemberInput`; layer 08 PR-1 wired all but
`self_only_allergens`). Their names are fixed here:

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `age_band` | `AgeBand`: `toddler`, `child`, `teen`, `adult`, `senior` | null, read as adult | |
| `sex` | `Sex`: `female`, `male` | null, the average of both | |
| `activity` | `ActivityLevel`: `low`, `moderate`, `high` | null, read as moderate | |
| `goal` | `PersonalGoal`: `fat_loss`, `muscle_gain` | null, no goal | |
| `self_only_allergens` | list of allergens | `[]` | a subset of the member's own allergens avoided only in that member's food |
| `default_present` | boolean | `true` | `false` is an occasional guest whom a presence rule adds |
| `servings_per_meal` | decimal 0.25 to 3, or null | existing integer values unchanged | null is computed from energy needs |

### `meal_plans` and `meal_plan_entries`

| Change | Before | After |
| --- | --- | --- |
| `meal_plans_day_count_valid` (was `meal_plans_day_count_seven`) | `day_count = 7` | `day_count BETWEEN 1 AND 14` |
| `meal_plan_entries_day_index_valid` | `day_index BETWEEN 1 AND 7` | `day_index BETWEEN 1 AND 14` |
| `meal_plan_entries.servings` (wired) | none | `NUMERIC(6,3)`, `> 0` (`meal_plan_entries_servings_positive`) |

`servings` is how many servings the dish is cooked for: the sum of the servings
of the present members who can eat it. NULL is the existing rule (the plan's
household servings at `portion_share`). Several meat dishes in one meal use the
existing `role_id`, such as `protein_main_1`, `protein_main_2` and `staple`.

### `recipes`

All ten columns are nullable. NULL is untagged, and planning chooses dishes as
it does today.

| Column | Type | Content |
| --- | --- | --- |
| `meal_role` | text, CHECK `recipes_meal_role_valid`, index `recipes_meal_role_idx` | `MealRole`: `protein_main`, `vegetable`, `soup`, `staple`, `one_bowl`, `breakfast`, `salad`, `snack`, `dessert`, `sauce`, `drink` |
| `contains_staple` | boolean | a one-bowl dish that carries its own staple |
| `protein_sources` | JSON list of `ProteinSource` | `chicken`, `duck`, `pork`, `beef`, `lamb`, `fish`, `shellfish`, `soy`, `egg`, `legume`; chicken and duck are separate sources. `[]` is no main protein |
| `cooking_methods` | JSON list of `CookingMethod` | `deep_fry`, `stir_fry`, `pan_fry`, `steam`, `boil`, `braise`, `bake`, `grill`, `raw` |
| `flavor_tags` | JSON list of `FlavorTag` | `fragrant`, `spicy`, `light`, `rich` |
| `equipment` | JSON `EquipmentNeeds`: a list of lists of `Equipment` | the outer list is all needed, each inner list is any one of; `[["oven", "air_fryer"]]` is "an oven or an air fryer". `Equipment`: `oven`, `air_fryer`, `steamer`, `microwave`, `blender` |
| `halal_status` | text, CHECK `recipes_halal_status_valid` | `HalalStatus`: `halal`, `needs_certification`, `not_halal`, `uncertain`. About ingredients only; whether a `needs_certification` meat is bought as a certified product is checked on the product |
| `unknown_safety` | JSON list of `UnknownSafety` | `allergens`, `halal`, `diet`: safety facts not yet confirmed. When not empty, a household with that kind of limit never gets the recipe. External intake writes `["allergens"]` when it cannot read the allergens, never an empty allergen list |
| `estimated` | JSON `RecipeEstimates` | field name to `FieldEstimate` (`method`: `rule` or `llm`, `batch`, `reviewed`) for the tag fields an estimate filled. Servings and time keep `servings_basis` and `time_basis`; safety labels are never estimated |
| `owner_household_id` | foreign key `recipes_owner_household_id_fkey` to `households.id`, `ON DELETE RESTRICT`; index `recipes_owner_household_id_idx` | NULL is a shared catalog recipe; a household's id makes it that household's provisional recipe |

Passive time already has `passive_time_minutes`. Cuisine groups need no column:
they are derived from `cuisine` through a planned small mapping file, data/recipes/cuisine-groups.json. An
external recipe's source link goes in the existing `source` JSON.

### `recipe_ingredients`

`provenance` (JSON `IngredientLineProvenance`, nullable): `quantity_estimated`,
`from_steps` (added from the steps), `match` (`exact`, `alias`, `embedding` or
`parent`) and `reviewed`. NULL is a line as released.

### `ingredients`

| Column | Type | Content | NULL means |
| --- | --- | --- | --- |
| `food_group` | text | food group copied from the release file | unknown |
| `perishable` | boolean | only a confirmed `true` is perishable | "other", as `false` is |
| `basic_seasoning` | boolean | `true` is assumed at home: not listed or priced | not a basic seasoning |
| `halal_status` | text, CHECK `ingredients_halal_status_valid` | `IngredientHalalStatus`: `halal`, `not_halal`, `uncertain` | unknown |
| `nutrition_per_100g` | JSON, `PlanningNutrients` keys | only for extension-table and externally added ingredients | not given |
| `provenance` | JSON `IngredientProvenance` | `origin` (`extension_table` or `external_intake`), `nutrition_source`, `price_source` | a release ingredient |

The extension table is the `ingredients` rows whose `provenance.origin` is
`extension_table`; there is no separate table.

### `product_snapshots`

- `regular_price_sgd` (nullable, `>= 0`): the price before promotion, which
  caching used to drop.
- `halal_certified` (nullable boolean): NULL is unknown and counts as not
  certified.
- No retailer column: `source` is the retailer slug (every existing row is
  `fairprice`), and a new adapter writes its own slug.

### `meal_plan_grocery_items`

- `retailer` (nullable text, a `Retailer` slug): groups the list by store. NULL
  reads as `fairprice`, where every earlier product came from.
- `product_regular_price_sgd` (nullable, `>= 0`): the price before promotion.
  Savings are computed, not stored.
- `product_source` is not reused: it says how the product data was obtained
  (`fairprice` or `fixture`) and is validated when read back.

### `recipe_feedback` (new)

| Column | Content |
| --- | --- |
| `id` | primary key |
| `household_id` | `recipe_feedback_household_id_fkey`, `ON DELETE CASCADE` |
| `recipe_id` | `recipe_feedback_recipe_id_fkey`, `ON DELETE CASCADE` |
| `kind` | `FeedbackKind`: `like`, `dislike`, `never_again` (`recipe_feedback_kind_valid`) |
| `source` | `FeedbackSource`: `button`, `chat` (`recipe_feedback_source_valid`) |
| `created_at` | when it was given |

Indexes: `recipe_feedback_household_created_idx` (`household_id`, `created_at`,
`id`) and `recipe_feedback_recipe_id_idx`. Rows are only appended; undo, delete
and "clear all" delete rows. Preference scores are not stored: they are computed
from this table and the existing cooked, locked and swapped records.

## Unwired types

The types live in two modules and are imported by the layers that wire them:

- `backend/app/schemas/catalog_tags.py`: `MealRole`, `ProteinSource`,
  `CookingMethod`, `FlavorTag`, `Equipment`, `EquipmentNeeds`, `HalalStatus`,
  `IngredientHalalStatus`, `UnknownSafety`, `FieldEstimate`, `RecipeEstimates`,
  `IngredientLineProvenance`, `IngredientProvenance`, `Retailer`,
  `RetailerChoice`, `FeedbackKind`, `FeedbackSource`, and the `RETAILERS`
  registry.
- `backend/app/schemas/household_rules.py`: `AgeBand`, `Sex`,
  `ActivityLevel`, `PersonalGoal`, `Weekday`, `PresenceRule`,
  `CookingTimeRule`, `NutritionLimit`, `FlavorBoost`, `PlanningPreferences`.

Every model forbids unknown keys. Notes:

- **`Retailer`** is a lowercase slug (`^[a-z][a-z0-9_]*$`) that must be in
  `RETAILERS`: `fairprice`, `sheng_siong`, `cold_storage`, `giant`, `redmart`,
  `shopee`, `lazada`. No CHECK constraint lists retailers, so a new retailer is
  one entry in that tuple.
- **`RetailerChoice`** is one ingredient at one retailer: its
  `product_external_id`, or `None` when the retailer has no product on sale.
- **`PresenceRule`** keeps the household's words (`source_text`), the
  confirmation-card restatement, `member_name`, `present`, `weekdays` and
  `meal_types`. An empty list is every weekday or every meal. Rules name
  weekdays and meals only, never dates.
- **`CookingTimeRule`** has the same text, weekday and meal fields and
  `max_minutes` (5 to 240).
- **`NutritionLimit`** is a nutrient, `scope` `per_day`, and `max_value`; a
  `None` limit is each member's own HPB limit.
- **`PlanningPreferences`** changes soft goals and default rules only, never a
  hard limit: `repeat_allowed_meals` (the variety penalty is off for these
  meals), `flavor_boosts` (a flavour preferred on some weekdays and meals),
  `more_vegetables` and `lighter`. The language layer produces it and the
  planner reads it.

The CHECK value lists in the models and in the migration are tested against
these Literals, so a value added to one without the other fails the tests.

## Conventions for the feature PRs

### Tag files and their overlay order

Tag results live in their own reviewed data files, keyed by recipe or ingredient
id: `data/recipes/recipe-tags-v<n>.json`, `data/ingredients/ingredient-tags-v<n>.json`
and `data/ingredients/halal-v<n>.json`, starting at `v1`. On import, later sources win:

1. the release file;
2. the tag files;
3. runtime writes (external intake).

The importer reads the tag files, includes them in the catalog digest and moves
to importer version `6` once, in the first tagging PR. Later PRs only add or
update files and do not change the importer again.

### Evaluation record header

Every result written to `docs/evaluation` for a baseline, the held-out set or
the algorithm ladder carries the same header fields:

- baseline name, model, run id and date;
- language and category;
- data version and code commit.

The exact format is fixed with the evaluation pipeline PR.

### Data version file

`data/versions/<version>.json` records the digest of each frozen input: the
release files, each tag file, the extension table, each retailer's snapshot and
the HPB table. Report headers name this version.

### Provisional-recipe visibility

The external intake PR must make **every** recipe read path (such as the
planning pool, retrieval, browsing, recipe details, nutrition and the console) see only shared recipes
(`owner_household_id IS NULL`) plus the current household's own provisional
recipes, with a test for each path. This foundation adds no filter on purpose:
filtering one path would suggest the others are already safe. Deleting a
household must delete its plans before its provisional recipes, since
`owner_household_id` and the plan entries' recipe key are both `RESTRICT`.

## Requesting a schema change

- **A new column or table** needs a migration. Write a short request with: the
  table, the column name, its type, whether it is nullable, its default, the
  layer that uses it, and the plan section it comes from. The change lands as a
  small migration-only PR with its own revision after the current head, its
  model change and a migration test.
- **A new key inside an existing JSON column** (members, plan shape,
  constraints, price evidence, source) needs no migration. Add it to the
  Pydantic model, with two conditions:
  - its default is `None`, `[]`, `{}` or `False`, so stored rows and evaluation
    reports do not change;
  - the same PR updates [API Contracts](../api-contracts.md).

## Rollback

`alembic downgrade 20261012_0029` drops the table, then each foreign key, index
and CHECK before its columns, and finally restores `day_count = 7` and
`day_index BETWEEN 1 AND 7`. It fails while any plan is longer than 7 days. That
is deliberate: a rollback never deletes a household's plans to succeed.
