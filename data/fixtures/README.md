# Fixtures

This directory contains stable sample data used for independent module
development and automated testing.

Fixture files:

- `fairprice-products.json`: stable FairPrice-shaped products used for deterministic development and tests.

Reference data is deliberately separated from database migrations:

- `../ingredients/ingredients.json`: normalized ingredient vocabulary and allergens.
- `../recipes/recipes.json`: complete recipe, nutrition, ingredient, and step records.
- `../evaluation/scenarios.json`: representative feasible and infeasible user requests.

The startup importer validates cross-file references and performs an idempotent
upsert. Fixture prices are reproducible test inputs; the application still
supports an explicit live FairPrice lookup mode.
