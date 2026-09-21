# Planning conflict explanations

`app/planning/conflict_explanation.py` explains an independently established
`exactly_infeasible` or `exhaustively_infeasible` outcome. A bounded search miss
and missing evidence never start a relaxation search.

## Candidate evidence

An empty recommendation list may have removed every slower recipe. It cannot
support a claim about whether more cooking time would help. The plan service
can collect diagnostic candidates with the API's maximum cooking time and
without the dietary filter. It still applies the original request to the
compiler and validator. Allergen, ingredient-exclusion, sodium and per-meal
budget admission checks remain fixed.

An infeasible result from a nonempty filtered pool gets at most one such
expanded attempt. Existing candidate quotes are retained. The expanded packet
must establish its own result; its prior attempt is retained in the run trace.
Conflicting observations, missing facts and search limits cannot inherit the
earlier packet's infeasibility claim.

## Conflict and proposal proofs

Counterfactuals enumerate subsets of three declared groups: cooking time,
weekly purchase budget and dietary requirements. Allergens, ingredient
exclusions, hard nutrition bands, locked slots and the per-meal cost ceiling
remain fixed. A conflict is minimum-cardinality **among these groups, relative
to those fixed constraints and this candidate packet**. It is not a global
claim over an unrestricted recipe catalog or every individual request field.
An unknown smaller subset prevents a minimality claim. If even the empty subset
is infeasible, fixed constraints block the packet and no relaxation is offered.

Only cooking time and purchase budget can appear in proposals. Dietary
requirements may appear in the diagnosed conflict but stay fixed in every
suggested solution. Hard nutrition bands and allergens never become priced
options or suggestions.

Declared options come from validated witnesses with time, budget or both
temporarily released for diagnosis. Time discovery also tries the first eight
observed recipe-time breakpoints. `propose_relaxations` checks each declared
set, retaining its `minimal_in_declared_options` or
`candidate_without_minimality_proof` label. Option cost counts changed fields;
it does not equate a dollar with a minute. Each proposal has its own declared
set, so there is no claim of a global smallest numeric adjustment.

Every retained witness passes the independent validator and the existing
per-meal cost check. The input packet is never mutated. At most three proposals
are retained. Each oracle invocation is capped at 256 raw assignments and each
declared proposal at eight options; oversized searches withhold a suggestion
rather than fabricate proof. These limits are recorded in the trace.

## Product and operations

The existing HTTP 422 `detail` contains one sentence identifying the conflict
and any verified numeric choices. A suggestion is not a saved plan or an
automatic update. The user chooses new values and submits a new request through
the same authenticated generation and validation path. Suggestions beyond the
weekly request schema's numeric limits are not rendered.

`OperationRun` stores the explanation status, conflict group IDs, proof scope,
declared options, validated witness IDs and counters. It does not copy raw
health-profile values into the explanation. No new Console or Agent interface
is introduced by this adapter.

Acceptance tests are `test_conflict_explanation.py` and
`test_product_conflict_explanation.py`: joint conflicts, safety-only failures,
missing evidence, search limits, determinism, candidate-pool expansion,
explicit resubmission and validated numeric witnesses.
