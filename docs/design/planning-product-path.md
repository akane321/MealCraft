# Planning product adapter

`app/planning/product_path.py` is the boundary between the existing weekly
request and the explicit-slot engine. The request and HTTP response contract
live in [API contracts](../api-contracts.md#weekly-meal-plans). Implementation
status lives in [current status](../current-status.md#planning-p1-branch-work).

## Input and search

The compatibility adapter converts the requested dinner dates into slots. The
engine, compiler and validator work on that slot set. Recipe quantities are
scaled from source servings; nutrition is per person. Unit conversions use the
existing exact mass, volume and piece mappings. Unknown quantities remain
unknown, and duplicate pantry entries require clarification.

Recipes pass through `recipe_input`; mapped product observations pass through
`product_input`. The checked allergen vocabulary is explicit. An allergen
outside it produces `needs_data`. Rejected observations retain diagnostic codes;
missing evidence on an unused candidate need not prevent a verified plan.

Beam search uses the existing recommendation score as local loss
`1 - score / 100`, preserving nutrition-target, pantry and time preferences.
Its bounds use the same loss. The offline default objective is unchanged when
no loss override is supplied. Repetition and meal affinity retain the engine's
existing penalties. This is a deterministic ordering policy, not learned ranking
or a claim of optimality. Resource limits and ranking-policy version are recorded.

The explicit greedy baseline uses the old selector, then passes through the
same acceptance gate. Its own feasibility claims cannot bypass validation.

## Acceptance and storage

Search and shopping construction receive detached copies. The independent
validator recomputes against the original packet, so a planner cannot change
the quantities or constraints it will be checked against. The per-meal cost
check also recomputes from source quantities and product prices instead of
trusting the recommendation's estimate.

Only `passed` results are saved. The validated grocery rows and observations
become the stored shopping list; there is no second price lookup. The plan and
its successful `OperationRun` commit together. A rejected run records its
failure without creating a plan. Storage failures roll back both records.

The fixed shopping policy selects one product per ingredient, with known pantry
quantities deducted once across the horizon. Mixed allocations require the
separate P5 product contract and are never flattened into a single-product row.

## Trace contract

`OperationRun.run_type` is `planning`. The authenticated actor and household are
recorded, with profile ID and version when supplied. `artifact_references`
contains a `planning_trace` object under `data`, and a `meal_plan` ID on success.

The trace contains input, packet, catalog, product-observation and shopping
digests; algorithm and policy versions; beam width, expansion limit, seed,
timeout policy and dominance rule; compiled candidate decisions; search counts;
and each attempted validation verdict. There is no wall-clock timeout in this
slice: `timeout_seconds` is null, and expansion count is the search bound.

Validator checks expose code, status, hardness and scope ID. Health values,
limits, free-text details and raw profiles are omitted from operations records.
These redacted records identify and diagnose a run; they are not a complete
replay packet or a new console interface.

| Status / evidence | Meaning |
| --- | --- |
| `feasible` / `validated` | Independent checks passed. |
| `needs_clarification` / `needs_data` | The request needs a concrete correction, such as whole-cent budgets or unambiguous pantry quantities. |
| `needs_data` / `needs_data` | Required facts cannot be verified. |
| `candidate_rejected` / `bounded_search_exhausted` | No validated completion was retained; no infeasibility claim or relaxation follows. |
| `infeasible` / `exactly_infeasible` | A required slot has no eligible candidate in the supplied packet. |
| `infeasible` / `exhaustively_infeasible` | Untruncated beam enumeration completed and every validated assignment failed only a budget check under the fixed shopping policy. |

Both infeasibility claims are limited to the supplied candidate packet. They
say nothing about recipes outside the candidate limit. Planner-output defects
such as wrong package counts remain candidate rejections, never proofs.

## Acceptance tests

`backend/tests/test_planning_product_path.py` covers real authenticated requests,
both planner strategies, independent rejection of corrupted outputs, frozen
source data, missing prices, budget precision, budget recomputation, bounded
search, deterministic replay of the same observations, redaction, atomic
storage and the repository's runtime catalog. Existing profile and Agent
request tests exercise the shared service through those entry points.
