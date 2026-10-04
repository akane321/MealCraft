# Development

This guide explains how to obtain, run, inspect, test, and recover the current
MealCraft development environment. New contributors should first read the
[Project Guide](project-guide.md), [Current Status](current-status.md), and
[Contributing Guide](../CONTRIBUTING.md).

## Course Delivery Boundary

MealCraft is submitted and assessed as a locally runnable system. Cloud hosting
and a deployment guide are not course requirements. The maintained delivery
path is a clean clone followed by the documented environment setup and Docker
Compose startup below. Contributors should spend engineering effort on clean
code, reliability, scalability, core capability depth, and reproducible local
evidence before considering optional hosting.

## Prerequisites

- Git
- Docker Desktop (on Windows, with WSL 2)

Running the checks on the host instead of in containers additionally needs
Python 3.12 with `uv`, and Node 24 with `pnpm` through Corepack.

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

- Frontend home (chat with week, nutrition and shopping list panels): <http://localhost:3000>
- Service status: <http://localhost:3000/system>
- Sign in or register: <http://localhost:3000/login>
- Household profile: <http://localhost:3000/profile>
- Backend API: <http://localhost:8000>
- Swagger documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:15432` (container-internal port remains `5432`)

The backend applies all pending Alembic migrations, validates and idempotently
imports the reference catalog, and then starts Uvicorn.

The frontend container serves `./frontend` from a bind mount and reloads on
edits. Docker Desktop on Windows passes no file-change events through a bind
mount, so `compose.yaml` sets `MEALCRAFT_WATCH_POLLING=true` and the dev server
polls for changes instead (`frontend/nuxt.config.ts`). The backend's reloader
polls too (`WATCHFILES_FORCE_POLLING=true`), and only `backend/app`
(`--reload-dir app`), not the data and docs the container also mounts. A dev
server run on the host keeps native file events.

## Run a Demonstration

The development frontend carries Nuxt DevTools, whose badge sits at the bottom
centre of every page, and compiles each page on its first visit. For a
demonstration, run the frontend as a production build instead:

```bash
docker compose -f compose.yaml -f compose.demo.yaml up --build --detach
```

`compose.demo.yaml` changes only the frontend: it builds the `demo` stage of
`frontend/Dockerfile` (`pnpm build`, served by `node .output/server/index.mjs`)
without the source bind mount, so an edit needs another `--build`. It is
tagged `mealcraft-frontend-demo`, apart from the dev image. The backend,
database and URLs are as above. Return to the development frontend with
`docker compose up --detach`.

In OpenAI mode the backend loads the OpenAI library and the catalog vectors in
the background when it starts, without calling the API, so the first message
or swap after a start is not the slow one. Give it a few seconds after the
health check turns green before the first swap.

Generated weekly plans are persisted in `meal_plans`, `meal_plan_entries`, and
`meal_plan_grocery_items`. Meal execution status and completion timestamps are
stored on `meal_plan_entries`. Agent conversations, extracted constraints,
outstanding clarifications, context version, last scope decision, pending typed
interaction, and generated-plan link are persisted in `agent_sessions` and
`agent_messages`. Replanning previews and confirmations are
stored in `meal_plan_events`; `meal_plans.revision` provides optimistic
concurrency and `meal_plan_entries.is_locked` protects selected meals. The
database revision can be inspected with `docker compose exec backend uv run --no-sync alembic current`;
the version chain lives in `backend/alembic/versions/`. Household profile identity and
immutable versions are stored in `household_profiles` and
`household_profile_versions`; linked plans preserve the exact profile version
and optional replaced-plan ID. Agent replanning drafts and pending
event links are stored on `agent_sessions`.

## Authentication API

The authentication slice uses Argon2id credentials and server-side opaque
sessions. Register through Swagger or the API:

```bash
curl -i -c mealcraft.cookies -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.test","display_name":"Alice","password":"correct-horse-battery-staple"}'
```

The response contains a non-secret CSRF token and sets two cookies. The raw
session token is `HttpOnly`; only its SHA-256 digest is stored in PostgreSQL.
Use the cookie jar to resume the session:

```bash
curl -b mealcraft.cookies http://localhost:8000/api/auth/me
curl -b mealcraft.cookies http://localhost:8000/api/auth/sessions
```

Logout and device-session revocation require the returned CSRF token in the
`X-CSRF-Token` header. `AUTH_COOKIE_SECURE` is inferred as true outside
development/test; do not force it to false in a deployed environment.

The browser login page is available at <http://localhost:3000/login>. Profile,
Plan, Agent and Dashboard data require an authenticated active household
membership. Mutations require the CSRF token returned at login or registration;
the frontend sends it automatically. Repository lookups are household-scoped,
and cross-household identifiers fail as HTTP 404.

Migration `20260916_0014` places rows created before tenancy enforcement in a
reserved suspended household with no login credential. Reassign those rows only
through an explicit administrative migration; do not attach them implicitly to
a newly registered user.

## Planning Assistant Parser

The default `.env.example` uses `AGENT_PARSER_PROVIDER=fixture`. This mode is
deterministic, works offline, and is what the tests use. It recognizes the
supported current baseline constraints in common English and Chinese phrasing.

The owner's demonstration runs in OpenAI parser mode with the rule parser as
fallback: any model failure falls back to the same rules. To run that way, set
these only in the local uncommitted `.env` file:

```bash
AGENT_PARSER_PROVIDER=openai
OPENAI_API_KEY=your_local_key
OPENAI_MODEL=gpt-5.4-mini
```

The model only extracts explicit fields. The deterministic planner still owns
all hard filters, scoring, grocery calculations, and persistence. Do not commit
API keys.

The deterministic scope gate runs before either parser. Its visible bilingual
developer set is reproduced as part of the offline workbench; it is not a
held-out claim. Agent responses also expose typed interactions and reject stale
or forged option IDs through
`/api/agent/sessions/{session_id}/interactions`.

Every action after session creation can carry an `Idempotency-Key` header. Keep
one key for one intended operation and payload; a completed duplicate replays
the saved result, while conflicting or concurrent reuse returns HTTP 409. This
is especially important for confirmation calls because a browser retry must not
create a second plan revision.

Inspect the persisted execution audit through:

```bash
curl http://localhost:8000/api/agent/sessions/<session-id>/runs
curl http://localhost:8000/api/agent/sessions/<session-id>/runs/<run-id>
```

The detail response includes checkpoints, ordered tool receipts, consumed
budgets, terminal status and error/termination metadata. `used_llm_calls` counts
every request the turn sent to the OpenAI API: the parser's chat request and the
embedding request, SDK retries included. It is recorded once the turn is over,
so it never stops a turn. The console's Services page shows these model calls
beside the number of runs, the runs that went on without the model after a
request failed (fallbacks), and the model calls since the backend started that
no run records (console replays, swap previews asked of the plan API directly).
Tests use deterministic fixture parsing and zero live API calls.

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

The container's environment comes from `.env`, so it may select the OpenAI
parser and hold keys. `backend/tests/conftest.py` removes the parser, model and
key settings from the test process before any setting is read, so the suite
behaves as it does in CI. A test that needs one sets it itself.

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

Compile the leakage-resistant Evaluation v2 developer packets without calling
an external model:

```bash
docker compose exec backend uv run --no-sync python -m app.evaluation.v2_packets
```

This creates `data/evaluation/v2/dev/packets-v1.json`. The compiler fails if a
candidate recipe or product reference is unknown, or if the frozen product
snapshot does not cover every ingredient in the candidate recipe pool. These
visible packets exercise the comparison contract and must not be described as
held-out results.

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

The browser tests answer the API themselves and start their own dev server
from the checkout on port 3100, not the Compose frontend on 3000, which may be
serving older code. A server already on 3100 is an error rather than silently
reused. To test against a dev server you started yourself from this checkout,
run it on port 3100 and set `PLAYWRIGHT_REUSE_SERVER=1`.

A successful typecheck or build does not prove that the rendered interface is
usable. Inspect affected pages at the supported minimum 1280×720 desktop
viewport and check browser console errors for visible product changes. Mobile
and tablet layouts are outside the current product and evaluation scope.

## Database Migrations

### Tenancy migration verification

Migration `20260916_0014` has a destructive-schema smoke suite that runs against a dedicated PostgreSQL database. The suite creates the schema at `20260909_0013`, loads historical private rows plus two already-tenanted households, and then proves the full `upgrade -> downgrade -> upgrade` cycle.

Never point this suite at a development, shared, staging, or production database. It refuses to reset any database whose name does not end with `_migration_test`.

Run it locally with a disposable PostgreSQL database:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://mealcraft:migration_test_only@localhost:5432/mealcraft_migration_test"
$env:MEALCRAFT_MIGRATION_TEST_DATABASE_URL = $env:DATABASE_URL
uv run --project backend pytest backend/tests/migrations
```

