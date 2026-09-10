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

## Triggered reading

The list above is the baseline. These topics require their contract to be read
*before* the change, not after. Reading them afterwards is how a change ships
against a contract that already said something different.

| The task touches | Read first |
| --- | --- |
| evaluation metrics, baselines, datasets, held-out splits, capability claims | `docs/design/comparative-evaluation-v2.md`, `docs/evaluation/protocol-v1.md` |
| a cross-module field, schema, provenance or unknown-value semantics | `docs/design/README.md` and the owning module contract |
| planning, validation, package or budget arithmetic | `docs/design/algorithm-engineering-handoff.md` |
| accounts, household isolation, migrations, operations | `docs/design/backend-platform-engineering.md` |
| Agent scope, tool authorization, grounding, runs | `docs/design/agent-orchestration.md` |
| FairPrice, YouTube, external evidence or RAG | `docs/design/external-retrieval-rag.md` |
| recipe or ingredient sourcing, cleaning, release | `docs/data/README.md` |

When the private knowledge repository is available, its `AGENTS.md` section 2.1
carries the same table with the corresponding decision records.

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

## One fact, one carrier

A fact has exactly one authoritative document. Every other mention links to it
rather than restating it. `docs/README.md` lists the canonical source for each
question; the private repository's `memory-manifest.json` carries the same table
for project memory.

Two consequences that are easy to get wrong:

- **Mutable state belongs only to `docs/current-status.md` and the generated
  evaluation reports.** A `main` SHA, whether a numbered pull request has
  merged, a "last verified" date, or a current metric value must not appear in a
  design document, contract, handoff or guide. Point at a path plus a decision
  id. A pull-request number stops being true the moment it merges, and the stale
  claim usually sits in the first line a reader sees.
- **Metric values are generated artifacts.** Quote them by linking
  `docs/evaluation/workbench/latest.md`. Do not hand-copy numbers into prose as
  an independent claim, and never recompute them by hand.

If two documents disagree, follow the evidence hierarchy above, then fix the
losing document in the same task or record the conflict as an open question in
the private repository. Leaving both versions in place is how the disagreement
reaches the next reader.

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

CI runs the backend checks in both layouts: from a checkout in the `backend`
job, and through the container in the `compose` job, using the commands above. A green run therefore means the documented
command works, not only that some equivalent of it works. The frontend container
commands are not covered; the frontend job runs them on the host.

Update the canonical document identified in `docs/README.md` when behaviour,
contracts, setup, final direction, or evaluation semantics change.

## After material changes

1. Run verification proportional to risk.
2. Run `<knowledge-root>\scripts\memory-finalize.ps1` to generate a task record.
3. Update `CURRENT_STATE.md` only for verified behavior merged to remote `main`; create an ADR for L2/L3 decisions.
4. Validate and submit knowledge changes through a separate `memory/*` branch and PR.
5. Do not automatically push, merge, or rewrite Git history unless the user explicitly authorizes it.
