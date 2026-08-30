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
