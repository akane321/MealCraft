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
ingredient rows count once per slot. This also excludes it from overlap reward.

The following names are the P3 controlled parameters. Their validated schema is
the executable range/default registry; arbitrary additional keys are rejected.

| Name | Range | Default | Meaning |
| --- | --- | --- | --- |
| `diversity_penalty` | 0 to 1, finite | 0.25 | Weight of reused core roles |
| `overlap_reward_weight` | 0 to 1, finite | 0.15 | Weight of shared non-core ingredients |
| `max_slots_per_core_ingredient` | integer 1 to 84 | 2 | Maximum selected slots containing a core ingredient |

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
