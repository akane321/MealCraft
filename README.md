# MealCraft

MealCraft is a constraint-aware weekly dietary planning application developed for
DSS5105 Data Science Projects in Practice.

## Product Goal and Minimum Baseline

MealCraft targets a polished, evidence-backed final product. The MVP is the minimum acceptance baseline, not a scope or quality ceiling. Once a capability meets the baseline, development continues toward stronger user value, reliability, usability, evaluation evidence, and engineering quality according to priority, risk, and available time.

The system accepts user dietary constraints, generates a seven-day meal plan,
maps required ingredients to FairPrice products, produces a grocery list,
supports previewed event-driven plan adjustments, and visualizes planned and
completed MealCraft nutrition through a dashboard.

## Technology Stack

- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy
- Frontend: Nuxt 4, Vue 3, TypeScript
- Database: PostgreSQL
- Python package management: uv
- Frontend package management: pnpm
- Infrastructure: Docker Compose
- Backend testing: Pytest
- Frontend testing: Vitest
- Agent orchestration: LangGraph
- Optional language parser: OpenAI structured outputs through LangChain

## Repository Structure

- `backend/`: backend API and business logic
- `frontend/`: Nuxt frontend application
- `data/ingredients/` and `data/recipes/`: validated reference catalog
- `data/fixtures/`: stable FairPrice-shaped products
- `data/evaluation/`: repeatable planning scenarios
- `docs/`: architecture, MVP boundary, and API contracts
- `.github/workflows/`: continuous integration
- `AGENTS.md`: cross-agent work protocol and private shared-memory bootstrap
- `docs/memory-bootstrap.md`: cross-device setup and daily memory workflow

## Current Status

The full-stack development environment is operational. The first business
vertical slice provides a PostgreSQL recipe catalog, FastAPI list/detail APIs,
and responsive Nuxt recipe pages. The constraint-matching slice adds a
deterministic recommendation API and an explainable planning form. The product
slice queries the current FairPrice catalogue with a PostgreSQL cache and an
explicit fixture fallback, maps ingredients to package sizes, and enforces the
per-meal budget using estimated ingredient-use cost. The weekly-planning slice
persists a seven-day main-meal schedule, avoids consecutive repetition where
possible, aggregates per-person nutrition, and produces one consolidated,
package-aware shopping list with a weekly budget result. The meal-execution
slice lets users mark each planned dish as planned, completed, or skipped, and
visualizes completed MealCraft dishes through daily nutrition totals, weekly
trends, and completion progress. The planning-assistant slice persists every
conversation and its structured constraint state, asks targeted clarification
questions, and invokes the deterministic weekly planner only after confirmation.
It runs without an API key in reproducible fixture mode; OpenAI parsing is an
explicit optional configuration.
The dynamic-replanning slice adds revision-safe previews for meal replacement,
cancellation, locking, and unavailable ingredients. Confirmed changes update
only the target meal and its derived shopping demand, while an event trail keeps
the before/after decision auditable.
The agent-replanning slice closes the interaction loop: users can request one
change in English or Chinese inside the existing Assistant conversation, answer
a focused clarification when needed, inspect recipe, nutrition, Shopping List,
and price deltas, then confirm or discard the persistent preview. The Agent
delegates every calculation and mutation to the deterministic replanning engine.
The data-quality and evaluation slice expands the validated catalog to 30
recipes and 34 normalized ingredients, provides complete fixture product
mappings, imports the catalog idempotently at startup, and gates changes through
20 developer scenarios. A separate 40-case held-out set compares a transparent
greedy baseline with the MealCraft weekly planner, while a 24-case offline Agent
benchmark records extraction, clarification and medical-boundary behaviour.
The household-profile slice persists member-level servings and safety
constraints together with shared budget, time, nutrition, pricing, and pantry
defaults. Every edit creates an immutable version. Plans generated from a
profile record the exact version and a replacement plan explains which
constraint groups changed.

## Quick Start

```bash
cp .env.example .env
docker compose up --build --detach
```

The backend validates and imports the reference catalog after migrations, so a
fresh environment and an existing environment converge on the same records.

- Backend API: <http://localhost:8000>
- Frontend: <http://localhost:3000>
- Planning assistant: <http://localhost:3000/assistant>
- Household profile: <http://localhost:3000/profile>
- Recipe catalog: <http://localhost:3000/recipes>
- Constraint matching: <http://localhost:3000/plan>
- Seven-day planning: <http://localhost:3000/weekly-plan>
- Meal check-in dashboard: <http://localhost:3000/dashboard>
- FairPrice product search: <http://localhost:3000/products>
- Swagger documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/health>

## Evaluation

The versioned method and metric definitions are documented in
[docs/evaluation/protocol-v1.md](docs/evaluation/protocol-v1.md). Run the
developer quality gate and the complete offline workbench from the repository
root:

```bash
uv run --project backend python -m app.evaluation
uv run --project backend python -m app.evaluation.workbench
```

The generated comparison and failure registry are written to
[`docs/evaluation/workbench/latest.md`](docs/evaluation/workbench/latest.md).
Both commands use fixtures and make no paid API call. The optional OpenAI Agent
benchmark is reserved behind two explicit command-line switches and a runtime
environment variable; it is not used by CI or the committed protocol-v1 report.

Frontend state tests run with `pnpm test`; browser acceptance tests run with
`pnpm test:e2e` after installing the Playwright Chromium browser.

## Shared Project Memory

Approved team members use the private `MealCraft-Knowledge` repository as the
versioned source for project decisions, course requirements, current state,
risks, and task history. Read [docs/memory-bootstrap.md](docs/memory-bootstrap.md)
before the first material contribution. The private repository is intentionally
kept separate from this public source repository and is never required to run
the application.
