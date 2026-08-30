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