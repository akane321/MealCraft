# Planning diversity packet

This contract implements the packet-level rules in
[Planning and Validation v2, P3](planning-validation-v2.md#p3--bound-variety-and-ingredient-overlap-then-trade-them-off).
Deployment and integration status belongs in [Current Status](../current-status.md).

## Producer and classification

Planning owns `PlanningDiversityPolicy` in `app/schemas/planning_v2.py` and the
synthetic example `data/fixtures/planning-v2/diversity-dev-v1.json`.
The catalog producer must supply explicit recipe roles before production
integration; the planner does not derive them from titles, quantities or a model.
No data-engineering records are changed by this implementation.

The policy records its schema version, classification version and complete rule
text. `classifications` maps recipe IDs to:

- `core_ingredient_ids`: the primary protein ingredients or ingredients that
  define the dish; at least one, unique, and present in the recipe;
- `primary_proteins`: a mapping from core ingredient IDs to stable protein-group
  IDs, so variants of one protein can share a group. An empty mapping explicitly
  means no primary protein; it does not mean unclassified;
- `source_reference`: the source or authoring reference for that classification.

The supplied rule must state how group IDs are assigned. These are assertions
from the producer, not proof that the classification is accurate. The synthetic
fixture's labels are authored test facts, not annotations for the real catalog.

Missing recipe classification yields an indeterminate check when the recipe is
selected. Missing data is never a compliant empty list. Unknown recipe IDs or
core ingredients absent from a recipe are rejected by packet parsing. Missing
classification on an unused recipe does not invalidate a fully known plan.
`diversity_policy: null` preserves older packets and provides no P3 guarantee.

## Constraints and scoring

Recipe IDs may appear only once. Consecutive occupied slots may not share a
primary-protein group. Slots are ordered by date, breakfast/lunch/dinner/snack,
then slot ID; skipping an optional slot does not break adjacency.

A core ingredient anywhere in the packet counts toward its cap wherever it
appears in the selected plan, including another recipe's non-core row. Repeated
ingredient rows count once per dish (one dish equals one slot in the original packet). This also excludes it from overlap reward.

The following names are the P3 controlled parameters. Their validated schema is
the executable range/default registry; arbitrary additional keys are rejected.

| Name | Range | Default | Meaning |
| --- | --- | --- | --- |
| `diversity_penalty` | 0 to 1, finite | 0.25 | Weight of reused core roles |
| `overlap_reward_weight` | 0 to 1, finite | 0.15 | Weight of shared non-core ingredients |
| `max_slots_per_core_ingredient` | integer 1 to 84 | 2 | Maximum selected dishes containing a core ingredient (legacy field name) |

For each added recipe, variety loss is the fraction of its core roles already
used. Overlap is the fraction of its non-core ingredient IDs seen in earlier
classified recipes. Both fractions lie between zero and one. Each increment is
`0.10 / slot_count * (diversity_penalty * variety - overlap_reward_weight * overlap)`.
The entire horizon's reward and penalty are each bounded by 0.10. This can
change close soft-score decisions; it cannot reverse hard constraints. No claim
is made that every tiny nutrition-score difference dominates the reward.
Zero weights disable soft terms only; the three hard rules remain active.
These defaults are developer settings, not tuned or frozen benchmark results.

Beam and greedy reference selection prune known violations before scoring.
The validator independently recounts the final assignments from frozen roles,
without reading a search score or calling the search guard. An exhaustive
oracle checks assignments through that validator and uses the same declared
objective. It proves optimality only within its existing fixed shopping policy.
Beam lower bounds include the maximum remaining negative reward, preventing a
positive-only bound from incorrectly evaluating promising continuations.

The trace includes the complete policy, classifications and parameter values.
The original packet is unchanged. Purchasing and nutrition arithmetic are
unchanged; overlap is a preference signal, not evidence of a cheaper checkout.
Console wiring and production catalog classification are separate integration
steps. A caller must not describe an unclassified legacy result as P3 compliant.

## Recipe-pair signals for the next diversity policy

`app/planning/recipe_pair_similarity.py` prepares a supplied candidate pool and
returns three separate signals for each pair: Jaccard overlap of cleaned title
words, Jaccard overlap of canonical ingredient names, and cosine similarity of
the committed recipe vectors. Ingredient rows are deduplicated; quantities and
ingredient hierarchy equivalence are not inferred. Shared ingredients alone do
not mean two dishes are equivalent: tomato soup and tomato salad may share them.

The vector source records its model, dimensions and source-text digest. Stored
signed int8 rows are normalized before comparison. Missing, zero or truncated
rows yield an unknown vector signal, never a zero similarity or a perfect match.
Empty title or ingredient evidence is unknown too. No model request is made.
The vector snapshot's digest identifies its source; it does not verify that a
recipe edited since embedding still has a matching vector.

This is a signal calculation component for developer calibration. It does not
alter product ranking, change eligibility or replace the
independent validator. A near-duplicate threshold and grouping policy must be
checked on developer examples before these signals decide the new shared
objective; existing title-based product ordering remains in place meanwhile.

The developer calibration now lives in `docs/evaluation/algorithm-dev/`.
`algorithm_objective.py` and `diversity_greedy.py` consume an explicitly supplied
policy in a separate experimental algorithm arm. Product defaults are unchanged.
The ordering is lexicographic: fill optional positions, maximize conservative
distinct representatives, minimize repeat pairs, normalized soft nutrition
deviation, declared ranking loss, then exact package checkout cost. Representatives
are selected in stable key order, accepting only keys distinct from every prior
representative. This is a conservative count, not maximum independent-set
optimization. Unknown pairs earn no distinctness credit and incur repeat cost.
Staple exemptions follow the problem; hard constraints remain hard.

The greedy arm reuses meal candidate generation and checks exact package cost
with one-meal lookahead. A complete result must pass the independent validator.
Search failure does not prove infeasibility. The shared objective can rescore
other validated results, but existing beam search has not been changed to
optimize it. Comparisons must freeze candidates, limits, ranking inputs and
nutrition scales before drawing conclusions about algorithm quality.

`near_duplicate_groups.py` provides an experimental consumer with explicit,
versioned thresholds and no production defaults. All three signals must meet
their thresholds; missing evidence yields `unknown`. It builds complete-link
groups in stable key order, so every pair inside a group is near under the
supplied policy. This avoids transitive chains merging dissimilar endpoints.
It is not an optimal-clustering claim. Unknown pairs and all near pairs are
returned alongside the groups: two groups may still contain a near pair, so
group count alone must not be presented as proven variety. Synthetic test
thresholds verify mechanics only, not catalog accuracy or calibration.


## Composed meal soft terms

With an explicit policy, MealBeamPlanner computes the existing per-dish
increment in role order, including earlier dishes of the same meal, and averages
the increments within the meal. Across the explicit slot set, both reward and
penalty therefore remain bounded by 0.10, independent of the number of roles.
The trace identifies this consumer as `meal-beam-diversity-v2`; packets without
an explicit policy retain their existing repetition policy. Hard caps still
count dishes, and within-meal and adjacent-meal protein guards remain unchanged.
Turning either soft weight to zero never disables those checks. CP-SAT does not
model an explicit diversity policy, so it supplies no optimum for this condition.
