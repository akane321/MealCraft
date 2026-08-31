# Contributing to MealCraft

MealCraft uses short-lived branches, pull requests, automated checks, and one reviewer before changes enter `main`.

## 1. Start from the latest main

```bash
git switch main
git pull --ff-only origin main
git switch -c <type>/<short-description>
```

Use one of these branch prefixes:

- `feat/`: user-visible feature
- `fix/`: bug fix
- `data/`: recipe, ingredient, nutrition, or product data work
- `docs/`: documentation or research notes
- `test/`: test-only change
- `chore/`: infrastructure, dependencies, or repository maintenance

Keep one independently reviewable objective per branch.

## 2. Link the work to an Issue

Create a Bug report or Feature / task Issue before substantial work. Record the scope, exclusions, acceptance criteria, owner, dependencies, evidence, and open questions there.

## 3. Develop and verify locally

Start the complete development environment:

```bash
cp .env.example .env
docker compose up --build --detach
```

Run backend checks:

```bash
docker compose exec backend uv run --no-sync ruff check .
docker compose exec backend uv run --no-sync ruff format --check .
docker compose exec backend uv run --no-sync pytest
```

Run frontend checks:

```bash
docker compose exec frontend pnpm lint
docker compose exec frontend pnpm test
docker compose exec frontend pnpm typecheck
docker compose exec frontend pnpm build
```

Validate Compose:

```bash
docker compose config --quiet
```

Automated tests use reproducible FairPrice fixtures. Verify live FairPrice behaviour manually and record visible fallback behaviour; do not make CI depend on the external website.

## 4. Commit and open a pull request

Use a short imperative commit subject, for example:

```text
feat: add planned-meal check-in
fix: deduct pantry quantity once per weekly plan
docs: explain nutrition dashboard semantics
```

Push the branch and open a pull request into `main`. Complete the PR template, link its Issue with `Closes #<number>`, attach UI screenshots when relevant, and request at least one teammate review.

## 5. Review and merge

Do not merge until the `backend`, `frontend`, and `compose` checks pass, review conversations are resolved, and one teammate approves. Use squash merge, then delete the merged branch.

After a merge:

```bash
git switch main
git pull --ff-only origin main
git fetch --prune
```

## Repository safety

- Never commit `.env`, passwords, API keys, cookies, access tokens, personal data, or private FairPrice session data.
- Do not weaken allergen and prohibited-ingredient hard constraints through an LLM or UI-only check.
- Database schema changes require an Alembic migration.
- Update API and architecture documentation when contracts or module responsibilities change.
- Unplanned foods remain outside the MVP; dashboard totals must be labelled as MealCraft-tracked nutrition.
