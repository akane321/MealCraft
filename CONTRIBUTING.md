# Contributing to MealCraft

MealCraft uses short-lived task branches, Issues, pull requests, automated
checks, and teammate review. Contributions should improve the final product
without weakening safety, reproducibility, traceability, or the deterministic
calculation boundary.

## 1. Understand the Project Before Editing

New contributors should read, in order:

1. [README.md](README.md)
2. [docs/project-guide.md](docs/project-guide.md)
3. [docs/current-status.md](docs/current-status.md)
4. [docs/architecture.md](docs/architecture.md)
5. [docs/development.md](docs/development.md)
6. the documents and tests related to the intended change

Coding agents must read [AGENTS.md](AGENTS.md) first and follow its private-memory
preflight when the approved sibling repository is available.

## 2. Identify the Responsibility Domain

A task may cross domains, but its primary responsibility and interfaces should
be explicit:

- product behaviour and interaction design;
- recipe, ingredient, nutrition, and provenance data;
- Agent requirement understanding and clarification;
- recipe retrieval and grocery grounding;
- planning, validation, explainability, and replanning;
- backend APIs, persistence, reliability, and operations;
- frontend implementation, responsive behaviour, and accessibility;
- evaluation, testing, datasets, baselines, and reproducibility.

These domains are not permanent personal branches. Coordinate through schemas,
fixtures, API contracts, and reviewable task branches.

## 3. Start with an Issue

Create or claim an Issue before substantial work. Record:

- problem and user value;
- current behaviour and evidence;
- proposed scope and explicit exclusions;
- acceptance criteria;
- affected domains and interfaces;
- dependencies and risks;
- required tests, fixtures, screenshots, or evaluation evidence;
- documentation that may need an update.

An Issue describes intended work. It is not evidence that the feature exists.

## 4. Start from the Latest `main`

Confirm that local work is safe before switching branches:

```bash
git status
git switch main
git pull --ff-only origin main
git switch -c <type>/<short-description>
```

Use one of these prefixes:

- `feat/`: user-visible feature
- `fix/`: bug fix
- `data/`: recipe, ingredient, nutrition, or product data
- `docs/`: documentation
- `test/`: tests or evaluation without a product change
- `chore/`: infrastructure, dependencies, or repository maintenance

Keep one independently reviewable objective per branch. Do not use a permanent
personal branch as a substitute for task branches.

## 5. Run the Development Environment

