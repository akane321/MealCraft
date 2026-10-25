# Agent Scope Developer-set Evaluation

> This is a developer set used to build the reference policy. It is not final held-out evidence.

- Dataset SHA-256: `218ed2d73898aca5937d7e54c931d71184c804e1d6d172ead1206b7bbb345ed9`
- Cases: **210**
- Classification accuracy: **1.0**
- Macro-F1: **1.0**
- False accepts: **0**
- False rejects: **0**
- State contamination: **0**

## Per-class metrics

| Class | N | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| `adversarial` | 30 | 1.0 | 1.0 | 1.0 |
| `domain_action` | 60 | 1.0 | 1.0 | 1.0 |
| `domain_question` | 30 | 1.0 | 1.0 | 1.0 |
| `out_of_scope` | 30 | 1.0 | 1.0 | 1.0 |
| `partially_supported` | 15 | 1.0 | 1.0 | 1.0 |
| `restricted` | 30 | 1.0 | 1.0 | 1.0 |
| `social` | 15 | 1.0 | 1.0 | 1.0 |

## Failure cases

| ID | Expected | Actual | Reasons |
|---|---|---|---|
| - | - | - | No failures recorded |
