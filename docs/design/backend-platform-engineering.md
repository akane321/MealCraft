# Backend Platform Engineering Handoff

## Status and purpose

This document defines the accepted final backend direction and the handoff for
the contributor completing it. MealCraft already has useful FastAPI,
PostgreSQL, repository, planning, Agent and Dashboard foundations, but its
current HTTP surface is still an anonymous single-tenant baseline.

This branch adds an additive persistence scaffold:

- account, credential and revocable authentication-session models;
- household and household-membership models;
- operations-run and append-only audit-event models;
- an Alembic migration;
- opaque session-token hashing utilities;
- household and system-operations permission matrices;
- low-level identity persistence methods;
- synthetic cross-household isolation fixtures and focused tests.

It deliberately does **not** expose registration/login routes or claim that
existing plans, profiles and Agent sessions are user-isolated. Wiring an
incomplete authentication dependency into selected routes would create a false
security boundary. The remaining work packages below must be completed before
MealCraft is described as a multi-user application.

## Final backend goal

Deliver a software backend that can:

1. register and authenticate users safely;
2. revoke login sessions and manage signed-in devices;
3. isolate all private data by authorized household;
4. represent account users separately from people included in dietary planning;
5. preserve plan, Agent, Shopping List and Dashboard history per household;
6. execute durable imports, retrieval, planning and evaluation jobs;
7. expose auditable traces through an authorized Operations Console;
8. support account export, deletion and operational recovery;
9. preserve deterministic safety, nutrition, package and cost authority.

## Identity concepts must remain separate

| Concept | Meaning | Must not be confused with |
| --- | --- | --- |
| `User` | Login identity with email, product settings and system role | a dietary household member |
| `UserCredential` | Password verifier and lock state | plaintext password or API key |
| `AuthSession` | Revocable browser/device login session | `AgentSession` conversation history |
| `Household` | Tenant and private-data ownership boundary | the versioned planning profile itself |
| `HouseholdMembership` | A user's access role in a household | a person who receives meal servings |
| dietary member | Person represented inside a profile version, optionally linked to a user | permission to access the software |
| system role | Permission to use internal Operations functions | household ownership |

A parent can own an account and plan for children who have no account. A
household owner is not automatically a system administrator.

## Authentication design

### Password boundary

The application receives a password only at registration, login, password
change or reset. A reviewed password-hashing adapter should use Argon2id with a
versioned policy and constant-time verification. The database stores only the
encoded password hash. Logs, traces, audit metadata and error responses must
never contain the password.

The scaffold intentionally stores an externally produced `password_hash` and
does not implement an improvised password algorithm. The contributor must add a
maintained password-hashing dependency, its policy wrapper, upgrade-on-login
behaviour and tests before exposing login.

### Recommended session model

Use a server-side opaque session for the same-origin web application:

1. generate at least 32 random bytes;
2. return the raw token once in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie;
3. persist only a SHA-256 token digest;
4. reject expired, revoked, missing or suspended-user sessions;
5. rotate on login, privilege change and password change;
6. revoke on logout and allow the user to revoke another device;
7. update `last_seen_at` with bounded write frequency.

Production should serve Nuxt and `/api` from one site or reverse proxy. Local
development can proxy `/api` through Nuxt; do not weaken cookie policy globally
to accommodate two unrelated origins. State-changing cookie requests require a
reviewed CSRF policy.

### Account abuse controls

- generic login errors that do not reveal whether an email exists;
- per-account and per-origin rate limits;
- increasing backoff and temporary lock state;
- email verification and password-reset tokens stored as hashes with expiry and
  one-time consumption;
- session revocation after password reset;
- no credential or token values in OperationRun or AuditEvent.

Email delivery can use an explicit development sink until a provider is
selected. A development verification shortcut must be unavailable in production
and visibly documented.

## Tenant and ownership model

Every private resource must resolve through an authorized household. The target
chain is:

```text
request cookie
  -> AuthSession token digest
  -> active User
  -> active HouseholdMembership
  -> household-scoped repository query
  -> private resource
```

The repository query itself must include `household_id`. Fetching an object by
global ID and checking ownership only after serialization is unsafe.

Target private ownership includes:

- household profile and immutable profile versions;
- meal plans, entries, check-ins, Shopping Lists and replanning events;
- Agent sessions and messages;
- pantry facts, favourites and recipe feedback;
- planning/retrieval runs whose payload contains household inputs;
- exports and account-lifecycle jobs.

Public recipe/ingredient releases, generic FairPrice observations, algorithms
and public evaluation fixtures can remain shared. A product observation becomes
private only when linked to a user's request or Shopping List trace.

## Migration sequence

The additive `20260906_0010` migration creates the foundation only. Complete
multi-tenancy should use staged migrations:

1. create users, credentials, auth sessions, households and memberships;
2. create a documented development/bootstrap account and legacy household
   through an explicit command, never a hard-coded production password;
3. add nullable `household_id` to private domain tables;
4. backfill existing rows to the selected legacy household;
5. add foreign keys and indexes;
6. update every repository and route to require the authorized scope;
7. verify cross-household denial and then make ownership non-null;
8. remove the global `current household` assumption only after the frontend and
   API migration are complete.

Do not combine destructive cleanup with the first ownership migration. Preserve
the current demo data and provide a reversible downgrade until the migration is
accepted.

## Planned API surface

These are target contracts, not current endpoints:

