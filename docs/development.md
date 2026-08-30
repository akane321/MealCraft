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

- Backend API: <http://localhost:8000>
- Swagger documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5432`

The backend applies all pending Alembic migrations before starting Uvicorn.

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
