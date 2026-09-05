# MealCraft Architecture

## Scope and Evidence Boundary

This document explains the implemented architecture and the direction required
to reach the final product described in [Project Guide](project-guide.md).
Components marked as targets are not current runtime behaviour. Generated
OpenAPI, source code, migrations, and tests remain the authority for exact
implementation details.

## Architectural Thesis

MealCraft separates probabilistic language understanding from deterministic
planning and arithmetic:

```text
LLM understanding and explanation
              +
grounded recipe and grocery retrieval
              +
deterministic planning, calculation and validation
              +
versioned persistence and repeatable evaluation
```

The Agent is an orchestrator, not the authority for safety, nutrition, cost, or
Shopping List correctness.

## System Context

```text
                         optional
                    +--------------+
                    |  OpenAI API  |
                    +------+-------+
                           |
+------+      +-------------v--------------+      +----------------+
| User | <--> | MealCraft Web Application  | <--> | FairPrice Web  |
+------+      | Nuxt + FastAPI + Services  |      +----------------+
              +-------------+--------------+      +----------------+
                            |              <----> | YouTube API    |
                     +------v-------+              +----------------+
                     | PostgreSQL   |
                     +--------------+
```

External services are optional at development and evaluation time. Fixture mode
must keep the core flow runnable without an API key or live retailer response.

## Runtime Containers

| Container | Technology | Responsibility |
| --- | --- | --- |
| Frontend | Nuxt 4, Vue 3, TypeScript | Product navigation, forms, Assistant, plans, recipes, products, Shopping List, Dashboard, and replanning interaction |
| Backend | Python 3.12, FastAPI, Pydantic | HTTP contracts, orchestration, deterministic services, external adapters, and evaluation entry points |
| Database | PostgreSQL | Profiles and versions, recipes, ingredients, products/cache, plans, entries, grocery items, events, check-ins, and Agent sessions |
| External provider | FairPrice public catalogue | Current product, package, and observed-price information |
| Optional tutorial provider | YouTube Data API | Bounded tutorial candidates after recipe selection; only one deterministic Top-1 reaches the user |
| Optional model provider | OpenAI through structured parsing | Explicit field extraction when locally enabled; never the calculator or validator |

Docker Compose provides the local integration boundary. The backend applies
Alembic migrations and idempotently validates/imports the reference catalog at
startup.

## Backend Layers

```text
backend/app/api/
    HTTP routes, request parsing, response models
             |
backend/app/services/
    application workflows and deterministic domain logic
             |
backend/app/repositories/
    persistence queries and transaction boundaries
             |
backend/app/models/ and backend/app/schemas/
    database representation and validated contracts
             |
PostgreSQL and external provider adapters
```

Routes should not duplicate planning or calculation logic. Services should not
depend on frontend presentation. Repositories should not decide product policy.

## Current Responsibility Boundaries

### Household profile

- Maintains one shared household profile in the verified baseline.
- Sums member servings for the shared plan.
- Applies the union of member allergens, prohibited ingredients, and diet
  requirements as hard constraints.
- Stores immutable versions and links every profile-generated plan to the exact
  version.
- Creates a replacement plan rather than rewriting history after profile change.

### Agent

- Persists conversations and structured constraint state.
- Extracts only explicit user information.
- Identifies material missing information and asks a focused clarification.
- Calls deterministic planning or replanning services after confirmation.
- Explains tool results without replacing their numeric output.

Fixture parsing is the default. OpenAI parsing is optional and requires a local
runtime key.

### Recipe knowledge

- Uses versioned recipe and normalized ingredient data as the trusted current
  catalog.
- Validates and imports data idempotently.
- Provides structured fields used by retrieval, planning, nutrition,
  aggregation, display, and evaluation.

Validated external recipe supplementation and semantic retrieval are final
design targets, not verified current capabilities.

### Planner and validator

- Compiles structured household and request constraints.
- Rejects hard violations.
- Scores eligible recipes using soft preferences.
- Selects a seven-day main-meal plan and avoids consecutive repetition when
  alternatives exist.
- Scales servings and aggregates per-person nutrition.
- Reports infeasibility instead of manufacturing a valid-looking result.

Hard constraints, soft penalties, tolerance policies, and output explanations
must remain explicit and testable.

### Grocery provider and Shopping engine

- Maps normalized ingredients to FairPrice-shaped products.
- Supports live lookup, PostgreSQL cache, and deterministic fixture modes.
- Records product packages and prices used for calculation.
- Aggregates repeated ingredient demand across the final plan.
- Deducts only known, compatible pantry quantities.
- Rounds remaining demand to purchasable packages.
- Keeps estimated use value and package checkout cost distinguishable.

### Dashboard

- Stores each plan entry as `planned`, `completed`, or `skipped`.
- Includes only completed MealCraft entries in actual nutrition totals.
- Displays daily totals, weekly trends, and logging coverage.
- Never infers off-plan food.

### Replanning

- Persists a preview before mutation.
- Ties the preview to a plan revision for optimistic concurrency.
- Protects completed and locked entries.
- Applies a confirmed local change and recalculates downstream grocery demand.
- Preserves event history and exposes before/after differences.

### Evaluation

- Uses physically separated developer, held-out, and Agent datasets.
- Uses deterministic fixtures by default.
- Compares methods under the same candidate pool and inputs.
- Stores dataset version and digest, category metrics, and case-level failures.
- Keeps paid API execution behind explicit provider and opt-in flags.

