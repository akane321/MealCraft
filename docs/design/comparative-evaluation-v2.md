# Capability-centred Comparative Evaluation v2

## Document status

**Accepted design target; implementation is not complete.** This document
defines the next formal evaluation direction. The existing
[Protocol v1](../evaluation/protocol-v1.md) and its committed reports remain the
reproducible record of what is currently implemented.

Evaluation v2 must not be quoted as a result until its datasets, baselines,
runner, labels and preregistered analysis are versioned and executed.

## 1. Correct evaluation question

The primary question is not whether the frontend renders or the API responds.
Those are necessary engineering and UI acceptance checks. The research question
is:

> Compared with reasonable alternatives, what measurable improvement does the
> MealCraft Agent system provide for realistic weekly dietary planning?

The intended claim is:

> Compared with rule-only planning and LLM-only generation, MealCraft more
> reliably converts natural-language dietary requirements into valid,
> actionable and adaptable weekly meal plans with internally consistent grocery
> results, while reducing human effort.

This claim is deliberately multi-part. Results may support some parts and not
others. Where a baseline wins, that result must be shown and analysed.

## 2. Evidence layers

Evaluation should separate five layers instead of pooling them into one score:

| Layer | Question | Example evidence |
| --- | --- | --- |
| A. Engineering verification | Does the implementation execute reliably? | unit/integration tests, schema checks, CI, browser acceptance |
| B. Component capability | Which stage succeeds or fails? | intent F1, clarification, mapping, package parse, validator accuracy |
| C. End-to-end comparison | Does the complete system solve the task better than alternatives? | strict task success, constraint, plan and Shopping List correctness |
| D. Human utility | Does the system reduce effort and improve understanding? | completion time, edits, workload, preference, trust |
| E. Robustness and failure | How does performance change under difficult or degraded conditions? | infeasibility, ambiguity, missing data, FairPrice failure, replanning |

Layer A protects the validity of the experiment but is not the headline Agent
evaluation. Layers B-E explain both measured value and limitations.

## 3. Systems compared

### B0 — Greedy-repeat lower bound

Use the existing v1 baseline: filter eligible recipes, choose the highest-ranked
recipe and repeat it across the week. Retain it because it makes one narrow
failure mode visible, but label it a weak lower bound. It is not the only or
main competitor in v2.

### B1 — Strong Rule-only Planner

This is the primary non-LLM baseline. It receives already structured user
constraints and the same recipe/product facts as MealCraft. It should:

- apply the same hard-constraint semantics;
- use a transparent reasonable rule such as cheapest, fastest or a fixed
  preference-weighted score;
- avoid adjacent repetition when an alternative exists;
- perform deterministic pantry, package and cost calculations;
- return infeasible when no valid plan exists.

It does not parse natural language, ask proactive clarification, call tools or
maintain a multi-turn planning conversation. It must be credible, documented and
independently runnable, not deliberately weakened to favour MealCraft.

This comparison isolates the incremental value of Agent-driven requirement
understanding, clarification and orchestration beyond a conventional structured
planner.

### B2 — Context-matched LLM-only

This is the primary architecture baseline. It uses the same base model and
receives the same scenario facts as MealCraft in one frozen prompt. It returns
the same output schema but has:

- no tool calls;
- no deterministic planning algorithm;
- no deterministic package/cost validator;
- no MealCraft post-generation repair;
- no access to MealCraft's intermediate answers.

This condition tests whether an Agent-plus-tools-plus-deterministic-planner
architecture adds value beyond giving a capable LLM the relevant information.

### B3 — Plain General-purpose LLM

This baseline receives only the raw user request and ordinary conversation,
without MealCraft's private structured recipe catalog, FairPrice snapshot or
tools. It represents the realistic alternative of asking a general chatbot.

Because the information conditions are unequal, B3 is ecological supporting
evidence, not the sole basis for attributing a difference to Agent architecture.
Its unsupported products, prices or nutrition claims should be measured, not
silently corrected.

### B4 — Human Manual Planning

