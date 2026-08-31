# Architecture

The MVP uses a modular monolith architecture.

## Components

- Nuxt frontend
- FastAPI backend
- PostgreSQL database
- Deterministic planning engine
- LLM constraint parser
- FairPrice grocery provider adapter

## Responsibilities

The agent interprets user language and produces structured constraints.

The planning engine applies deterministic hard constraints and soft-preference
scoring.

The grocery provider retrieves and normalizes FairPrice product information.

The database stores recipes, plans, products, and meal records.

## Recipe Data Flow

The recipe catalog follows the same modular-monolith boundary intended for the
remaining features:

1. FastAPI routes validate HTTP input and output.
2. The recipe service defines pagination and response assembly.
3. The repository performs eager-loaded SQLAlchemy queries.
4. PostgreSQL stores recipes, per-serving nutrition, normalized ingredients,
   recipe quantities, and ordered cooking steps.
5. Nuxt consumes the list and detail contracts without direct database access.

## Constraint Recommendation Flow

The constraint parser contract is represented by `RecipeRecommendationRequest`.
The current form produces that structure directly; an LLM parser can later emit
the same validated object without changing the deterministic engine.

The recommendation flow is:

1. FastAPI validates normalized constraints.
2. The repository batch-loads recipes, nutrition, and ingredient relationships.
3. Hard constraints produce explicit exclusion reasons.
4. Eligible recipes receive nutrition, pantry, and time scores.
5. The grocery estimator maps scaled ingredient demand to product packages,
   deducting pantry stock only when a compatible quantity is known.
6. Complete ingredient-use estimates enforce the optional meal budget.
7. Nuxt renders rankings, grocery costs, package counts, and exclusions.

The LLM never determines allergen safety or the final constraint result.

## FairPrice Product Flow

1. The product route receives a normalized search query and pricing mode.
2. Fixture mode reads stable local product records for reproducible development.
3. Live mode first checks a time-bounded PostgreSQL cache, then parses the
   current FairPrice catalogue response when refresh is required.
4. Normalized snapshots are upserted by source, query, and external product ID.
5. A deterministic matcher ranks compatible products by ingredient tokens,
   package unit, and name similarity.
6. The estimator calculates both actual package checkout cost and prorated
   ingredient-use cost. The latter is used for the per-meal budget constraint.
7. Any live-provider failure is exposed and falls back to fixtures so the
   planning flow remains demonstrable.
