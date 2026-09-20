# Operations Console

The internal surface the team uses to see what the system did, and to run
experiments against it. Decision: private `ADR-0031`; platform boundaries:
[Backend Platform Engineering](backend-platform-engineering.md).

This document is the contract for building it. Where it and a decision record
disagree, the decision record wins.

## What it is for

1. Is the system healthy now?
2. How did one result come about — why this plan, what that retrieval returned,
   which constraints a message changed?
3. How good is the data?
4. What did an evaluation produce?
5. **What changes if a parameter changes or a component is switched off?**

## Boundaries

1. The product surface stays one surface: `/` (decision ADR-0026). The console
   is a second, internal surface and must not grow product features.
2. Read-only by default. The only state-changing actions are the four listed
   under [Write endpoints](#write-endpoints).
3. Every state change **adds** an `OperationRun` and an `AuditEvent`. Nothing
   updates or deletes a historical row.
4. No raw SQL, no secrets or tokens, no plaintext health profiles, no arbitrary
   file access.
5. No action may overturn a deterministic verdict. A plan the validator refused
   cannot be marked feasible here; allergens, nutrition, packaging, cost and
   feasibility stay with deterministic code.

## Access

- The console is reached through the **same login form as the product**. There
  is no second login page.
- After authentication the system role decides what happens:
  - `ordinary_user`: no console entry is rendered, and `/ops` returns the user
    to the home surface without disclosing why;
  - `data_reviewer`, `operator`, `admin`: the home surface shows a console
    entry and `/ops` opens.
- Permissions follow `OPERATIONS_PERMISSIONS` in `backend/app/auth/authorization.py`:
  reviewers read runs and review data; operators also trigger and cancel jobs;
  admins additionally manage system roles.
- Household roles are independent: a household owner gets nothing from being one.
- Granting a system role is a local command-line script, not an endpoint.

## Modules

### System overview
API and database health, code revision, dataset version, failures in the last 24
hours by class, product-price source mix (live, cache, fixture, degraded),
queued and running job counts.

### Task runs
List with filters (type, status, time) showing type, status, who triggered it,
duration and input digest. Detail shows the timeline, warnings, error class,
artifact references and a copyable trace id. A running job can be cancelled.

### Data quality
Released recipe and ingredient counts, distribution by cuisine and course,
nutrition coverage, the share of values that are estimated rather than stated
(servings, times, ingredient amounts, separately), dropped candidates with their
reason, allergen rules still awaiting human confirmation, and the ingredient
mapping review queue where a reviewer records a decision.

Shapes are fixed by `data-engineering/data/fixtures/ops/` — real pipeline output
from a partial build; see that folder's README.

### Planning run inspector
Request, household profile version, pantry input; compiled hard constraints and
soft preferences; per-candidate rejection reasons (filterable, e.g. "rejected
for an allergen"); score breakdown; chosen slots; grocery derivation; the
independent validator's verdict; and the distinction between genuinely
infeasible, exhaustively infeasible, bounded search exhausted and needs-data.
Search statistics: expansions, pruned states, whether a limit was reached.

### Retrieval monitor
Per query: terms, provider, cache or live, timestamp, candidate evidence,
warnings, parser version. Replay is from the stored snapshot; it does not call
the external site again.

### Agent trace
How a message became structured constraints and which constraints changed,
the clarification exchange, tool calls, the parser provider, and links to the
deterministic results. Redacted: message digests and structured changes only,
never the full conversation text.

### Experiments and ablations
Define a run: dataset, system (`greedy-baseline`, `rule-only-baseline`,
`mealcraft-planner`, context-matched LLM-only), parameters, seed, repeats, and
ablation presets that switch off a component (independent validation, repair,
meal affinity, diversity).

Parameters come from a controlled registry — name, meaning, range, default —
covering at least beam width, expansion cap, dominance rule, meal-affinity
penalty, nutrition tolerance and the agent parser provider. The console changes
registered parameters only.

Every run records: code revision, parameter-configuration digest, each dataset's
path and SHA-256, seed, repeat count, who ran it, duration, and whether a paid
model was used. **A run whose conditions are not fully recorded may not be
cited.** Paid-model runs need an explicit opt-in and a per-run budget cap, and
are off by default.

Comparison view: two or more runs side by side — overall metrics, per-category
episode counts and failure mechanisms (never a per-category success rate,
decision ADR-0028), failures gained and lost, and a per-episode diff. Opening an
episode shows the two runs side by side: constraint parsing, candidate
rejections, scores, chosen slots, validator verdict.

Integrity guards, enforced by the console rather than by discipline (decision
ADR-0020 section 2 as amended by ADR-0029 section 1):

- a held-out dataset is not offered while it is unfrozen; tuning uses synthetic
  or developer data;
- after the freeze, held-out runs are a separate "final comparison" action and
  the number of runs against a manifest is recorded;
- experiment results are labelled implementation-side evidence and are not
  circulated to episode authors before the freeze.

## Endpoints

All under `/api/ops`, all requiring a system role.

### Read endpoints

| Endpoint | Returns |
| --- | --- |
| `GET /overview` | system overview |
| `GET /runs?type=&status=&since=` | task runs |
| `GET /runs/{trace_id}` | one run with its timeline and artifacts |
| `GET /data-quality` | the quality summary |
| `GET /data-quality/dropped` | dropped candidates with reasons, paged |
| `GET /mappings/review-queue` | ingredient mappings awaiting review |
| `GET /plans/{plan_id}/inspect` | planning derivation |
| `GET /retrieval?provider=&since=` | retrieval records |
| `GET /agent-runs?status=` | redacted agent runs |
| `GET /experiments` | experiment runs with their conditions |
| `GET /experiments/{id}` | one experiment with metrics |
| `GET /experiments/compare?ids=` | comparison of two or more runs |
| `GET /experiments/{id}/cases` | per-episode results, filterable |
| `GET /parameters` | the tunable-parameter registry |

### Write endpoints

| Endpoint | Role | Effect |
| --- | --- | --- |
| `POST /jobs` | operator | queues a named job (catalog import, evaluation rebuild, price-snapshot refresh) |
| `POST /runs/{trace_id}/cancel` | operator | cancels a running job |
| `POST /mappings/{id}/decision` | data_reviewer | records a mapping decision |
| `POST /experiments` | operator | queues an experiment |

Each requires an explicit confirmation from the interface and writes a new run
and audit event.

## Durable jobs

Reuse `operation_runs`, adding job payload, lease expiry, attempt count and an
idempotency key. States: `queued → running → succeeded | failed | cancelled |
degraded`. Work is claimed in a transaction and the lease renewed while running;
a crashed worker's lease expires and the job is reclaimed. Retries are bounded,
timeouts enforced, handlers idempotent. The worker is a separate container in
`compose.yaml`. No Redis or Celery.

## Frontend

- Route `/ops`, entered from the home surface when the role allows it.
- Left navigation (overview, runs, data, planning, retrieval, agent,
  experiments) with a content area to the right.
- The dark liquid-glass styling of the product, at higher information density:
  tables first.
- Shared components: filterable table, status pill, timeline, collapsible JSON
  viewer, copyable trace id, two-column diff.
- Every view implements loading, empty, error and forbidden states.
- Write actions confirm first, stating what will happen, what it affects and
  whether it can be cancelled.
- Desktop, minimum 1280x720 (decision ADR-0010).

## Acceptance

| Area | Must hold |
| --- | --- |
| Authorization | an ordinary user is refused by every `/api/ops` endpoint; a reviewer cannot trigger jobs; an operator cannot change system roles |
| Entry isolation | an ordinary user sees no console entry and `/ops` discloses nothing |
| Immutability | no endpoint updates or deletes an `OperationRun` or `AuditEvent`; no action marks a refused plan feasible |
| Worker | jobs survive a restart without loss or duplication; timeouts reclaim leases; cancellation takes effect; retries are bounded |
| Experiment guards | held-out is unavailable before the freeze; the final comparison is a separate action; every run's conditions are complete enough to reproduce it |
| Redaction | no secret, token or plaintext profile appears in runs or audit events |
| Browser | signed in as an admin: overview → trigger a job → watch it finish → open a failure → run an ablation and compare it |
