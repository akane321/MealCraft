# MealCraft Design Contracts

This directory is the coordination layer between product ambition, current
code, module-specific implementation work, and Evaluation v2. It exists to
prevent one domain from assuming data or behaviour that another domain never
promised to deliver.

## Status language

Every design document distinguishes three states:

- **Verified baseline**: behaviour already merged to `main` and supported by
  code or test evidence.
- **Accepted target**: the direction contributors should design toward. It is
  not evidence that the feature exists.
- **Experimental proposal**: a method that must be frozen and reviewed before
  it can produce reportable results.

Current runtime truth still comes from code, tests, generated OpenAPI, and
[Current Status](../current-status.md). These design contracts describe how the
next pieces should fit together.

## Module map

| Design area | Canonical design detail | Primary output |
| --- | --- | --- |
| Recipe and ingredient knowledge | [Recipe and Ingredient Data](recipe-ingredient-data.md) | Validated recipes, canonical ingredients, nutrition and provenance |
| FairPrice retrieval and grounding | [FairPrice Product Grounding](fairprice-product-grounding.md) | Timestamped products, package facts, ingredient-product mappings |
| Planning and deterministic validation | [Planning Engine](planning-engine.md) | Feasible plan, trace, conflict result and derived Shopping List |
| Language understanding and orchestration | [Agent Orchestration](agent-orchestration.md) | Validated user intent, clarification state and tool trace |
| Product interaction and human evidence | [Frontend and Human Evaluation](frontend-human-evaluation.md) | Understandable desktop workflow and human-task evidence |
| Comparative research evaluation | [Capability-centred Evaluation v2](comparative-evaluation-v2.md) | Fair baseline comparison, metrics, statistics and failure analysis |

## Cross-module contract matrix

| Producer | Versioned artifact | Required consumer | Contract risk if missing |
| --- | --- | --- | --- |
| Recipe data | Canonical recipe, ingredient IDs, quantities, tags, nutrition completeness and provenance | retrieval, planner, grocery mapping, Evaluation | a planner may appear correct only because unsafe or missing facts were never represented |
| FairPrice grounding | Product observation, package parse, price, availability, timestamp, mapping candidates and confidence | grocery estimator, planner, UI, Evaluation | package cost and Shopping List claims become invented or incomparable |
| Agent | Raw request link, structured constraints, missing fields, clarification and parser provenance | deterministic planner, UI, Evaluation | intent quality cannot be separated from planning quality |
| Planner | Eligibility decisions, scores, selected week, feasibility result, relaxation trace and immutable inputs | Shopping engine, UI, Evaluation | a final plan cannot be audited or fairly compared |
| Shopping engine | Consolidated demand, pantry deduction, product choice, packages, surplus and costs | UI, replanning, Evaluation | shopping consistency and budget correctness cannot be measured |
| Frontend | user choices, confirmation, timestamps, edits and task outcomes | human evaluation, product analysis | usability claims collapse into screenshots or developer opinion |
| Evaluation harness | frozen scenario packet, gold labels, system outputs, run metadata and failures | report, regression suite, all module owners | results cannot be reproduced or traced to upstream data |

## Dependency rule

No module may add a downstream metric, filter, score, or user-facing claim
unless the required upstream field has all of the following:

1. a named owner and canonical definition;
2. a versioned schema and at least one valid fixture;
3. missing/unknown semantics;
4. provenance and freshness where the fact comes from outside MealCraft;
5. validation tests and a documented hand-off to the consumer.

Conversely, a producer should not collect a high-dimensional field merely
because it is available. At least one product decision, evaluation question, or
auditable explanation must consume it.

## Change protocol

For work that crosses a module boundary:

1. state the user or evaluation value;
2. identify the producer, consumer and canonical field;
3. update the relevant design contract before or with code;
4. add a minimal fixture that both sides can use independently;
5. define unknown, invalid and degraded behaviour;
6. update API/schema contracts and focused tests;
7. report the capability only after it is merged and verified.

This supports parallel development: a consumer can build against a frozen
fixture or interface while the producer improves its implementation.

## Evaluation readiness gate

Before enabling an Evaluation v2 slice, check its upstream evidence:

| Evaluation claim | Minimum upstream evidence |
| --- | --- |
| allergen or dietary safety | ingredient-level labels, recipe composition, deterministic validator and reviewed gold cases |
| nutrition alignment | per-serving values, basis, source, completeness flags and tolerance policy |
| budget and package correctness | normalized quantities, compatible units, package parse, price snapshot and mapping gold labels |
| pantry use | known/unknown distinction, unit compatibility and deterministic deduction trace |
| preference fit | defined attributes or human labels; absence must not be treated as dissatisfaction |
| FairPrice grounding | timestamped frozen snapshot for primary comparison and separate live-degradation runs |
| replanning quality | immutable prior plan, event, locked/completed state, revised plan and expected delta |
| explanation faithfulness | machine-readable decision trace to which every explanation claim can be linked |

If a gate is not met, retain the test design as **deferred** and explain the
missing dependency. Do not substitute an unrelated proxy and call the claim
validated.