## Core Runtime Flows

### Profile-driven planning

```text
Nuxt profile form
 -> FastAPI profile route
 -> validate member and shared fields
 -> append immutable profile version
 -> compile effective constraints
 -> deterministic weekly planner
 -> grocery mapping and Shopping List
 -> persist plan with profile version
 -> return plan, validation, nutrition and grocery results
```

### Agent-driven planning

```text
User message
 -> persist message
 -> fixture or optional model parser
 -> Pydantic-validated constraint state
 -> clarification when materially incomplete
 -> user confirmation
 -> deterministic planner and validator
 -> persist and return authoritative plan
```

The Agent does not construct an unvalidated Shopping List in its response.

### Grocery lookup and fallback

```text
Normalized ingredient query
 -> check requested mode
 -> recent PostgreSQL cache when eligible
 -> FairPrice lookup when live refresh is required
 -> normalize product and package fields
 -> visible fallback when live data is unavailable
 -> fixture path for repeatable tests and demos
```

The response must preserve source mode and freshness so fallback data is not
presented as current live data.

FairPrice live retrieval is demand-driven: it begins only after a validated
plan or Shopping List identifies remaining canonical ingredient demand. It must
not become a broad background catalog crawl.

### Recipe tutorial lookup

```text
Selected canonical recipe
 -> deterministic query builder
 -> bounded YouTube candidates or fixture
 -> eligibility filter and scored ranking
 -> one Top-1 tutorial plus retrieval trace
 -> Recipe Side Panel
```

Candidate evidence and score components remain internal for evaluation. Video
content is execution support and cannot overwrite MealCraft ingredients,
quantities, allergens, nutrition, or written steps. Provider failure returns a
typed degraded or unavailable state rather than an invented recommendation.

### Check-in and Dashboard

```text
Entry status update
 -> validate transition
 -> persist status and completion timestamp
 -> load authoritative plan entries
 -> aggregate completed MealCraft nutrition
 -> return daily totals, weekly trend and coverage
```

Repeated status updates are idempotent.

### Replanning

```text
User event
 -> identify target plan entry and intent
 -> validate lock/completion/revision conditions
 -> generate deterministic alternative and downstream deltas
 -> persist preview
 -> user confirms or discards
 -> on confirm, apply local change and increment revision
 -> recompute Shopping List and expose event history
```

## Data Ownership and Traceability

| Data | Authoritative owner | Traceability requirement |
| --- | --- | --- |
| Household constraints | Profile version plus request override | Profile ID, version, effective snapshot |
| Recipe and ingredient facts | Validated catalog | Stable IDs, schema validation, source where available |
| Parsed request | Agent session state | User message, parser mode, validated structured output |
| Plan | Deterministic planning service | Effective constraints, selected recipes, revision, replacement link |
| Product and price | Grocery provider/cache/fixture | Provider, source mode, package, observed price, timestamp |
| Tutorial candidate and selection | Tutorial provider plus deterministic ranker | Query, provider mode, candidate count, ranking policy, selected video ID, timestamp, warnings |
| Shopping List | Shopping engine | Derivable from final plan, pantry state, and product packages |
| Dashboard actuals | Persisted plan-entry status | Completed entries and coverage |
| Evaluation result | Evaluation workbench | Code revision, dataset path/digest, method, metrics, failures |

## Design-time Module Contracts

Runtime architecture is complemented by the [Design Contracts](design/README.md).
They identify the producer, consumer, versioned artifact, missing-data policy
and evaluation-readiness gate for recipe data, FairPrice grounding, planning,
Agent orchestration, frontend evidence and Evaluation v2.

The detailed provider, evidence-packet, Top-1, degradation and teammate
contracts are defined in
[External Retrieval and RAG](design/external-retrieval-rag.md).

The core dependency chain is:

```text
recipe/ingredient facts ----+----> candidate retrieval ----> planner
                            |                                |
FairPrice observations ----> ingredient-product mapping ----+----> Shopping List
                                                             |
user request ----> Agent state/clarification ----------------+
                                                             |
all frozen inputs and traces --------------------------------+----> Evaluation
```

Consumers may develop against versioned fixtures, but a fixture assumption does
not become a production fact. A downstream claim is enabled only after the
upstream schema, provenance, unknown semantics and validation evidence exist.

## Final-Design Extensions

The architecture should evolve toward the product baseline without mislabelling
targets as current behaviour:

- authentication and user separation appropriate to deployment;
- a larger high-dimensional recipe and nutrition catalog;
- validated external recipe ingestion;
- semantic retrieval followed by metadata filtering;
- a unified recipe execution side panel with provenance and optional tutorial
  support;
- source-aware elastic nutrition policy and deeper nutrition evaluation;
- broader dynamic-event semantics and disruption metrics;
- operations views for health, data quality, product mapping, plan trace, Agent
  trace, and evaluation runs.

Each extension must define contracts, failure behaviour, tests, evaluation
evidence, and a fallback strategy before it is treated as complete.

## Security, Privacy, and Reproducibility

- Never commit `.env`, API keys, cookies, tokens, personal health data, or raw
  private-memory content.
- Treat allergens and prohibited ingredients as deterministic safety boundaries.
- Keep live external data separate from frozen evaluation snapshots.
- Store no clinical diagnosis or treatment claim.
- Database changes require Alembic migrations.
- Contract changes require API and architecture documentation updates.
- Current behaviour is verified by code and tests; roadmap text is not evidence.
