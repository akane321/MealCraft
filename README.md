# Dietary Planner MVP

A constraint-aware weekly dietary planning application developed for
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

The FastAPI backend, PostgreSQL database, Alembic migrations, and Docker
Compose development environment are operational.

## Quick Start

```bash
cp .env.example .env
docker compose up --build --detach
```

- Backend API: <http://localhost:8000>
- Frontend: <http://localhost:3000>
- Swagger documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/health>
