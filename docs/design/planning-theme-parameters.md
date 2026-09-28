# Planning theme proposal gate

`app.planning.theme_parameters.apply_theme_parameters` checks structured theme
proposals against existing Planning consumers. It is default off and is not
called by a product route. It does not translate natural language or invoke an
LLM; the Agent owner supplies that translation through an agreed interface.

The enabled gate accepts only `diversity_penalty` and `overlap_reward_weight`,
using their existing `PlanningDiversityPolicy` definitions: finite numbers from
zero to one. Strings, booleans, nonfinite values and out-of-range values are
dropped without conversion or clamping. A packet must already carry its explicit
classification policy; the gate cannot infer core ingredients or protein groups.

It returns a detached problem with only those soft weights updated. All recipes,
ingredient facts, prices, pantry, nutrition, hard caps and user constraints remain
unchanged. A theme cannot select a recipe, change a budget, remove an allergen,
raise a core-ingredient cap, activate learned ranking or expand search limits.
The full plan must still pass the independent validator after search.

The trace records the gate version, enabled state, applied weights and dropped
field names with reasons. It does not copy rejected values or raw theme text.
Proposals are handled in sorted key order for reproducibility. Disabled mode
returns an unchanged detached packet and records every proposed field as disabled.

## Fields that need a consumer agreement

P7's narrative mentions cuisine affinity, energy preference and weekday effort.
The controlled parameter table does not define cuisine or energy theme fields,
and the current candidate contract has no difficulty field for the stated effort
consumer. The table names `effort_rhythm_weight`, but naming a weight does not
define its input normalization, scope or scoring behavior.

The gate therefore records `cuisine_affinity`, `energy_preference` and
`effort_rhythm_weight` as `consumer_contract_pending`. It applies none of them.
This is a visible limitation of the adapter, not completed theme support. These
fields need an agreed schema, missing-value behavior, scope and versioned scoring
fixture before activation. The gate deliberately implements a smaller subset of
the console's controlled list: operational settings and hard caps are not theme
weights.

Tests in `backend/tests/test_theme_parameters.py` cover off-list requests,
malformed weights, missing classifications, detached inputs, deterministic trace
ordering and independently validated plans with the gate on and off. They use the
existing synthetic diversity fixture. Product Agent translation, console controls
and the pending preference consumers remain separate integration work.
