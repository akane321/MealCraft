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
- POST /api/recommendations/recipes
- GET /api/products/search?q={query}&live={boolean}&refresh={boolean}

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

## Recipe Recommendations

`POST /api/recommendations/recipes` accepts a structured planning request with:

- household size and maximum cooking time
- allergens, excluded ingredient IDs, and dietary requirements
- optional health preferences and user-entered nutrition targets
- an optional explicit sodium ceiling
- available ingredients with optional quantities and units
- an optional per-meal budget and `fixture` or `live` pricing mode

Hard filters remove recipes that violate allergens, excluded ingredients,
dietary requirements, cooking-time limits, an explicit sodium ceiling, or a
complete ingredient-use estimate above the user-entered budget.

Eligible recipes receive an explainable weighted score:

- nutrition alignment: 45%
- available-ingredient coverage: 30%
- cooking time: 25%

Inactive score dimensions are removed from the denominator. Low-sodium uses a
flexible 700 mg per-meal benchmark and gradually reduces the nutrition score up
to 1400 mg; it does not remove a recipe unless the user enters a hard ceiling.

Each retained recommendation contains a grocery estimate with the matched
product, required packages, checkout total, ingredient-use total, pantry
deduction, surplus quantity, mapping completeness, and budget result.

## Product Search

`GET /api/products/search` supports two explicit modes:

- `live=false`: deterministic FairPrice-shaped fixtures for tests and demos
- `live=true`: current FairPrice catalogue lookup with a 15-minute PostgreSQL cache

`refresh=true` bypasses a fresh cache entry. If a live lookup fails, the API
returns fixture results with `fallback_used=true` and a warning; the source is
never silently misrepresented.
