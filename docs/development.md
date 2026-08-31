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
- FairPrice product search: <http://localhost:3000/products>
- Seven-day planner: <http://localhost:3000/weekly-plan>
- Backend API: <http://localhost:8000>
- Swagger documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:15432` (container-internal port remains `5432`)

The backend applies all pending Alembic migrations before starting Uvicorn.

Generated weekly plans are persisted in `meal_plans`, `meal_plan_entries`, and
`meal_plan_grocery_items`. The current migration head is `20260831_0004`.

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
