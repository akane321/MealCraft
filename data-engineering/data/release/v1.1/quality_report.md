# Data Release v1.1

Generated 2026-09-17T12:03:10+00:00 from pipeline revision `244a84cf7da0723749f2502570a2f921b65f5d99`.

## Scope

- Upstream recipes scanned: 1642647
- Released (four-condition eligible): 9282 (0.565%)
- Released canonical ingredients: 465
- Servings basis: {'stated_exact': 6458, 'range_lower_bound': 2824}

## Release gate

See `docs/schema-v1-freeze.md`. Every released recipe has every ingredient mapped, quantified, and unit-anchored (mass/volume/count), and a non-null servings count.

## Known gaps

- nutrition.status is not_computed for every released recipe (no reviewed USDA mapping or quantity-to-mass conversion yet)
- allergen labels are deterministic-rule-only; no independently reviewed gold subset exists yet (see docs/schema-v1-freeze.md)
- cuisine/meal_types/methods/equipment/difficulty are empty for every released recipe; no controlled vocabulary exists yet
- dietary_tags (dairy-free/gluten-free/vegetarian/vegan) are derived only, not independently reviewed: {'dairy-free': 3602, 'gluten-free': 4507, 'vegan': 1030, 'vegetarian': 5625} of released recipes carry a positive tag; a recipe with any unmapped ingredient carries none, by design (see scripts/derive_dietary_tags.py)
- servings_basis == 'range_lower_bound' rows carry an estimated, not stated, servings count (see src/servings.py)
