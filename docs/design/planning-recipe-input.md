# Recipe details as Planning inputs

`app.planning.recipe_input.recipe_input` consumes `RecipeDetailResponse` without
database access. The caller must explicitly supply V2 `allowed_meal_types` (the
recipe's usual meal types, a soft affinity rather than a filter) and
confirm `nutrition_basis="per_serving"`. Legacy `main` is not silently mapped
to breakfast, lunch or dinner; whole-recipe nutrition is not silently divided.

The candidate uses the recipe slug as its ID. The detached source retains the
database ID, detail fields and original ingredient records. Serving count,
ingredient amounts, canonical ingredient names and units are copied without
scaling or conversion. Planning later scales quantities for each slot once.
Numeric zero is retained; unknown quantity remains `None`.

Allergen labels are the sorted union of non-null ingredient allergen fields.
The source schema has no completeness flag: null labels and an empty resulting
list do not certify reviewed allergen safety. Source review and completeness
remain responsibilities described in the [recipe data contract](recipe-ingredient-data.md).
Dietary tags are copied for the existing compiler to interpret.

Nonfinite facts, blank identities and values rejected by the target schema
produce field-oriented issues with no candidate. Numeric values and raw error
messages are not included in those issues. Invalid original facts may remain in
the detached source for diagnosis; do not serialize them into valid-data JSON
responses. No truncation or invented defaults are used to fit the target schema.

An empty issue list establishes only conversion compatibility. The caller must
retain catalog version, provenance and eligibility/basis evidence, check IDs
across the complete candidate pool, and pass the assembled problem through
planning and independent validation. This function does not translate legacy
budgets or user nutrition targets, persist a plan, or implement a public route.
