# Operations Console

The console at `/ops` is the team's internal tool for monitoring, debugging,
catalog/account maintenance and reproducible experiments. It is separate from
the household product surface. ADR-0047 and ADR-0051 amend ADR-0031: it is
**not read-only**, and has one administrator level, not a reviewer/operator
hierarchy. [Backend Platform](backend-platform-engineering.md) defines platform
boundaries; [Current Status](../current-status.md) records integration, not this
handoff. Proposed endpoints are not an inventory of implemented routes.

## Access and invariants

- Use the same login form and session as the product. Fixed `ADMIN_ACCOUNTS`
  are administrators; household ownership grants no console.
- Only `admin` opens the console. Legacy `operator` and `data_reviewer`
  database values grant no access. Ordinary accounts see no console entry;
  authenticated non-admin API callers receive the non-disclosing 404.
- GET uses the common admin read dependency. Writes use admin plus session
  CSRF; check account access before CSRF.
- Registered workflows may update/delete product or account data, with an
  audit of who changed what. This is not an append-only catalog.
- Replay and experiments create new runs; audit history is not rewritten.
  Durable job lifecycle transitions may update their row while retaining
  cancellation/retry evidence.
- No action can mark a refused plan feasible or override deterministic safety,
  nutrition, packages or cost. Allergens remain rule-derived and not editable.
  No raw SQL, arbitrary commands/paths or exposed secrets.
- Existing sign-in and household separation stay. Additional security/privacy
  lifecycle work is excluded by ADR-0051, not a delivery to-do list.

## Reuse the existing modules

Exact routes and fields belong in [API Contracts](../api-contracts.md) and
generated OpenAPI. Start from `backend/app/api/routes/operations.py`, its
services, `OperationRun`, `AuditEvent` and the frontend's `/ops` pages;
do not start by building overview/runs as though no console existed.

| Module | Purpose | Boundary |
| --- | --- | --- |
| Overview | Health, recorded volumes, failures, durations and provider mix | Never infer live prices from fixture success |
| Tasks/debugging | Stored inputs, understood constraints, candidates, verdicts, bounded replay and comparison | Replay must not save a new product plan or rewrite the conversation |
| Services | Configuration presence, recent evidence and bounded live checks | A configured key is not displayed; a probe is not a quality benchmark |
| Data | Registered recipe edits, withdraw/restore, ingredient aliases and product mappings | Allergens remain in reviewed rules; distinguish estimated from stated facts |
| Users | Accepted account, household and product-record management | Do not reopen excluded invitation/reset/export security work |
| Experiments/configuration | Registered settings, recorded conditions and comparisons | Developer tuning is separate from independent final comparison |

Data-quality views read released `quality_summary.json`, manifest and dropped
candidates with digests and degraded states. Pipeline-shaped samples in
`data-engineering/data/fixtures/ops/` are test inputs, not runtime counts.
Release coverage, imported rows and planner-eligible rows have different
denominators. Complete fields do not mean independently verified facts.

Planning inspection explains candidate rejection, dish roles, shopping,
validator checks and limits. Proven infeasible, bounded-search exhausted and
needs-data are different outcomes. Retrieval views preserve mode, freshness,
warnings and evidence. Replay stored inputs rather than silently re-querying
to explain a historical result. Reuse trace minimization/redaction.

## Durable jobs: separately integrated

Reuse PostgreSQL `operation_runs` with typed payload, lease expiry, attempt
count and scoped idempotency key. No Redis/Celery without measured need.

- Claim transactionally with `FOR UPDATE SKIP LOCKED`; commit before execution.
- Renew the lease; reclaim expired work up to a bounded attempt count.
- Renew, completion and retry must check current attempt/status atomically.
  An old worker must not resurrect a cancelled or reclaimed job.
- Use registered typed handlers in a separate worker container.
- Handlers must be idempotent. Termination cannot undo a committed import;
  cancellation must not promise rollback or exactly-once execution.
- Test timeout, shutdown, cancellation, competing workers and retry behavior
  against the intended database. A schema is not restart-reliability evidence.

Consult Current Status for integration; a design does not establish a worker.

## Experiments and ablations

Retain code revision/source fingerprint, runner version, configuration digest,
input paths/SHA-256, seed, repeats, duration, actor and paid-model use. Keep the
matching checkout and lockfile: digests alone cannot reconstruct an environment.
Registered parameter names carry meanings, ranges and defaults.

Developer presets can measure validation, repair, meal affinity, diversity or
ranking. An unchecked offline draft never becomes a persistable product plan.
Compare recorded conditions and case-level failures. Report category counts and
mechanisms, not category success rates (ADR-0028). Width-one MealBeam is not the
formal strong Rule-only baseline unless that comparison protocol defines it so.

Integrity follows ADR-0020/0029/0049:

- Tuning uses synthetic/developer inputs, never held-out episodes or gold.
- Unfrozen held-out inputs are not offered; frozen final comparison is a
  separate action with recorded run count.
- Implementation results do not go to authors before freeze.
- After inspection and result-guided fixes, reruns are diagnostics, not new
  unseen evidence. Preserve the clean first run.
- Paid experiments default off and require explicit authorization and a cap.
  Offline experiments must not indirectly make paid calls.

## Frontend and acceptance

Desktop only, minimum 1280×720. Reuse navigation, tables, status and task detail.
Distinguish loading, empty, degraded/unavailable and error states. Confirm writes
with their effects and use idempotency for repeat submissions; cancellation
is not rollback.

Acceptance requires endpoint-wide admin/read-write checks, audited edits that
cannot bypass validation, explicit data provenance/missing artifacts, durable
worker race/restart tests, reproducible experiment conditions and paid-call
guards, plus the relevant signed-in desktop journey. These are acceptance
conditions, not a claim that every extension is already integrated.
