# Data Release v1

Generated 2026-09-14T10:24:51+00:00 from pipeline revision `244a84cf7da0723749f2502570a2f921b65f5d99`.

## Scope

- Upstream recipes scanned: 1642647
- Released (four-condition eligible): 8718 (0.531%)
- Released canonical ingredients: 443
- Servings basis: {'stated_exact': 6074, 'range_lower_bound': 2644}

## Release gate

See `docs/schema-v1-freeze.md`. Every released recipe has every ingredient mapped, quantified, and unit-anchored (mass/volume/count), and a non-null servings count.

## Known gaps

- nutrition.status is not_computed for every released recipe (no reviewed USDA mapping or quantity-to-mass conversion yet)
- allergen labels are deterministic-rule-only; no independently reviewed gold subset exists yet (see docs/schema-v1-freeze.md)
- cuisine/meal_types/methods/equipment/difficulty/dietary_tags are empty for every released recipe; no controlled vocabulary exists yet
- servings_basis == 'range_lower_bound' rows carry an estimated, not stated, servings count (see src/servings.py)