On a representative subset, participants receive the same request, recipe
packet, product packet and answer template. Their outputs are validated by the
same deterministic evaluator. This condition measures task time, errors,
corrections and workload.

It estimates whether MealCraft reduces routine coordination effort. It does not
compare against clinical dietitians and cannot establish clinical validity.

### B5 — Optional optimization oracle

A MILP or CP-SAT formulation may provide the best known valid solution under a
fully specified objective. It is an upper bound for cost or preference regret,
not necessarily a usable conversational product. If no exact formulation is
available, use `best observed valid result` and do not call it optimal.

### Optional ablations

If capacity permits, run MealCraft with one mechanism removed:

- no clarification;
- no FairPrice grounding;
- no deterministic post-validation;
- no replanning/minimal-disruption objective.

Ablations explain which mechanism causes an improvement, but they should not
replace the external baselines above.

## 4. Three information conditions

### A. Controlled planning condition — primary causal comparison

MealCraft, Rule-only and Context-matched LLM-only receive the same reviewed,
normalized evidence packet. This controls recipe availability, nutrition facts,
ingredient normalization and product observations so the experiment isolates
planning and orchestration mechanisms.

### B. Full-pipeline condition — end-to-end system comparison

Systems begin with raw or lightly structured recipe/product observations. This
tests normalization, retrieval, orchestration and planning together. It should
be reported separately because a failure can originate upstream of planning.

### C. Plain-assistant condition — ecological comparison

The Plain General-purpose LLM receives the user request only. This approximates
what a user could do without MealCraft, but information inequality must be
stated prominently.

Primary claims about architecture should use condition A. Condition B supports
whole-system claims; condition C supports real-world alternative framing.

## 5. Frozen Evaluation Packet

Each scenario should compile into one immutable packet:

```json
{
  "scenario_id": "heldout-v2-001",
  "scenario_category": "budget_package",
  "user_request": "raw natural-language request",
  "conversation_history": [],
  "household_profile": {},
  "pantry": [],
  "planning_horizon": {},
  "locked_or_completed_meals": [],
  "recipe_candidates": [],
  "fairprice_snapshot": [],
  "output_schema_version": "evaluation-output-v2",
  "policy_version": "planning-policy-v2"
}
```

The manifest must also record dataset version/digest, catalog version/digest,
product snapshot version/digest and timestamp, prompt/model configuration,
runner commit and random seed where applicable.

### Recipe facts shared in the controlled condition

Give every compared system the same predeclared candidate records:

- recipe ID and name;
- servings and preparation/cooking time;
- diet tags and ingredient-level allergens;
- normalized ingredient IDs, quantities and units;
- per-serving calories, protein, carbohydrate, fat, sodium and sugar with
  completeness flags;
- cuisine, taste, method, equipment and difficulty only when the catalog and
  evaluation labels genuinely support them;
- source/provenance and coverage metadata needed to avoid overclaiming.

Images, long cooking prose and tutorial media should be excluded when they are
irrelevant to the planning decision. This prevents context length from becoming
an uncontrolled variable.

### FairPrice facts shared in the controlled condition

Use one frozen timestamped snapshot containing:

- provider product ID and raw title;
- reviewed canonical ingredient mapping for the planning-only experiment;
- brand and category;
- displayed and normalized package quantity/unit;
- regular/effective observed price and promotion metadata when used;
- availability, source URL and observation time;
- multiple valid alternatives, deliberate decoys, unavailable products and
  near-name mismatches.

The packet should cover all ingredients in the candidate recipes, not just the
ingredients of MealCraft's final selections.

### Information that must not be shared as input

These values are intermediate answers and would leak the target mechanism:

- MealCraft's parsed constraint object;
- eligibility or hard-violation labels;
- planner score or rank;
- selected weekly plan or gold plan;
- selected product, required package count or grocery total;
- feasibility label;
- required clarification answer;
- expected explanation or evaluation score.

### Household and pantry facts

