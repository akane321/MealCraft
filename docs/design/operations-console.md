# Operations Console

The internal surface the team uses to see what the system did, and to run
experiments against it. Decision: private `ADR-0031`; platform boundaries:
[Backend Platform Engineering](backend-platform-engineering.md).

This document is the contract for building it, and the briefing for whoever
picks it up. Where it and a decision record disagree, the decision record wins.

> **Amended by private `ADR-0047` (2026-09-26), now built.** Fixed admin accounts of one
> level (`ADMIN_ACCOUNTS`) replace the role gating described below, and the console
> edits as well as reads: replay, runtime settings, users and catalog data, each change
> audited. Edits still never overrule deterministic code (the validator, allergen rules).
> Security and privacy hardening is out of scope by the owner's decision. Where this
> document describes a read-only default or per-role permissions, ADR-0047 wins.

## What it is for

1. Is the system healthy now?
2. How did one result come about — why this plan, what that retrieval returned,
   which constraints a message changed?
3. How good is the data?
4. What did an evaluation produce?
5. **What changes if a parameter changes or a component is switched off?**

## Why it exists at all

Worth being explicit, because "an admin dashboard" sounds like a feature nobody
asked for.

The product is one surface and stays one surface. But every claim the project
will make — this planner beats the baseline, this ablation shows the validator
matters, this retrieval degraded gracefully — depends on being able to look at a
single run afterwards and see what actually happened. Today that means reading
logs and re-running things locally, which means only the person who wrote a
module can check it, which means nobody checks it. The console is how a claim
becomes falsifiable by someone other than its author.

The fifth question is the one that makes it worth building rather than
inspecting by hand. Ablations and parameter tuning are part of the evaluation,
and a tuning run whose conditions were not recorded cannot be cited. Making the
recording automatic — code revision, dataset hash, seed, parameters, who ran it
— is cheaper and more honest than asking people to write it down.

It is deliberately **not** a control panel. Almost everything is read-only. The
four write actions exist because they are things the team genuinely needs to do
(run a job, stop a job, record a data decision, queue an experiment), and each
one only ever appends.

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

Boundary 5 is the one that will be tested by a real situation: a demo is
failing, a plan is refused, and the quickest fix is a button that marks it fine.
There is no such button, and adding one would make every other verdict in the
system meaningless.

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

Two details that are easy to get subtly wrong. First, *the same login form*
means one authentication path, one session, one cookie — the role decides what
is rendered and what the API allows, not a separate admin login. A second login
page is a second attack surface and a second thing to keep correct. Second,
*without disclosing why*: a refusal that says "you are not an operator" confirms
the console exists and tells an outsider what to go after. Return them home the
way any unknown route would.

## Start here

What already exists, so you do not rebuild it:

- `backend/app/models/platform.py` has `OperationRun` (trace id, run type,
  status with a check constraint, who triggered it, input digest, code commit,
  catalog and snapshot versions, warnings, artifact references, error class,
  timestamps) and `AuditEvent`. The schema for recording a run is largely there;
  the durable-job fields are what is missing.
- `backend/app/auth/authorization.py` has the four system roles and the
  permission sets. They are defined and not yet enforced on any `/ops` route,
  because there are no `/ops` routes.
- `backend/app/api/routes/` shows the existing route and dependency style;
  follow it rather than inventing a second one.
- `data-engineering/data/fixtures/ops/` holds real partial-build output —
  `quality_summary.sample.json`, released recipe and ingredient samples, and the
  dropped list with reasons. Build the data-quality module against these shapes.
  They are genuine pipeline output, not invented samples, so the field names and
  the awkward cases in them are the real ones.

```bash
cd backend && python -m pytest tests/ -q
```

The first slice worth shipping: `GET /api/ops/overview` and
`GET /api/ops/runs`, role-enforced, with the authorization tests that prove an
ordinary user is refused. That is small, it proves the access model end to end,
and everything else hangs off the same pattern.

## Modules

### System overview

API and database health, code revision, dataset version, failures in the last 24
hours by class, product-price source mix (live, cache, fixture, degraded),
queued and running job counts.

