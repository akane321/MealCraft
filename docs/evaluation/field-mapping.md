# Product constraints to the neutral field dictionary

This is apparatus, **a draft that needs an independent review**, not run admission, a freeze or a result. It reads
the product's echo of its constraints into the public neutral dictionary
([`scripts/sprint2-heldout-fields.json`](../../scripts/sprint2-heldout-fields.json)) so that intent cases can later be
compared field by field. The sealed set's dictionary may carry fields beyond the public one; those are not known here.

`backend/app/evaluation/field_mapping.py` takes only `UnifiedOutput.request_fields`. Nothing is read from an answer
text, a recipe name or a category, and nothing is scored.

| Native key | Dictionary field | Rule |
|---|---|---|
| `household_size` | `household_size` | as stated |
| `weekly_budget_sgd` | `weekly_budget_sgd` | as stated |
| `allergens` | `allergens` | as stated, non-empty |
| `excluded_ingredients` | `excluded_ingredients` | as stated, non-empty |
| `dietary_preferences` | `dietary_requirements` | the labels as stated, non-empty |
| `requires_halal` | `halal_required` | only `true`; the product drops a false value from its echo, so false is **not stated**, never mapped to `false` |
| `max_cooking_time_minutes` | `cooking_time_minutes` | as stated, except the no-limit value (240), which is not stated |
| `plan_shape.meals` | `meal_types` | the planned meals in breakfast, lunch, dinner order |

A missing or empty value is listed under `not_stated`; it is never filled with a default.

**An empty list or `None` reads as "not stated".** The echo cannot tell "the user said there is no allergen" (or no
limit) from "the user said nothing", so a stated "none" and "not stated" look the same here. The mapping does not try
to separate them; the intent scorer treats an empty expected value as
satisfied by silence.

**Premise.** `household_size` and `max_cooking_time_minutes` can come from a saved household instead of the
conversation (`AgentConstraintState`). A held-out run starts with no saved household, so both come from what the
conversation said. A run that starts with a saved household would break this reading.

**Value vocabularies are passed through.** `dietary_preferences` (the product has four labels), `allergens` and
`excluded_ingredients` (normalized ingredient names) are copied as the product writes them. Whether the dictionary
spells them the same way (singular or plural, `gluten-free` or `gluten_free`) is not checked here; the sealed side
checks the vocabularies against the frozen dictionary before the run (OPEN_QUESTIONS 74 (e)).

**Listed and never converted** (`unmapped_native`): a per-meal budget (the dictionary has a weekly budget with a
per-trip basis, not a per-meal one), the per-meal sodium cap (the dictionary has a daily limit and a dinner share),
`max_uses_per_recipe` (uses are not repeats), `health_preferences`, `nutrition_targets`,
`available_ingredients` (the pantry needs item-level mapping), and the saved-household block with members,
attendance and basic seasonings.

**Not produced** (`dictionary_not_produced`): `start_date`, `action`, `request_scope`, `horizon_days`, `members`,
`attendance`, `meal_structure`, `budget_basis`, `shopping_trip_days`, `perishable_window_days`, `sodium_limit_enabled`,
`sodium_limit_mg`, `dinner_sodium_share`, `allergen_avoidance_scope`, `basic_seasonings`, `pantry`,
`maximum_repeats`, `preferences`. An intent case that expects one of these cannot be scored from the product's echo
alone, and that must be reported as not scorable, not as a wrong answer.

`start_date` is not produced because the product fills a default start day when the request names none
(`agent/workflow.py`, `default_start`: today or tomorrow). The echo almost always carries a start date and cannot tell
"from Wednesday" from the default, so mapping it would report a default as stated. It is also never listed under
`unmapped_native`.

Open for the independent reviewer: whether a false halal flag should stay "not stated"; whether the per-meal
budget and sodium cap should get an agreed conversion; and the household block and pantry mappings.

```text
PYTHONPATH=backend python -m pytest backend/tests/test_field_mapping.py -p no:cacheprovider --basetemp <new-temporary-directory>
```
