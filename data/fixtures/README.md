# Fixtures

This directory contains stable sample data used for independent module
development and automated testing.

Fixture files:

- `fairprice-products.json`: stable FairPrice-shaped products used for deterministic development and tests.
- `planning-v2/final-scope-multislot.json`: final-scope algorithm integration
  packet with explicit multi-meal slots, nutrition bands, pantry states,
  product packages and a purchase budget. It is a scaffold fixture, not a
  representative evaluation dataset.
- `backend-platform/identity-scope.json`: synthetic account, household and
  expected-access cases for authorization and cross-tenant testing. It contains
  no usable password, token or personal information.
- `agent-orchestration/scope-and-grounding-v1.json`: synthetic scope and claim
  examples for independent orchestration development. It freezes starter
  semantics only and is not a final multilingual or hallucination benchmark.

Reference data is deliberately separated from database migrations:

- `../ingredients/ingredients.json`: normalized ingredient vocabulary and allergens.
- `../recipes/recipes.json`: complete recipe, nutrition, ingredient, and step records.
- `../evaluation/scenarios.json`: representative feasible and infeasible user requests.

The startup importer validates cross-file references and performs an idempotent
upsert. Fixture prices are reproducible test inputs; the application still
supports an explicit live FairPrice lookup mode.

## Why there are two FairPrice snapshots

`fairprice-products.json` is frozen. Protocol v1's committed reports were
computed against it, and `ADR-0020` section 3 forbids rewriting a condition that
has already been reported: adding a cheaper package size changed one baseline
case from over-budget to within-budget, which is a real change to a published
number.

`fairprice-products-v2.json` is the same catalog plus several package sizes for
the ingredients recipes lean on most, and it is what the v2 held-out set and its
packets use.

That difference is the point rather than an accident. Real supermarkets sell one
ingredient in several sizes, and until this snapshot carried any, the
mixed-package planner merged in `ADR-0021` could not be exercised at all outside
its own developer fixture. Where the snapshot has one size per ingredient, that
is a limit of what has been captured from FairPrice, not evidence that mixing is
unnecessary.

