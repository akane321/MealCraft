# MealCraft

MealCraft is an explainable, constraint-aware weekly meal-planning system that
turns household requirements and real grocery information into a validated meal
plan and an actionable Shopping List.

It is developed for **DSS5105 Data Science Projects in Practice**. The project
targets a polished, evidence-backed final product: the current MVP is a minimum
acceptance baseline, not the scope or quality ceiling.

## Product Vision

MealCraft addresses a planning problem that ordinary recipe search and one-shot
LLM generation do not solve reliably. A useful weekly plan must coordinate
dietary restrictions, allergens, budget, cooking time, serving size, optional
nutrition targets, existing ingredients, real product packages, and changing
user decisions without losing numerical consistency.

The intended product journey is:

```text
Household profile and natural-language request
                    |
          Agent parsing and clarification
                    |
       Grounded recipe candidate retrieval
                    |
   Deterministic planning, calculation and validation
                    |
     FairPrice products, packages and observed prices
                    |
       Validated weekly plan and Shopping List
                    |
          Check-in, Dashboard and replanning
```

The LLM may interpret intent, request clarification, select tools, and explain
results. It does **not** own allergen decisions, constraint validation, nutrition
arithmetic, package quantities, cost calculation, or Shopping List derivation.
Those operations remain deterministic and testable.

## Current Verified Capabilities

| Capability | Current implementation |
| --- | --- |
| Household profile | One shared household profile with member servings, safety constraints, shared defaults, and immutable versions |
| Planning assistant | Persistent English/Chinese conversations, structured constraint state, targeted clarification, confirmation, and tool delegation |
| Weekly planning | Persisted seven-day main-meal plans with hard filtering, soft ranking, diversity control, and per-person nutrition |
| Grocery grounding | FairPrice product lookup with normalized packages, PostgreSQL cache, and reproducible fixtures |
| Shopping List | Consolidated ingredient demand, known-quantity pantry deduction, package rounding, and budget results |
| Plan execution | `planned`, `completed`, and `skipped` check-in states |
| Nutrition Dashboard | Daily totals, weekly trends, and completion coverage for completed MealCraft dishes only |
| Replanning | Revision-safe preview, confirmation or discard, local meal changes, Shopping List deltas, and event history |
| Evaluation | Versioned developer, held-out, and Agent fixtures; greedy baseline; failure registry; frontend state and browser tests |

This table reports capabilities verified on remote `main`, not every final
design target. Read [Current Status](docs/current-status.md) for the evidence
boundary, known limitations, and next gaps.

## Product Boundaries

- Allergens, prohibited ingredients, incompatible diet types, and explicit
  user-entered limits are validated as constraints.
- Lower-sodium, lower-sugar, lower-calorie, nutrition alignment, variety, and
  pantry use are general planning preferences unless the user supplies an
  explicit numeric ceiling.
- Calorie and macronutrient targets are used only when entered by the user.
  MealCraft does not calculate BMR/TDEE or prescribe weight-loss or muscle-gain
  targets.
- Dashboard totals include completed MealCraft dishes only. Off-plan food is not
  inferred or recorded.
- A known pantry quantity may reduce purchase demand. An unknown quantity may
  influence recipe ranking but is never silently deducted.
- MealCraft does not provide clinical nutrition, diagnosis, disease treatment,
  or medically tailored diet planning.
- Complete inventory management, waste prediction, multi-store price
  comparison, ordering, and payment are not part of the verified baseline.

See [MVP Boundary](docs/mvp-boundary.md) for precise current semantics and
[Project Guide](docs/project-guide.md) for the final product direction.

## Technology Stack

- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic
- Frontend: Nuxt 4, Vue 3, TypeScript
- Database: PostgreSQL
- Agent orchestration: LangGraph-style state and tool orchestration
- Optional language parser: OpenAI structured output through LangChain
- Package management: uv and pnpm
- Infrastructure: Docker Compose
- Quality: Ruff, Pytest, ESLint, Vitest, Playwright, GitHub Actions

The initial proposal mentioned alternative frameworks such as Next.js and
Supabase. Nuxt, FastAPI, and PostgreSQL are intentional implementation choices
that preserve the same product responsibilities.

## Repository Map

```text
backend/app/api/          HTTP routes and request boundaries
backend/app/services/     deterministic application and domain services
backend/app/repositories/ persistence adapters
backend/app/evaluation/   repeatable evaluation workbench
frontend/app/pages/       user-facing product routes
frontend/app/components/  reusable interface components
data/recipes/             versioned recipe catalog
data/ingredients/         normalized ingredient catalog
data/fixtures/            reproducible grocery fixtures
data/evaluation/          versioned evaluation inputs
docs/                     product, architecture, operation and evaluation docs
.github/                   CI, issue, PR and ownership configuration
```

