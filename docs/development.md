# Development

## Prerequisites

- Git
- Docker Desktop
- WSL 2
- Ubuntu
- Visual Studio Code
- Dev Containers extension

## Initial Setup

```bash
cp .env.example .env
```

The `.env` file is local-only and must not be committed.

## Start the Development Services

```bash
docker compose up --build --detach
```

Available services:

- Frontend: <http://localhost:3000>
- Planning assistant: <http://localhost:3000/assistant>
- FairPrice product search: <http://localhost:3000/products>
- Seven-day planner: <http://localhost:3000/weekly-plan>
- Meal check-in dashboard: <http://localhost:3000/dashboard>
- Backend API: <http://localhost:8000>
- Swagger documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:15432` (container-internal port remains `5432`)

The backend applies all pending Alembic migrations, validates and idempotently
imports the reference catalog, and then starts Uvicorn.

Generated weekly plans are persisted in `meal_plans`, `meal_plan_entries`, and
`meal_plan_grocery_items`. Meal execution status and completion timestamps are
stored on `meal_plan_entries`. Agent conversations, extracted constraints,
outstanding clarifications, and the generated-plan link are persisted in
`agent_sessions` and `agent_messages`. Replanning previews and confirmations are
stored in `meal_plan_events`; `meal_plans.revision` provides optimistic
concurrency and `meal_plan_entries.is_locked` protects selected meals. The
current migration head is `20260901_0008`. Agent replanning drafts and pending
event links are stored on `agent_sessions`.

## Planning Assistant Parser

The default `.env.example` uses `AGENT_PARSER_PROVIDER=fixture`. This mode is
deterministic, works offline, and is used in tests. It recognizes the supported
MVP constraints in common English and Chinese phrasing.

To experiment with model-based structured extraction, set these only in the
local uncommitted `.env` file:

```bash
AGENT_PARSER_PROVIDER=openai
OPENAI_API_KEY=your_local_key
OPENAI_MODEL=gpt-5.4-mini
```

The model only extracts explicit fields. The deterministic planner still owns
all hard filters, scoring, grocery calculations, and persistence. Do not commit
API keys.

## Product Pricing Modes

The planner defaults to `fixture` pricing for repeatable development and tests.
Select `live` in the UI to query FairPrice. Live responses are cached in
PostgreSQL for 15 minutes by default; selecting “Ignore cache” on the product
page requests a refresh. Configuration is available in `.env.example`.

## Inspect Service Status and Logs

```bash
docker compose ps
docker compose logs --follow backend
```

## Run Backend Quality Checks

```bash
docker compose exec backend uv run --no-sync ruff check .
docker compose exec backend uv run --no-sync ruff format --check .
docker compose exec backend uv run --no-sync pytest
```

Validate or import the catalog manually:

```bash
docker compose exec backend uv run --no-sync python -m app.data.import_catalog --validate-only
docker compose exec backend uv run --no-sync python -m app.data.import_catalog
```

Run the reproducible MVP evaluation and refresh both reports:

```bash
docker compose exec backend uv run --no-sync python -m app.evaluation
```

The evaluation covers 20 constraint combinations and fails when catalog size,
scenario feasibility, hard-constraint safety, deterministic selection,
consecutive-repeat avoidance, product mapping, or grocery completeness falls
below its gate. Results are written to `docs/evaluation/latest.json` and
`docs/evaluation/latest.md`.

## Run Frontend Quality Checks

```bash
docker compose run --rm frontend pnpm lint
docker compose run --rm frontend pnpm test
docker compose run --rm frontend pnpm typecheck
docker compose run --rm frontend pnpm build
```

## Database Migrations

Show the current revision:

```bash
docker compose exec backend uv run --no-sync alembic current
```

Apply pending migrations:

```bash
docker compose exec backend uv run --no-sync alembic upgrade head
```

## Stop the Development Services

```bash
docker compose down
```

This preserves the PostgreSQL named volume. Do not add `--volumes` unless the
development database is intentionally being discarded.
