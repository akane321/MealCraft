# MealCraft

MealCraft is a constraint-aware weekly dietary planning application developed for
DSS5105 Data Science Projects in Practice.

## MVP Goal

The system accepts user dietary constraints, generates a seven-day meal plan,
maps required ingredients to FairPrice products, produces a grocery list, and
visualizes planned-meal nutrition through a dashboard.

## Technology Stack

- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy
- Frontend: Nuxt 4, Vue 3, TypeScript
- Database: PostgreSQL
- Python package management: uv
- Frontend package management: pnpm
- Infrastructure: Docker Compose
- Backend testing: Pytest
- Frontend testing: Vitest

## Repository Structure

- `backend/`: backend API and business logic
- `frontend/`: Nuxt frontend application
- `data/fixtures/`: stable development fixtures
- `docs/`: architecture, MVP boundary, and API contracts
- `.github/workflows/`: continuous integration

## Current Status

The full-stack development environment is operational. The first business
vertical slice provides a PostgreSQL recipe catalog, FastAPI list/detail APIs,
and responsive Nuxt recipe pages. The constraint-matching slice adds a
deterministic recommendation API and an explainable planning form.

## Quick Start

```bash
cp .env.example .env
docker compose up --build --detach
```

- Backend API: <http://localhost:8000>
- Frontend: <http://localhost:3000>
- Recipe catalog: <http://localhost:3000/recipes>
- Constraint matching: <http://localhost:3000/plan>
- Swagger documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/health>