## Quick Start

Prerequisites: Git, Docker Desktop with WSL 2, and Docker Compose. Clone the
repository, then run from the repository root:

```bash
cp .env.example .env
docker compose up --build --detach
docker compose ps
```

PowerShell users can create the local environment file with:

```powershell
Copy-Item .env.example .env
```

The backend applies pending migrations, validates and imports the reference
catalog idempotently, and starts the API. The local `.env` file must never be
committed.

### Local entry points

- Product home: <http://localhost:3000>
- Planning assistant: <http://localhost:3000/assistant>
- Household profile: <http://localhost:3000/profile>
- Recipe catalog: <http://localhost:3000/recipes>
- Constraint matching: <http://localhost:3000/plan>
- Seven-day planning: <http://localhost:3000/weekly-plan>
- Meal check-in Dashboard: <http://localhost:3000/dashboard>
- FairPrice product search: <http://localhost:3000/products>
- Backend API: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/health>

Follow the [User Guide](docs/user-guide.md) for the product workflow and the
[Development Guide](docs/development.md) for setup, testing, debugging, pricing
modes, migrations, and troubleshooting.

## Evaluation Snapshot

The committed offline-first workbench currently contains 20 developer planning
scenarios, 40 held-out planning scenarios (36 feasible and 4 infeasible), and 24
Agent fixtures. On the recorded held-out run, the transparent greedy baseline
and MealCraft used the same eligible recipe pool:

| Metric | Greedy baseline | MealCraft |
| --- | ---: | ---: |
| Adjacent repetitions | 216 | 0 |
| Mean distinct recipes per plan | 1.0 | 6.1389 |
| Feasible-case failures | 36 | 0 |

The recorded MealCraft run had zero hard-constraint violations. The offline
Agent fixture result was field F1 `0.907` and exact-case rate `16/24`; eight
failures remain visible for regression work. These results describe curated,
versioned fixtures, not clinical outcomes, representative Singapore households,
or the reliability of the live FairPrice website.

Run the deterministic developer gate and full offline workbench:

```bash
docker compose exec backend uv run --no-sync python -m app.evaluation
docker compose exec backend uv run --no-sync python -m app.evaluation.workbench
```

Neither command makes a paid API call by default. Read the
[Evaluation Protocol](docs/evaluation/protocol-v1.md) and the
[latest workbench report](docs/evaluation/workbench/latest.md) before quoting
results. The accepted next-stage design is the
[Capability-centred Comparative Evaluation v2](docs/design/comparative-evaluation-v2.md),
which is not yet an implemented or reported result.

## Documentation

Start with [Documentation Home](docs/README.md), which provides reading paths
for users, contributors, maintainers, and coding agents.

- [Project Guide](docs/project-guide.md) - product purpose, principles, final
  design, functional model, and success definition
- [User Guide](docs/user-guide.md) - how to operate the current application
- [Current Status](docs/current-status.md) - verified implementation, remaining
  design gaps, and current priorities
- [Architecture](docs/architecture.md) - components, ownership boundaries, data
  flow, and runtime behaviour
- [Design Contracts](docs/design/README.md) - detailed module outputs,
  dependencies, hand-offs, readiness gates, and Evaluation v2 design
- [Data Engineering Handoff](docs/data/README.md) - recipe and ingredient
  sources, cleaning layers, review policy, release gates, and teammate hand-off
- [External Retrieval and RAG Handoff](docs/design/external-retrieval-rag.md) -
  on-demand FairPrice retrieval, YouTube Top-1 tutorial selection, evidence
  packets, degradation states, teammate work packages, and acceptance metrics
- [API Contracts](docs/api-contracts.md) - current HTTP and schema contracts
- [Development](docs/development.md) - setup, run, debug, test, and recovery
- [MVP Boundary](docs/mvp-boundary.md) - minimum baseline and exact current
  semantics
- [Evaluation v1](docs/evaluation/protocol-v1.md) - currently executable
  datasets, metrics, limitations, and commands
- [Contributing](CONTRIBUTING.md) - Issue, branch, validation, review, and merge
  workflow
- [Agent Instructions](AGENTS.md) - mandatory context and safety rules for coding
  agents

## Contributing and Shared Context

Use short-lived task branches, pull requests, automated checks, and teammate
review. Begin with [CONTRIBUTING.md](CONTRIBUTING.md); do not commit directly to
`main`.

Approved contributors may also use the private sibling repository
`MealCraft-Knowledge` for accepted decisions, course requirements, risks, and
task history. The private repository is never required to run MealCraft and its
contents must not be copied into this public repository. See
[Memory Bootstrap](docs/memory-bootstrap.md).
