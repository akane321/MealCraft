# Development

This guide explains how to obtain, run, inspect, test, and recover the current
MealCraft development environment. New contributors should first read the
[Project Guide](project-guide.md), [Current Status](current-status.md), and
[Contributing Guide](../CONTRIBUTING.md).

## Prerequisites

- Git
- Docker Desktop
- WSL 2
- Ubuntu
- Visual Studio Code
- Dev Containers extension

## Initial Setup

Clone the repository into a normal development directory. Do not download a ZIP
if the clone will be used for team contribution:

```bash
git clone https://github.com/akane321/MealCraft.git
cd MealCraft
git switch main
git pull --ff-only origin main
```

Create the local environment file:

```bash
cp .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

The `.env` file is local-only and must not be committed.

## Start the Development Services

```bash
docker compose up --build --detach
```

Available services:

- Frontend: <http://localhost:3000>
- Planning assistant: <http://localhost:3000/assistant>
- Household profile: <http://localhost:3000/profile>
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
current migration head is `20260902_0009`. Household profile identity and
immutable versions are stored in `household_profiles` and
`household_profile_versions`; linked plans preserve the exact profile version
and optional replaced-plan ID. Agent replanning drafts and pending
event links are stored on `agent_sessions`.

## Planning Assistant Parser

The default `.env.example` uses `AGENT_PARSER_PROVIDER=fixture`. This mode is
deterministic, works offline, and is used in tests. It recognizes the supported
current baseline constraints in common English and Chinese phrasing.

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

Run the reproducible baseline evaluation and refresh both reports:

```bash
docker compose exec backend uv run --no-sync python -m app.evaluation
docker compose exec backend uv run --no-sync python -m app.evaluation.workbench
```

The evaluation covers 20 constraint combinations and fails when catalog size,
scenario feasibility, hard-constraint safety, deterministic selection,
consecutive-repeat avoidance, product mapping, or grocery completeness falls
below its gate. Results are written to `docs/evaluation/latest.json` and
`docs/evaluation/latest.md`. The workbench additionally runs the held-out
planner comparison and offline Agent fixture benchmark and writes
`docs/evaluation/workbench/latest.json` and `latest.md`. Both commands are
fixture-only by default and do not make a paid API call.

## Run Frontend Quality Checks

```bash
docker compose run --rm frontend pnpm lint
docker compose run --rm frontend pnpm test
docker compose run --rm frontend pnpm typecheck
docker compose run --rm frontend pnpm build
```

Run browser acceptance tests when a desktop user journey or visible state changes:

```bash
cd frontend
pnpm exec playwright install chromium
pnpm test:e2e
```

A successful typecheck or build does not prove that the rendered interface is
usable. Inspect affected pages at the supported minimum 1280×720 desktop
viewport and check browser console errors for visible product changes. Mobile
and tablet layouts are outside the current product and evaluation scope.

## Database Migrations

Show the current revision:

```bash
docker compose exec backend uv run --no-sync alembic current
```

Apply pending migrations:

```bash
docker compose exec backend uv run --no-sync alembic upgrade head
```

## Debugging and Inspection

### Follow logs

```bash
docker compose logs --follow backend
docker compose logs --follow frontend
docker compose logs --follow db
```

### Inspect API contracts

Open <http://localhost:8000/docs>. The generated OpenAPI view is the fastest
way to inspect current request and response models. Compare material changes
with [API Contracts](api-contracts.md).

### Inspect persisted state

Use repository/service tests or a PostgreSQL client connected to
`localhost:15432`. Do not manually edit production-like data to make a test
pass; add an explicit seed, fixture, migration, or reproducible setup.

### Work in a Dev Container

Open the repository folder in VS Code after Docker Desktop and WSL 2 are ready.
Use **Dev Containers: Reopen in Container** when the repository configuration is
detected. If the command is absent, confirm that the Dev Containers extension is
installed and that the repository root, not a parent directory, is open.

## Common Problems

### A service is unhealthy or a page cannot reach the API

```bash
docker compose ps
docker compose logs --tail 200 backend
```

Verify <http://localhost:8000/api/health>, then inspect the backend log before
changing application code.

### A local port is already in use

Check which application owns ports `3000`, `8000`, or `15432`, stop the stale
process or container, and restart Compose. Do not silently change committed
ports for one machine.

### Migrations and local database state disagree

```bash
docker compose exec backend uv run --no-sync alembic current
docker compose exec backend uv run --no-sync alembic upgrade head
```

Preserve the database volume unless discarding local data is intentional. Never
use `docker compose down --volumes` as a routine troubleshooting step.

### FairPrice live lookup is unavailable

Use fixture mode to continue deterministic development. Record and expose the
degraded state; do not label cache or fixture data as a successful fresh lookup.

### The optional model parser is unavailable

Return to `AGENT_PARSER_PROVIDER=fixture`. A missing key or provider response
must not prevent deterministic development, CI, or evaluation.

## Stop the Development Services

```bash
docker compose down
```

This preserves the PostgreSQL named volume. Do not add `--volumes` unless the
development database is intentionally being discarded.