Share the same raw request, conversation history, household profile, planning
horizon, locked meals and pantry facts. Pantry quantities must preserve
known/unknown and unit semantics. Do not share MealCraft's computed deduction,
coverage score or resolved conflict.

## 6. Candidate-pool policy

With the current 30-recipe catalog, all systems may receive all recipes if the
context remains tractable. As the catalog grows toward 150-250 recipes, use two
separate experiments:

1. **Planning-only:** a neutral harness selects a fixed 20-30 recipe packet
   before any compared system runs. It contains valid candidates plus realistic
   decoys. Every system receives the identical packet.
2. **Retrieval plus planning:** each system searches the full frozen catalog;
   retrieval recall and downstream task success are reported separately.

Do not let MealCraft choose its own favourable candidate pool while forcing the
LLM baseline to search a larger or different set.

## 7. Prompt and generation controls

The Context-matched LLM-only prompt should explicitly request strong behaviour:

- respect all hard constraints;
- ask for necessary missing information rather than invent it;
- use only supplied recipes/products/prices;
- account for servings, known pantry quantities and package rounding;
- distinguish purchase cost from ingredient-use cost;
- report infeasibility and conflicts truthfully;
- return the specified machine-readable JSON.

Freeze this prompt before final held-out evaluation. Across LLM-based
conditions, hold constant the base model/version, temperature, language,
maximum output tokens, non-medical policy and output schema where applicable.
Record retries and parse failures. Run each stochastic condition at least three
times per scenario and retain every run, not only the best output.

The API path remains opt-in: it requires explicit provider selection, explicit
live-API permission and a runtime-only key. Default CI remains fixture-only and
must never spend API credit.

## 8. Dataset design

Retain the 20-case developer split for rapid regression. Build a new independent
held-out v2 set of approximately 80 end-to-end episodes:

| Category | Target count | Main capability stressed |
| --- | ---: | --- |
| complete ordinary requests | 12 | useful plan without unnecessary questions |
| ambiguity and clarification | 12 | missing information, contradictions, unknown pantry quantity |
| allergens, exclusions and diet | 12 | hard safety and compatibility |
| budget, package and price | 10 | product alternatives, rounding, weekly totals |
| nutrition and general health preference | 10 | user targets, lower-sodium/sugar/calorie semantics |
| pantry and near-expiry preference | 8 | known deduction versus unknown ranking only |
| infeasible and conflicting requests | 8 | truthful rejection and relaxation |
| multi-turn replanning | 8 | state retention, minimal disruption and grocery delta |

Use English, Chinese and mixed-language requests in predeclared proportions.
Include straightforward cases, combined constraints and boundary cases. Avoid
creating categories only after seeing which system performs well.

Labels should be reviewed independently by at least two people for a meaningful
subset, with disagreements resolved before freezing. Where possible, some
held-out cases should be authored by contributors who did not implement the
planner. Every correction creates a new dataset version; previously reported
digests remain available.

## 9. Gold annotations and output schema

Gold data should not prescribe one aesthetically perfect week when many plans
are valid. It should define:

- scenario class: feasible, needs clarification, or infeasible;
- required and forbidden structured fields;
- acceptable clarification field set;
- applicable hard constraints;
- valid recipe/product sets or deterministic validation rules;
- numeric targets and tolerances;
- pantry and package arithmetic ground truth;
- required warning, fallback and source disclosures;
- replanning invariants and expected changed/unaffected items.

The common output schema should preserve status, clarifying question or plan,
all explicit slot selections, servings, constraint claims, Shopping List lines, package
counts, costs, warnings, relaxation options and explanation evidence references.
Unparseable output counts as an end-to-end failure and is also reported as a
schema failure.

## 10. Primary endpoint: Strict End-to-End Task Success

Predeclare **Strict End-to-End Task Success Rate** as the primary endpoint:

```text
strict success rate = number of episodes passing every applicable required check
                      ----------------------------------------------------------
                                      total evaluated episodes
```

For a labelled feasible episode, success requires:

1. correct interpretation or completion of required clarification;
2. a complete assignment for every required slot in the frozen packet;
3. zero applicable hard-constraint violations;
4. nutrition claims calculated under the frozen semantics;
5. Shopping List ingredients consistent with the final plan;
6. correct known-pantry deduction and no unknown-quantity deduction;
7. correct package counts and costs within predeclared numeric tolerance;
8. truthful budget and data-completeness status;
9. no invented recipe, product, price or source fact.

For a labelled ambiguous episode, success requires the necessary clarification
without fabricating a final plan. For a labelled infeasible episode, success
requires rejecting false compliance, identifying the conflict and presenting
only allowed user-controlled relaxation options.

Report feasible, ambiguous and infeasible strict success separately as well as
overall. A hard-constraint failure cannot be offset by diversity or preference
score.

## 11. Secondary metrics with denominators

### Intent and clarification

- field precision = correctly populated labelled fields / all populated fields;
- field recall = correctly populated labelled fields / all required labelled
  fields;
- field F1 = harmonic mean of field precision and recall;
- exact-case rate = episodes with exact allowed fields and no hallucinated field
  / evaluated extraction episodes;
- clarification precision = required missing fields asked / all fields asked;
- clarification recall = required missing fields asked / all required missing
  fields;
- unnecessary-question rate = episodes asking at least one non-required question
  / episodes where planning could otherwise proceed.

### Safety and feasibility

- episode hard-violation rate = episodes with at least one violation / episodes
  with an applicable hard constraint;
- meal hard-violation rate = violating meal-constraint pairs / all applicable
  meal-constraint pairs;
- feasibility accuracy = correctly classified feasible/ambiguous/infeasible
  episodes / all episodes;
- false-feasible rate = infeasible episodes returned as feasible / labelled
  infeasible episodes.

### Plan quality

- required-slot completion rate over labelled feasible episodes;
- adjacent repetition count and mean distinct recipes per completed week;
- nutrition mean absolute deviation and within-tolerance rate, separately by
  nutrient and only where the source field is complete;
- preference satisfaction = satisfied labelled soft preferences / all
  applicable labelled soft preferences;
- cost regret = system valid-plan cost minus best known valid-plan cost, with
  the comparator explicitly named.

### Grocery grounding

- ingredient-line precision/recall over canonical ingredient IDs;
- quantity error only for gold quantities with compatible units;
- package-count exact-match rate over mapped required lines;
- purchase-cost MAE and ingredient-use-cost MAE in SGD;
- complete-grocery rate = feasible plans with every required line mapped or
  explicitly labelled unavailable / feasible plans;
- invented-product or invented-price rate.

### Replanning

- post-change strict validity rate;
- protected-entry preservation rate for locked/completed meals;
- unnecessary disruption = unaffected meal slots changed / all unaffected meal
  slots;
- Shopping List delta line/package/cost accuracy;
- stale-revision and unavailable-item recovery success.

### Explanation and efficiency

- trace faithfulness = explanation claims supported by authoritative trace /
  all verifiable explanation claims;
- median and distribution of end-to-end latency;
- conversation turns and unnecessary questions;
- human edits needed before acceptance;
- model input/output tokens and API cost per successful episode.

### Human utility

- validated task-completion rate;
- median completion time;
- manual correction count;
- workload and confidence ratings;
- blinded pairwise win/tie/loss and usefulness/clarity/trust/personal-fit
  ratings.

Do not publish an opaque weighted composite as the primary result. If a
secondary composite is useful, publish every weight and a sensitivity analysis.

## 12. Statistical analysis

- Evaluate systems on paired scenarios.
- For strict binary success, report absolute paired difference and a 95%
  bootstrap confidence interval; McNemar's test may be added for paired binary
  outcomes.
- For continuous or count metrics, report median and interquartile range plus a
  paired bootstrap interval; add means only when informative.
- Keep all repeated LLM runs and report run-to-run variance.
- Report inter-rater agreement for subjective or manually labelled fields.
- Predeclare the primary endpoint, exclusions, tolerances, model configuration
  and analysis before opening final held-out labels/results.