The price-source mix earns its place: "the demo used live prices" and "the demo
quietly fell back to fixtures" look identical on screen and are completely
different claims. One number here answers it.

### Task runs

List with filters (type, status, time) showing type, status, who triggered it,
duration and input digest. Detail shows the timeline, warnings, error class,
artifact references and a copyable trace id. A running job can be cancelled.

The trace id is the spine of the whole console: a plan, the retrieval it
triggered, the agent run that parsed the request and the experiment that
replayed it should all be reachable from one id. Make it copyable everywhere and
accept it in every filter.

### Data quality

Released recipe and ingredient counts, distribution by cuisine and course,
nutrition coverage, the share of values that are estimated rather than stated
(servings, times, ingredient amounts, separately), dropped candidates with their
reason, allergen rules still awaiting human confirmation, and the ingredient
mapping review queue where a reviewer records a decision.

**Estimated versus stated is reported separately on purpose.** Release v2 fills
every field, but some values come from the source and some from reasoned
inference (`ADR-0030` section 4). A single "100% complete" number would hide
that distinction, and the distinction is exactly what a reader of the report
needs. Three separate shares — servings, times, amounts — because they fail for
different reasons.

The mapping review queue is a real workflow, not a display: a reviewer opens an
unmapped or ambiguous ingredient, sees the candidates with their evidence, and
records a decision that appends. Allergen rules awaiting confirmation feed the
intake flow (`ADR-0032` section 1) — one console confirmation is one of the two
independent confirmations a shared rule needs.

Shapes are fixed by `data-engineering/data/fixtures/ops/`; see that folder's
README.

### Planning run inspector

