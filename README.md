# MealCraft

MealCraft is an explainable, constraint-aware weekly meal-planning system that
turns household requirements and real grocery information into a validated meal
plan and an actionable Shopping List.

It is developed for **DSS5105 Data Science Projects in Practice**. The project
targets a polished, evidence-backed final product: the current MVP is a minimum
acceptance baseline, not the scope or quality ceiling.

The course deliverable is evaluated as a locally runnable system. Cloud hosting
or public deployment is not required; `Readme.pdf` and this repository should
make setup, requirements, and local execution reproducible. Docker Compose
remains the supported local runtime rather than evidence of a hosted service.

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
| Accounts and sessions | Argon2id credentials, registration and login, digest-only revocable sessions, CSRF, and per-device revocation. Business routes are still anonymous and single-tenant |
| Planning assistant | Persistent English/Chinese conversations, bounded scope routing, structured constraints and clarification controls, confirmation, and tool delegation |
| Weekly planning | Persisted seven-day main-meal plans with hard filtering, soft ranking, diversity control, and per-person nutrition |
| Grocery grounding | FairPrice product lookup with normalized packages, PostgreSQL cache, and reproducible fixtures |
| Shopping List | Consolidated ingredient demand, known-quantity pantry deduction, package rounding, and budget results |
| Plan execution | `planned`, `completed`, and `skipped` check-in states |
| Nutrition Dashboard | Daily totals, weekly trends, and completion coverage for completed MealCraft dishes only |
| Replanning | Revision-safe preview, confirmation or discard, local meal changes, Shopping List deltas, and event history |
| Agent runs | Synchronous per-action `AgentRun` with input digests, explicit deadlines and budgets, durable checkpoints, ordered tool receipts, idempotent replay, and run list/detail/cancel APIs |
| Evaluation | Versioned developer, held-out, Agent, scope and grounding fixtures; greedy and strong Rule-only references; matched-information v2 developer packets; a Strict End-to-End Task Success scorer that recomputes rather than trusting claims; held-out episode authoring, compilation and freeze tooling; failure registry; frontend state and browser tests |

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
backend/app/planning/     deterministic planning, shopping and validation algorithms
backend/app/auth/         session-token and authorization foundations
backend/app/orchestration/ scope, interaction, bounded runs and grounding foundations
frontend/app/pages/       user-facing product routes
frontend/app/composables/ shared frontend state and API access
data/recipes/             versioned recipe catalog
data/ingredients/         normalized ingredient catalog
data/fixtures/            reproducible grocery fixtures
data/evaluation/          versioned evaluation inputs
docs/                     product, architecture, operation and evaluation docs
scripts/                  repository checks that run without a container
.github/                  CI, issue, PR and ownership configuration
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

## Evaluation

### What exists today

An offline, fixture-only workbench: 20 developer planning scenarios, 40 held-out
planning scenarios, 24 Agent extraction fixtures, and two orchestration developer
sets covering bilingual scope routing and typed claim grounding. Every report
records the SHA-256 digest of its input, so a dataset change is a new
experimental condition rather than a quiet edit.

```bash
docker compose exec backend uv run --no-sync python -m app.evaluation
docker compose exec backend uv run --no-sync python -m app.evaluation.workbench
```

Neither command makes a paid API call. Current numbers live in the
[generated workbench report](docs/evaluation/workbench/latest.md) and are not
copied here: a metric table in a README goes stale without anyone noticing,
and this one did.

### What that evidence does not yet show

**It does not show that MealCraft beats a competent alternative.** Against the
strong Rule-only reference, the two systems tie on task success, on
hard-constraint violations and on recorded failures. Only recipe diversity
separates them, and a primary metric that saturates for both systems is
measuring the difficulty of the evaluation set rather than the strength of the
planner.

Track 5 requires evidence of improvement over a simple approach, so closing this
is the point of
[Capability-centred Comparative Evaluation v2](docs/design/comparative-evaluation-v2.md),
which is an accepted design and not a reported result.

Two further limits worth stating plainly:

- The Agent fixture numbers describe a **deterministic fixture parser**, not a
  model. They say nothing about what a language model would score.
- The scope and grounding sets were visible during implementation. They are
  diagnostics, not held-out evidence.

### What is being built

Strict End-to-End Task Success is the accepted primary endpoint, and the scorer
for it recomputes every requirement from frozen facts rather than reading a
system's claims. An independent held-out set of roughly 80 episodes is being
authored under cross-authoring rules - nobody writes episodes that test their
own module - and must be frozen before the components it evaluates are tuned,
because that ordering cannot be repaired afterwards.

The 44-record failure registry is **not** a defect list. 36 entries are greedy
baseline failures, which are the reason the baseline exists; 8 are Agent
extraction or clarification failures in MealCraft itself.

Read the [Evaluation Protocol](docs/evaluation/protocol-v1.md) before quoting
any result, and the
[authoring guide](docs/evaluation/heldout-authoring-guide.md) before writing an
episode.

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
- [Algorithm Engineering Handoff](docs/design/algorithm-engineering-handoff.md) -
  final-scope multi-meal mathematical model, deterministic validation,
  Beam Search proposal, product-repair loop, work packages, and completion gates
- [Backend Platform Engineering Handoff](docs/design/backend-platform-engineering.md) -
  accounts, revocable sessions, household data isolation, durable jobs,
  operations traces, internal Console design, security gates, and work packages
- [Agent Orchestration Engineering Handoff](docs/design/agent-orchestration.md) -
  bounded scope, capability/tool policy, structured interaction, checkpoints,
  hallucination controls, grounded response evaluation, and work packages
- [API Contracts](docs/api-contracts.md) - current HTTP and schema contracts
- [Development](docs/development.md) - setup, run, debug, test, and recovery
- [MVP Boundary](docs/mvp-boundary.md) - minimum baseline and exact current
  semantics
- [Evaluation v1](docs/evaluation/protocol-v1.md) - currently executable
  datasets, metrics, limitations, and commands
- [Comparative Evaluation v2](docs/design/comparative-evaluation-v2.md) - the
  accepted comparison design: baselines, matched information, strict end-to-end
  success, statistics, and failure analysis
- [Held-out Authoring Guide](docs/evaluation/heldout-authoring-guide.md) - how
  to write an episode, what the checker enforces, and what it cannot judge
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