- Treat statistical significance as supporting evidence, not a substitute for
  effect size and concrete failures.

## 13. Failure registry

Analyse at least ten **distinct failure mechanisms**, not ten repeated instances
of the same weak-baseline behaviour. Each selected failure record should include:

- scenario and system/run ID;
- input packet and expected outcome;
- actual output;
- severity and affected user consequence;
- failing stage: data, parsing, clarification, retrieval, planning, mapping,
  validation, explanation or UI;
- root-cause hypothesis supported by trace evidence;
- affected metric;
- proposed fix and regression test;
- whether another baseline won and why.

The existing v1 registry has 44 records, but 36 represent the same greedy-repeat
failure pattern. It satisfies useful diagnostic coverage; it should not be
presented as 44 distinct MealCraft weaknesses or as sufficient v2 qualitative
analysis.

## 14. Dependency and claim-readiness matrix

| Capability claim | Required upstream fields/evidence | Enable when | If not ready |
| --- | --- | --- | --- |
| dietary safety | reviewed ingredient allergens, recipe composition and diet semantics | safety labels and validator gold subset pass review | keep cases deferred; do not count missing label as safe |
| nutrition alignment | per-serving nutrient value, basis, source and completeness | chosen nutrient coverage meets frozen threshold | report coverage only, not target satisfaction |
| preference fit | controlled attribute vocabulary or reviewed human labels | label agreement and coverage are stated | omit metric or report as exploratory |
| pantry savings | canonical ingredient, known quantity and compatible unit | deduction gold arithmetic exists | evaluate rank effect only for unknown quantity |
| FairPrice actionability | product candidates, package parse, price, availability and timestamp | benchmark demand has reviewed mapping states | report mapping gap rather than invented cost |
| budget superiority | complete package-aware costs under one snapshot | compared systems use identical product facts | restrict to fully mapped subset and disclose denominator |
| replanning quality | prior revision, event, locks/completions and expected deltas | immutable before/after gold cases exist | defer replan metric |
| explanation trust | authoritative trace and claim-to-trace annotation | explanations can be independently checked | evaluate readability only, not faithfulness |

The linked module contracts define how to close these dependencies:

- [Recipe and Ingredient Data](recipe-ingredient-data.md)
- [FairPrice Product Grounding](fairprice-product-grounding.md)
- [Planning Engine](planning-engine.md)
- [Agent Orchestration](agent-orchestration.md)
- [Frontend and Human Evaluation](frontend-human-evaluation.md)

## 15. Implementation phases

### Phase 1 — freeze design and contracts

- approve baseline definitions and primary claim;
- version Evaluation Packet and common output schema;
- assign every required field to a producing module;
- define category counts, tolerances and unavailable-data rules.

### Phase 2 — implement low-cost deterministic baselines

- retain B0;
- implement strong B1 on the same packet;
- implement validators and metric unit tests;
- build an initial v2 development set without viewing final held-out outcomes.

### Phase 3 — build data and held-out assets

- expand reviewed scenario labels;
- freeze recipe candidate packets and FairPrice snapshots;
- run dependency gates and publish digests;
- reserve final held-out labels from tuning.

### Phase 4 — bounded model comparison

- pilot B2 and B3 on development cases;
- freeze prompts/model settings;
- use explicit API authorization and budget controls;
- execute repeated held-out runs and retain raw structured outputs safely.

### Phase 5 — human subset and final analysis

- run B4 and blinded paired utility tasks;
- compute paired estimates and uncertainty;
- select diverse failure mechanisms;
- report limitations and cases where baselines win.

## 16. Relationship to Protocol v1

Protocol v1 remains valuable for deterministic regression, current fixture
quality, the greedy diversity lower bound and offline Agent parsing diagnostics.
Evaluation v2 adds stronger comparators, matched information, strict end-to-end
success, human effort and causal attribution.

Until v2 is implemented, public status and README metrics must continue to cite
v1. When v2 becomes executable, release it as a new version rather than silently
rewriting v1 data or reports.