Request, household profile version, pantry input; compiled hard constraints and
soft preferences; per-candidate rejection reasons (filterable, e.g. "rejected
for an allergen"); score breakdown; chosen slots; grocery derivation; the
independent validator's verdict; and the distinction between genuinely
infeasible, exhaustively infeasible, bounded search exhausted and needs-data.
Search statistics: expansions, pruned states, whether a limit was reached.

This is the module the owner specifically asked to keep, and it is the one that
pays for itself during debugging. The question it has to answer is not "what did
the planner output" but "why was the dish I expected not chosen" — which means
the rejection reasons have to be per candidate and filterable, not an aggregate
count. See [Planning and Validation v2](planning-validation-v2.md) for what the
planner will be emitting.

A correctness note that shapes the UI: *bounded search exhausted* is not
infeasibility. Show the four kinds as four different things, with the search
statistics next to them, or the inspector will teach the team a wrong habit.

### Retrieval monitor

Per query: terms, provider, cache or live, timestamp, candidate evidence,
warnings, parser version. Replay is from the stored snapshot; it does not call
the external site again.

Replaying from the snapshot rather than re-querying matters twice: it is polite
to the external site, and it is the only way to see what a past run actually
saw. A re-query answers a different question than the one being investigated.

### Agent trace

How a message became structured constraints and which constraints changed,
the clarification exchange, tool calls, the parser provider, and links to the
deterministic results. Redacted: message digests and structured changes only,
never the full conversation text.

The redaction is not optional politeness. Conversations contain health details,
and an internal console with a role check is still not a place to keep a
readable transcript of someone's dietary restrictions. Digests and structured
changes answer every debugging question that matters; if one day they genuinely
do not, that is a decision to revisit in a record, not in a commit.

### Experiments and ablations

Define a run: dataset, system (`greedy-baseline`, `rule-only-baseline`,
`mealcraft-planner`, context-matched LLM-only), parameters, seed, repeats, and
ablation presets that switch off a component (independent validation, repair,
meal affinity, diversity, ingredient-overlap reward, learned ranking).

Parameters come from a controlled registry — name, meaning, range, default —
covering at least beam width, expansion cap, dominance rule, meal-affinity
penalty, nutrition tolerance and the agent parser provider, plus the planning
parameters listed in [Planning and Validation
v2](planning-validation-v2.md#controlled-parameters). The console changes
registered parameters only.

**Why a registry instead of a free-form parameter field.** A free-form field is
a way to set anything, which makes every run a potential one-off configuration
nobody can reproduce or compare. A registry with ranges also gives the UI its
validation and the report its vocabulary for free. When a parameter needs to be
tunable, adding it to the registry is the work.

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

The per-episode diff is where the value is. "Overall score moved by two points"
is unactionable; "these four episodes started failing, all of them on package
coverage" is a defect report.

Integrity guards, enforced by the console rather than by discipline (decision
ADR-0020 section 2 as amended by ADR-0029 section 1):

- a held-out dataset is not offered while it is unfrozen; tuning uses synthetic
  or developer data;
- after the freeze, held-out runs are a separate "final comparison" action and
  the number of runs against a manifest is recorded;
- experiment results are labelled implementation-side evidence and are not
  circulated to episode authors before the freeze.

These are guards in code because the failure they prevent is not dishonesty, it
is a tired person at 1am picking the obvious dataset from a dropdown. Remove it
from the dropdown and the mistake becomes unavailable.

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
and audit event. "Named job" is literal: the endpoint takes a job name from a
fixed set and its declared arguments, never a command, a path or a query.

## Durable jobs

Reuse `operation_runs`, adding job payload, lease expiry, attempt count and an
idempotency key. States: `queued → running → succeeded | failed | cancelled |
degraded`. Work is claimed in a transaction and the lease renewed while running;
a crashed worker's lease expires and the job is reclaimed. Retries are bounded,
timeouts enforced, handlers idempotent. The worker is a separate container in
`compose.yaml`. No Redis or Celery.

**Why leases rather than a simple "running" flag.** A worker that dies leaves
the flag set forever and the job stuck; a lease expires and the job comes back.
**Why idempotent handlers.** A reclaimed job runs twice by design — that is the
trade for surviving a crash — so running twice has to be harmless. An import
that appends unconditionally will duplicate the catalog the first time a worker
is restarted mid-run.

**Why no Redis or Celery.** PostgreSQL is already in the stack and
`SELECT ... FOR UPDATE SKIP LOCKED` does this job at our scale. Another broker
is another container, another failure mode and another thing to explain in the
report, for a queue that handles a few jobs an hour.

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

Build the shared components first and use them everywhere. Seven pages of
bespoke tables is how an internal tool becomes unmaintainable, and the whole
point of this surface is that it stays cheap enough to keep truthful.

"Empty" deserves the same care as the others: an empty runs table on a fresh
database should say there are no runs yet, not render a broken frame that looks
like a bug.

## How to tell you did it well

- **Someone who did not build a module can debug it.** The real test: ask a
  teammate to find out why a given plan rejected the dish they expected, using
  only the console.
- **The authorization tests are boring and exhaustive.** Every endpoint, every
  role, including the ones that obviously pass.
- **A killed worker loses nothing and duplicates nothing.** Kill it mid-job on
  purpose and watch the job complete after the lease expires.
- **An experiment you ran last week can be reproduced this week from its record
  alone**, without asking you what you set.
- **Nothing in a run record or audit event would embarrass you if pasted into a
  report** — no tokens, no profiles, no raw conversation.

## Common ways this goes wrong

- Enforcing roles in the frontend and forgetting the API, so the data is one
  `curl` away.
- A refusal message that confirms the console exists.
- A write endpoint that updates a row instead of appending one, usually
  introduced as "fixing a stale status".
- Free-form parameters added "temporarily" for one experiment, after which no
  two runs are comparable.
- Job handlers that are not idempotent, discovered the first time a worker
  restarts mid-import.
- Recording an experiment's parameters but not its dataset hash, which makes
  every number in it unquotable.

## Dependency on release v2

The data-quality module reads the release build's output. Real shapes are
committed under `data-engineering/data/fixtures/ops/`, so the module can be
built and tested now.

**Only meaningful after v2**: the actual coverage and estimated-share numbers,
because they describe a catalog that is still being enriched. Build against the
fixtures; quote numbers from the real build.

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
