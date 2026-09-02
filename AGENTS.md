# MealCraft Agent Bootstrap

This public repository contains source code. The private sibling repository `MealCraft-Knowledge` is the shared project-memory authority for accepted decisions, course requirements, current state, risks, and task history.

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
- Preserve unrelated user changes and use feature branches plus pull requests.
- Keep numeric constraints, nutrition, cost, package quantity, Shopping List, and evaluation logic deterministic and testable. The Agent may parse intent and explain tool results.
- Never commit secrets, `.env`, real personal health data, private memory content, or raw restricted course material to this public repository.

## After material changes

1. Run verification proportional to risk.
2. Run `<knowledge-root>\scripts\memory-finalize.ps1` to generate a task record.
3. Update `CURRENT_STATE.md` only for verified behavior merged to remote `main`; create an ADR for L2/L3 decisions.
4. Validate and submit knowledge changes through a separate `memory/*` branch and PR.
5. Do not automatically push, merge, or rewrite Git history unless the user explicitly authorizes it.
