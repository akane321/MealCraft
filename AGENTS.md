# MealCraft Agent Bootstrap

This public repository contains source code. The private sibling repository `MealCraft-Knowledge` is the shared project-memory authority for accepted decisions, course requirements, current state, risks, and task history.

## Required public reading order

Before reasoning about a material change, read:

1. `docs/project-guide.md` for the accepted final product direction;
2. `docs/current-status.md` for the last documented verified snapshot;
3. `docs/architecture.md` for current component and calculation boundaries;
4. `docs/api-contracts.md` and the relevant code/tests for exact behaviour;
5. `docs/mvp-boundary.md` when minimum product semantics are involved;
6. `docs/design/README.md` and the relevant module contract when changing a
   producer/consumer boundary or accepted target;
7. `docs/evaluation/protocol-v1.md` for currently executable evidence and
   `docs/design/comparative-evaluation-v2.md` for accepted next-stage evaluation
   semantics.

The initial proposal defines a minimum final-product ambition. Its maintained
public interpretation is `docs/project-guide.md`; do not require every agent to
infer the current target from an old PDF. The current MVP is not the final scope.

## Evidence hierarchy

When sources disagree, use this order unless the current user instruction or a
course authority explicitly overrides it:

1. current code, migrations, generated OpenAPI, and passing tests;
2. accepted, non-superseded decisions in the private knowledge repository;
3. `docs/api-contracts.md` and `docs/architecture.md`;
4. `docs/current-status.md`;
5. `docs/project-guide.md`, roadmap, Issues, and proposals.

A design target, Issue, branch, or roadmap entry is not implemented behaviour.

## Public code map

```text
backend/app/api/          HTTP routes and request/response boundaries
backend/app/services/     deterministic workflows and domain services
backend/app/repositories/ persistence adapters
backend/app/evaluation/   repeatable datasets, metrics and reports
frontend/app/pages/       user-facing routes
frontend/app/components/  reusable product interface
data/recipes/             validated recipe catalog
data/ingredients/         normalized ingredient catalog
data/fixtures/            deterministic grocery fixtures
data/evaluation/          versioned evaluation inputs
docs/                     maintained product and engineering documentation
```

## Before material changes

Classify the task:

- L0: read-only answer or status lookup
- L1: routine code, tests, or documentation change
- L2: scope, architecture, data semantics, evaluation, rubric, or release change
- L3: destructive migration, major refactor, history rewrite, or deletion

For L1--L3, locate the knowledge repository in this order:

1. `$env:MEALCRAFT_KNOWLEDGE_HOME`
2. sibling directory `../MealCraft-Knowledge`

Then run:

```powershell
powershell -ExecutionPolicy Bypass -File <knowledge-root>\scripts\memory-preflight.ps1 `
  -ProjectPath $PWD -Impact L1
```

Use the actual impact level. Follow the knowledge repository's root `AGENTS.md` as the canonical protocol.

If the private knowledge repository cannot be accessed, state that the context is unsynchronized. L2/L3 work must stop; L1 is limited to safe, reversible diagnostics until context is restored.

## While working

- Current code, tests, remote GitHub state, course source documents, and accepted ADRs are evidence; do not treat a roadmap item as completed behavior.
- Treat MVP requirements as the minimum acceptance baseline, never as the product goal, scope ceiling, or automatic stopping point. After a module meets its baseline, continue toward final-product quality in user value, completeness, reliability, usability, evaluation evidence, testing, documentation, and demo readiness when time, risk, and dependencies allow.
- Going beyond the baseline does not authorize unbounded feature growth. Material additions must state user value, success criteria, evaluation evidence, cost, dependencies, and risks, and must preserve the accepted safety, privacy, reproducibility, and deterministic-computation boundaries.
- Do not add a metric, filter, score, or claim until its upstream field has a
  canonical definition, versioned fixture, missing-value semantics, provenance
  where required, and a documented consumer. Use `docs/design/README.md`.
- Preserve unrelated user changes and use feature branches plus pull requests.
- Keep numeric constraints, nutrition, cost, package quantity, Shopping List, and evaluation logic deterministic and testable. The Agent may parse intent and explain tool results.
- Never commit secrets, `.env`, real personal health data, private memory content, or raw restricted course material to this public repository.

## Protected product invariants

- Allergens, prohibited ingredients, diet compatibility, explicit numeric
  limits, nutrition arithmetic, cost, packages, pantry deduction, Shopping List
  derivation, Dashboard aggregation, and evaluation metrics remain deterministic
  and testable.
- Unknown pantry quantity may affect ranking but must not be deducted.
- Dashboard actuals include completed MealCraft dishes only.
- Broad lower-sodium or lower-sugar preferences are not medical prescriptions or
  silent hard filters.
- Live FairPrice data must remain distinguishable from cache and fixture data.
- An external recipe or model response is untrusted until parsed, normalized,
  validated, and linked to provenance.
- The Shopping List is derived after the final plan is validated; it is not a
  free-form Agent output.

## Verification routing

Use checks proportional to the changed surface:

```bash
docker compose config --quiet
docker compose exec backend uv run --no-sync ruff check .
docker compose exec backend uv run --no-sync ruff format --check .
docker compose exec backend uv run --no-sync pytest
docker compose run --rm frontend pnpm lint
docker compose run --rm frontend pnpm test
docker compose run --rm frontend pnpm typecheck
docker compose run --rm frontend pnpm build
```

Run `python -m app.evaluation.workbench` for evaluation-affecting changes and
Playwright for affected desktop user journeys. Do not claim visual quality from
a successful build alone. Mobile and tablet product design are out of scope.

Update the canonical document identified in `docs/README.md` when behaviour,
contracts, setup, final direction, or evaluation semantics change.

## After material changes

1. Run verification proportional to risk.
2. Run `<knowledge-root>\scripts\memory-finalize.ps1` to generate a task record.
3. Update `CURRENT_STATE.md` only for verified behavior merged to remote `main`; create an ADR for L2/L3 decisions.
4. Validate and submit knowledge changes through a separate `memory/*` branch and PR.
5. Do not automatically push, merge, or rewrite Git history unless the user explicitly authorizes it.
