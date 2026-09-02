# Shared Memory Setup

MealCraft uses two repositories:

- `akane321/MealCraft`: public source code
- `akane321/MealCraft-Knowledge`: private decisions, state, course requirements, risks, and task history

The knowledge repository is deliberately not a Git submodule. Public cloning and CI remain usable without private access, while approved team members can synchronize internal context independently.

## First-time setup

Ask the owner to add your GitHub account as a collaborator on `MealCraft-Knowledge`, then clone both repositories into any locations you prefer. Placing them side by side avoids extra configuration:

```powershell
git clone https://github.com/akane321/MealCraft.git
git clone https://github.com/akane321/MealCraft-Knowledge.git
```

If the repositories are not siblings, set a user environment variable:

```powershell
[Environment]::SetEnvironmentVariable(
  'MEALCRAFT_KNOWLEDGE_HOME',
  'D:\your\path\MealCraft-Knowledge',
  'User'
)
```

Restart VS Code/terminal after setting it.

## Start a task

```powershell
Set-Location D:\your\path\MealCraft-Knowledge
git pull --ff-only

powershell -ExecutionPolicy Bypass -File .\scripts\memory-preflight.ps1 `
  -ProjectPath "D:\your\path\MealCraft" `
  -Impact L1
```

The command prints the mandatory context, recent task records, and current MealCraft Git state, then stores a local preflight receipt under `.local/`.

## Finish a task

After tests and before the final handoff:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\memory-finalize.ps1 `
  -TaskId "short-kebab-case-id" `
  -Title "Human-readable task title" `
  -Summary "What was implemented and why." `
  -Impact L1 `
  -ProjectPath "D:\your\path\MealCraft" `
  -PullRequestUrl "https://github.com/akane321/MealCraft/pull/123" `
  -Verification "pytest passed","frontend tests passed" `
  -Risks "Known limitation or None" `
  -NextAction "Exact next step"
```

Review the generated `history/YYYY-MM/*.md` file. If an accepted decision or merged capability changed, also update the relevant ADR or `CURRENT_STATE.md`. Then:

```powershell
git switch -c memory/short-task-id
python scripts/validate_memory.py
git add .
git commit -m "docs: record short task id"
git push -u origin memory/short-task-id
```

Open a PR in the private knowledge repository. Do not paste private memory content into the public code PR.

## Agent prompt to reuse

```text
Before making any material MealCraft change, read and follow the public AGENTS.md,
locate MealCraft-Knowledge, and run its memory-preflight script with the correct
impact level. After verification, run memory-finalize and update shared memory
only with evidence-backed facts. Never store secrets or real health data.
```

## Failure behavior

- `git pull --ff-only` failure: resolve authentication/divergence before continuing.
- Missing knowledge access: L2/L3 tasks stop; do not reconstruct decisions from memory.
- Knowledge HEAD changed after preflight: rerun preflight before finalize.
- Validation failure: fix the reported structure or sensitive-data issue; do not bypass CI.

