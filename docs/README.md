# MealCraft Documentation

This directory separates the final product direction from currently verified
behaviour. A roadmap item or design target is not evidence that a capability is
already implemented.

## Choose a Reading Path

### I am new to MealCraft

1. Read the repository [README](../README.md).
2. Read the [Project Guide](project-guide.md) to understand the problem, product
   principles, final design, and scope.
3. Read [Current Status](current-status.md) to distinguish verified behaviour
   from remaining work.
4. Follow the [User Guide](user-guide.md) to operate the application.

### I want to contribute

1. Complete the new-project reading path above.
2. Read [CONTRIBUTING.md](../CONTRIBUTING.md).
3. Use [Development](development.md) for environment setup, commands, debugging,
   migrations, and troubleshooting.
4. Read [Architecture](architecture.md) and [API Contracts](api-contracts.md)
   before changing a boundary between modules.
5. Read the relevant evaluation protocol before changing planning, Agent,
   grocery, nutrition, or evaluation semantics.

### I am a coding agent

1. Read [AGENTS.md](../AGENTS.md) first.
2. Follow its private-memory preflight when the repository is available.
3. Read [Project Guide](project-guide.md), [Current Status](current-status.md),
   and [Architecture](architecture.md).
4. Inspect current code and tests before treating any document as runtime fact.

### I want to understand the evidence

1. Read the [Evaluation Protocol](evaluation/protocol-v1.md).
2. Inspect the [latest workbench report](evaluation/workbench/latest.md).
3. Use the [frontend state matrix](evaluation/frontend-state-matrix.md) for the
   current browser and state coverage boundary.

## Canonical Documents

| Question | Canonical source |
| --- | --- |
| What should the final product become? | [Project Guide](project-guide.md) |
| What is verified now? | [Current Status](current-status.md) plus current code and tests |
| What is the minimum accepted baseline? | [MVP Boundary](mvp-boundary.md) |
| How is the system structured? | [Architecture](architecture.md) |
| What are the current API contracts? | [API Contracts](api-contracts.md) and generated OpenAPI |
| How do I run and debug it? | [Development](development.md) |
| How do I operate the product? | [User Guide](user-guide.md) |
| How do I contribute safely? | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| How is performance evaluated? | [Evaluation Protocol](evaluation/protocol-v1.md) |

## Documentation Update Rules

- Update `current-status.md` only after behaviour is merged and verified.
- Update `project-guide.md` when the accepted final product direction changes.
- Update `mvp-boundary.md` when minimum acceptance semantics change.
- Update `architecture.md` and `api-contracts.md` with code that changes system
  boundaries or contracts.
- Version evaluation datasets and protocols instead of silently changing
  previously reported conditions.
- Do not copy private project memory, credentials, personal data, or restricted
  course material into this public directory.