```bash
cp .env.example .env
docker compose up --build --detach
docker compose ps
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

The `.env` file is local-only and must not be committed. Use fixture modes for
repeatable development unless live external behaviour is the explicit subject
of the task.

See [docs/development.md](docs/development.md) for setup and troubleshooting.

## 6. Verification Required by Change Type

| Change | Minimum evidence |
| --- | --- |
| Backend route or service | Ruff, focused Pytest, relevant integration tests, and API-contract update when behaviour changes |
| Database schema | Alembic migration, upgrade verification, repository/service tests, and persistence documentation |
| Frontend behaviour | ESLint, Vitest, typecheck, relevant loading/empty/success/error states, and screenshots for visible changes |
| End-to-end workflow | Playwright or a documented browser walkthrough across the affected desktop/mobile path |
| Recipe or ingredient data | Schema validation, source/provenance where required, duplicate and reference checks, and affected evaluation fixtures |
| Grocery provider or mapping | Live/cache/fixture behaviour, package and unit tests, freshness/source display, and visible failure degradation |
| Planner or validator | Hard-constraint, determinism, infeasibility, scoring, and Shopping List consistency tests |
| Agent or prompt | Structured-output validation, regression fixtures, clarification/safety cases, provider/model disclosure, and no default paid call |
| Nutrition semantics | Source/basis/coverage handling, deterministic calculations, tolerance explanation, and dedicated tests |
| Evaluation dataset or metric | New dataset version or justified correction, digest, formula/denominator, comparable inputs, result report, and limitations |
| Documentation only | Link check, consistency with current code and accepted decisions, and a distinction between verified and target behaviour |

## 7. Standard Quality Commands

Validate Compose:

```bash
docker compose config --quiet
```

Backend:

```bash
docker compose exec backend uv run --no-sync ruff check .
docker compose exec backend uv run --no-sync ruff format --check .
docker compose exec backend uv run --no-sync pytest
```

Frontend:

```bash
docker compose run --rm frontend pnpm lint
docker compose run --rm frontend pnpm test
docker compose run --rm frontend pnpm typecheck
docker compose run --rm frontend pnpm build
```

Evaluation:

```bash
docker compose exec backend uv run --no-sync python -m app.evaluation
docker compose exec backend uv run --no-sync python -m app.evaluation.workbench
```

Browser acceptance, when relevant:

```bash
cd frontend
pnpm exec playwright install chromium
pnpm test:e2e
```

Run the smallest relevant checks while developing and the complete required set
before requesting review.

## 8. Evaluation Integrity

- Do not tune on the held-out set.
- Do not silently overwrite labels, splits, fixtures, or previously reported
  conditions; version material changes.
- Baselines and MealCraft must receive the same applicable input, candidate
  pool, pantry state, product snapshot, and planning horizon.
- State every metric's numerator, denominator, sample size, and limitation.
- Keep baseline, Agent, planner, grocery, frontend, and product failures
  distinguishable.
- Do not describe missing nutrition data as a passed nutrition check.
- CI and default evaluation must not call a paid API.
- A live model run requires explicit provider selection, live-API opt-in, a
  runtime-only key, and a recorded model/data/cost boundary.

## 9. Documentation Responsibilities

Update documentation in the same pull request when behaviour changes:

- final product direction -> `docs/project-guide.md` and an accepted design
  decision where required;
- merged and verified capability -> `docs/current-status.md`;
- minimum accepted semantics -> `docs/mvp-boundary.md`;
- component or runtime boundary -> `docs/architecture.md`;
- request, response, or schema contract -> `docs/api-contracts.md`;
- setup, command, or troubleshooting -> `docs/development.md`;
- user operation -> `docs/user-guide.md`;
- dataset, metric, or experimental procedure -> `docs/evaluation/`;
- coding-agent safety or workflow -> `AGENTS.md`.

Do not duplicate the same changing fact across multiple files without a clear
canonical source.

## 10. Commit and Open a Pull Request

Inspect the intended changes before committing:

```bash
git status
git diff
git add <specific-files>
git diff --staged --check
git diff --staged
git commit -m "<type>: <imperative summary>"
git push -u origin <branch-name>
```

Examples:

```text
feat: add planned-meal check-in
fix: deduct pantry quantity once per weekly plan
data: add traceable sodium coverage
docs: explain current and final product boundaries
```

Open a pull request into `main`, complete the template, link the Issue with
`Closes #<number>`, describe verification and limitations, attach screenshots
for visible changes, and request teammate review.

## 11. Definition of Done

A change is complete only when:

- the acceptance criteria are satisfied;
- affected contracts and fixtures remain usable by other domains;
- required automated checks pass;
- visible failure behaviour is handled;
- documentation reflects the new verified state without overstating it;
- no secret or private material is included;
- review conversations are resolved and at least one teammate approves;
- CI passes and the pull request is squash-merged;
- the merged branch is deleted and local `main` is refreshed.

After merge:

```bash
git switch main
git pull --ff-only origin main
git fetch --prune
```

## Repository Safety

- Never commit `.env`, passwords, API keys, cookies, tokens, personal data,
  private FairPrice sessions, or private project-memory content.
- Do not weaken allergen or prohibited-ingredient checks through an LLM or a
  frontend-only condition.
- Do not move deterministic nutrition, cost, package, Shopping List, or
  evaluation arithmetic into an LLM prompt.
- Database changes require an Alembic migration.
- Do not delete data, rewrite history, force-push, push, or merge on behalf of
  the team without the authority required by the task.
- Preserve unrelated local changes and stop when ownership of an overlapping
  edit is unclear.
