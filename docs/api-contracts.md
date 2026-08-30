# API Contracts

The system will define the following shared objects:

- UserConstraints
- Recipe
- Ingredient
- Nutrition
- FairPriceProduct
- MealPlan
- ShoppingList

Available endpoints:

- GET /api/health
- GET /api/info
- GET /api/recipes?limit=20&after_id={recipe_id}
- GET /api/recipes/{slug}

## Recipe Catalog

The recipe list uses keyset pagination. `next_cursor` is the last visible recipe
ID when another page is available; clients pass it back as `after_id`.

A recipe detail contains:

- identity, title, slug, cuisine, meal type, serving count, and preparation time
- dietary tags
- nutrition values per serving
- normalized ingredients, amounts, preparation notes, and allergen labels
- ordered cooking steps

Nutrition values are descriptive planning data. They are not medical advice.