```text
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me
GET    /api/auth/sessions
DELETE /api/auth/sessions/{session_id}
POST   /api/auth/password/change
POST   /api/auth/password-reset/request
POST   /api/auth/password-reset/confirm

GET    /api/households
POST   /api/households
GET    /api/households/{household_id}
GET    /api/households/{household_id}/memberships
POST   /api/households/{household_id}/invitations
PATCH  /api/households/{household_id}/memberships/{user_id}
DELETE /api/households/{household_id}/memberships/{user_id}

GET    /api/me/settings
PUT    /api/me/settings
POST   /api/me/data-export
DELETE /api/me
```

Authentication and authorization dependencies should be defined once and
injected into routes. Business routes must not parse cookies independently.
Use generic unauthenticated responses and consistent 403/404 behaviour that
does not expose another household's resource existence.

## Operations Console and observability

The internal `/ops` product surface is a consumer of backend trace contracts,
not a replacement for identity or tenancy. Recommended modules are:

1. **System Overview**: database/provider status, code and dataset versions,
   recent failures and live/cache/fixture/degraded distribution;
2. **Planning Run Inspector**: input, parsed constraints, candidate rejection,
   scores, selected slots, grocery derivation and independent validation;
3. **Data Quality and Mapping Review**: release coverage, normalization errors,
   missing nutrition and review-gated ingredient-product mappings;
4. **Retrieval Monitor**: query, provider, cache, timestamp, candidate evidence,
   warnings, parser drift and safe replay;
5. **Agent Trace**: message-to-constraint state changes, clarification, tool
   calls, parser provider and links to deterministic results;
6. **Evaluation Console**: frozen dataset/method selection, offline runs,
   comparative metrics and failure registry.

Read-only inspection is the default. Retrying a job or approving a mapping
creates a new OperationRun/AuditEvent; it never overwrites historical evidence.
The Console must not expose raw SQL, secrets, plaintext personal data, arbitrary
filesystem access, or a button that changes a failed plan to `feasible`.

## Run and audit contracts

`OperationRun` is the common envelope for imports, retrieval, planning,
evaluation and export work. It records status, trace ID, input digest, code and
data versions, provider mode, warnings, error classification and artifact
references. Large or sensitive payloads should live in a controlled artifact
store and be referenced by digest, not copied into a generic JSON column.

`AuditEvent` records who performed a state-changing action, which household and
target were affected, before/after digests and minimal safe metadata. Audit
events are append-only. They must not contain passwords, raw session tokens,
OpenAI keys, cookies or unrestricted health-profile payloads.

## Durable background work

Data imports, live retrieval batches, planning searches, exports and Evaluation
runs should not depend only on FastAPI in-process background tasks. The first
implementation can use a PostgreSQL-backed job table and a separate worker
container:

```text
queued -> running -> succeeded | failed | cancelled | degraded
```

Claim work transactionally, record progress, enforce retry limits and make
handlers idempotent. Redis/Celery is optional only when measured throughput or
scheduling requirements justify another service.

## Security and privacy invariants

- password and token material never enters logs, traces, fixtures or Git;
- only token digests are stored server-side;
- account status and session revocation are checked for every protected request;
- all private repository queries are household-scoped;
- household role and system role remain independent;
- ordinary users cannot access `/api/ops`;
- deletion/export is explicit, authenticated and audited;
- planning health fields are minimized and never used for medical claims;
- deterministic services remain the authority for allergens, nutrition,
  packages, costs and validation.

## Work packages left for the backend contributor

1. **Password adapter**: add Argon2id, policy versioning, verification,
   upgrade-on-login and secret-leak tests.
2. **Authentication service and routes**: registration, login, logout, current
   actor, device sessions, cookie and CSRF policy.
3. **Account lifecycle**: email verification, reset tokens, password change,
   suspension, export and deletion.
4. **Tenant migration**: add/backfill household ownership across every private
   domain table and remove global-current assumptions.
5. **Authorization layer**: reusable current-user/current-household
   dependencies plus route and repository enforcement.
6. **Household collaboration**: invitations, membership roles and dietary
   people optionally linked to accounts.
7. **Isolation tests**: Alice/Bob adversarial API tests for every private
   endpoint, including guessed IDs and Agent/plan history.
8. **Operations persistence**: repositories/services for OperationRun,
   AuditEvent and safe artifact references.
9. **Durable jobs**: PostgreSQL worker, retry/idempotency policy, health and
   cancellation.
10. **Operations APIs and Console integration**: role-protected read models,
    planning inspector, data/retrieval/Agent/evaluation views and safe actions.
11. **Deployment hardening**: reverse proxy, secure cookie configuration,
    trusted hosts, rate limiting, secret rotation, backups and restore drill.
12. **Documentation and evaluation**: threat model, OpenAPI, migrations,
    failure states, usability tasks and reproducible evidence.

## Definition of done

- a user can register, log in, reload, log out and revoke another session;
- passwords use the reviewed adaptive hash and never appear outside the
  credential boundary;
- all private resources have a non-null household ownership path;
- Alice cannot read or mutate Bob's profile, plan, check-in, Shopping List or
  Agent session, including by guessing IDs;
- dietary household members can exist without login accounts;
- household and system permissions are independently tested;
- migration from the current demo state is reversible and preserves history;
- background work survives an API-process restart and has bounded retries;
- Console actions are authorized, auditable and cannot override deterministic
  validation;
- account export/deletion semantics are documented and tested;
- no real credential, token, cookie or personal health data exists in fixtures,
  logs or repository history;
- current anonymous behaviour is not called multi-user until the complete route
  and ownership migration is merged and verified.