The suite verifies all of the following before CI accepts the migration:

- historical household profiles, meal plans, Agent sessions, and Agent runs receive the suspended legacy household;
- the legacy account has no credential row and therefore cannot authenticate;
- existing Alpha and Beta household-scoped operations and audit events retain their assignments;
- tenant root columns are non-null, foreign keys and uniqueness rules exist, and lookup indexes have the expected column order;
- row counts survive downgrade and re-upgrade;
- rerunning `upgrade head` does not create duplicate legacy users, households, or memberships.

If an upgrade fails, retain the database and migration logs before changing anything. Correct the cause, then rerun `alembic upgrade head`; Alembic will continue from the recorded revision. If application compatibility requires rollback and `20260916_0014` is still the latest applied migration, run `alembic downgrade 20260909_0013`, verify that the three tenant-root columns were removed and row counts are unchanged, then retry the upgrade. Do not manually delete the suspended legacy user or household: later upgrades reuse that identity to avoid duplicate imports.

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
docker compose logs --follow database
```

### Inspect API contracts

Open <http://localhost:8000/docs>. The generated OpenAPI view is the fastest
way to inspect current request and response models. Compare material changes
with [API Contracts](api-contracts.md).

### Inspect persisted state

Use repository/service tests or a PostgreSQL client connected to
`localhost:15432`. Do not manually edit production-like data to make a test
pass; add an explicit seed, fixture, migration, or reproducible setup.

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
