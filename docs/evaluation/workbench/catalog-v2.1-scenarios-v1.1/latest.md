# MealCraft Evaluation Workbench

> Generated evidence. Method, split rules and metric definitions are fixed in [`protocol-v1.md`](../../protocol-v1.md).

## Run status

- Developer gate: **PASS**
- Agent provider: **fixture**
- Live API used: **no**
- Recorded failure cases: **63**

## Inputs

Every number below was computed over exactly these files. A report whose inputs differ is a different report, even where the numbers coincide.

| Input | Path | SHA-256 |
|---|---|---|
| `agent` | `data/evaluation/agent/fixture-v1.json` | `6fd3bd8d01a10f0b...` |
| `developer` | `data/evaluation/dev/planning-catalog-v2.1.json` | `103caaed048b2395...` |
| `eligibility` | `docs/evaluation/catalog-v2.1-labels.json` | `97330069ee554a91...` |
| `fixtures` | `data/fixtures/fairprice-products.json` | `19e760bd53e438fa...` |
| `grounding` | `data/evaluation/agent-orchestration/grounding-developer-v1.json` | `b8d61c8d5c107a58...` |
| `heldout` | `data/evaluation/heldout/planning-catalog-v2.1.json` | `71b1f01a3f9dc78f...` |
| `ingredients` | `data/ingredients/ingredients.json` | `c995508b5d9dde10...` |
| `recipes` | `data/recipes/recipes.json` | `f35c55874b15c3a1...` |
| `release_ingredients` | `data-engineering/data/release/v2.1/ingredients.jsonl` | `499798b92e76994b...` |
| `release_manifest` | `data-engineering/data/release/v2.1/release_manifest.json` | `7e81e661870b0fb1...` |
| `release_products` | `data/products/fairprice-v2-snapshot.json` | `2cfd10e150fd38cb...` |
| `release_recipes` | `data-engineering/data/release/v2.1/recipes.jsonl` | `df6b428714c74db6...` |
| `scope` | `data/evaluation/agent-orchestration/scope-developer-v1.json` | `062446e2467ba273...` |

## Held-out comparison

| Metric | Greedy baseline | MealCraft planner | Delta |
|---|---:|---:|---:|
| Scenario expectation rate | 1.0 | 1.0 | 0.0 |
| Mean distinct recipes | 1.0 | 6.6897 | 5.6897 |
| Consecutive repetitions | 348 | 6 | -342 |
| Failure cases | 57 | 0 | -57 |

## Held-out strong Rule-only comparison

| Metric | Rule-only baseline | MealCraft planner | Delta |
|---|---:|---:|---:|
| Scenario expectation rate | 1.0 | 1.0 | 0.0 |
| Mean distinct recipes | 1.9828 | 6.6897 | 4.7069 |
| Consecutive repetitions | 6 | 6 | -0 |
| Failure cases | 0 | 0 | -0 |

## Offline Agent benchmark

| Metric | Result |
|---|---:|
| `case_count` | 24 |
| `exact_case_rate` | 0.75 |
| `field_precision` | 1.0 |
| `field_recall` | 0.8723 |
| `field_f1` | 0.9318 |
| `hallucinated_field_count` | 0 |
| `clarification_accuracy` | 0.875 |
| `medical_boundary_accuracy` | 1.0 |
| `failure_case_count` | 6 |

## Agent scope developer set

> Diagnostic only: this set was visible during implementation and is not held-out evidence.

| Metric | Result |
|---|---:|
| `classification_accuracy` | 1.0 |
| `macro_f1` | 1.0 |
| `mutating_case_count` | 13 |
| `non_mutating_case_count` | 23 |
| `false_accept_count` | 0 |
| `false_accept_rate` | 0.0 |
| `false_reject_count` | 0 |
| `false_reject_rate` | 0.0 |
| `state_contamination_count` | 0 |
| `state_contamination_rate` | 0.0 |
| `tool_policy_accuracy` | 1.0 |
| `failure_case_count` | 0 |

## Grounding developer set

> Diagnostic only: typed claims are supplied directly; natural-language claim extraction is not evaluated.

| Metric | Result |
|---|---:|
| `verification_accuracy` | 1.0 |
| `supported_case_count` | 4 |
| `unsupported_case_count` | 8 |
| `unsupported_claim_escape_count` | 0 |
| `unsupported_claim_escape_rate` | 0.0 |
| `supported_claim_rejection_count` | 0 |
| `supported_claim_rejection_rate` | 0.0 |
| `failure_case_count` | 0 |

## Failure registry

| # | Source | Case | Reasons |
|---:|---|---|---|
| 1 | heldout-greedy-baseline | hold-001 | consecutive_recipe_repetition |
| 2 | heldout-greedy-baseline | hold-002 | consecutive_recipe_repetition |
| 3 | heldout-greedy-baseline | hold-003 | consecutive_recipe_repetition |
| 4 | heldout-greedy-baseline | hold-004 | consecutive_recipe_repetition |
| 5 | heldout-greedy-baseline | hold-005 | consecutive_recipe_repetition |
| 6 | heldout-greedy-baseline | hold-006 | consecutive_recipe_repetition |
| 7 | heldout-greedy-baseline | hold-007 | consecutive_recipe_repetition |
| 8 | heldout-greedy-baseline | hold-008 | consecutive_recipe_repetition |
| 9 | heldout-greedy-baseline | hold-009 | consecutive_recipe_repetition |
| 10 | heldout-greedy-baseline | hold-010 | consecutive_recipe_repetition |
| 11 | heldout-greedy-baseline | hold-011 | consecutive_recipe_repetition |
| 12 | heldout-greedy-baseline | hold-012 | consecutive_recipe_repetition |
| 13 | heldout-greedy-baseline | hold-013 | consecutive_recipe_repetition |
| 14 | heldout-greedy-baseline | hold-014 | consecutive_recipe_repetition |
| 15 | heldout-greedy-baseline | hold-015 | consecutive_recipe_repetition |
| 16 | heldout-greedy-baseline | hold-016 | consecutive_recipe_repetition |
| 17 | heldout-greedy-baseline | hold-017 | consecutive_recipe_repetition |
| 18 | heldout-greedy-baseline | hold-018 | consecutive_recipe_repetition |
| 19 | heldout-greedy-baseline | hold-019 | consecutive_recipe_repetition |
| 20 | heldout-greedy-baseline | hold-020 | consecutive_recipe_repetition |
| 21 | heldout-greedy-baseline | hold-021 | consecutive_recipe_repetition |
| 22 | heldout-greedy-baseline | hold-022 | consecutive_recipe_repetition |
| 23 | heldout-greedy-baseline | hold-023 | consecutive_recipe_repetition |
| 24 | heldout-greedy-baseline | hold-024 | consecutive_recipe_repetition |
| 25 | heldout-greedy-baseline | hold-025 | consecutive_recipe_repetition |
| 26 | heldout-greedy-baseline | hold-026 | consecutive_recipe_repetition |
| 27 | heldout-greedy-baseline | hold-027 | consecutive_recipe_repetition |
| 28 | heldout-greedy-baseline | hold-028 | consecutive_recipe_repetition |
| 29 | heldout-greedy-baseline | hold-029 | consecutive_recipe_repetition |
| 30 | heldout-greedy-baseline | hold-030 | consecutive_recipe_repetition |
| 31 | heldout-greedy-baseline | hold-031 | consecutive_recipe_repetition |
| 32 | heldout-greedy-baseline | hold-032 | consecutive_recipe_repetition |
| 33 | heldout-greedy-baseline | hold-033 | consecutive_recipe_repetition |
| 34 | heldout-greedy-baseline | hold-034 | consecutive_recipe_repetition |
| 35 | heldout-greedy-baseline | hold-035 | consecutive_recipe_repetition |
| 36 | heldout-greedy-baseline | hold-036 | consecutive_recipe_repetition |
| 37 | heldout-greedy-baseline | hold-037 | consecutive_recipe_repetition |
| 38 | heldout-greedy-baseline | hold-101 | consecutive_recipe_repetition |
| 39 | heldout-greedy-baseline | hold-102 | consecutive_recipe_repetition |
| 40 | heldout-greedy-baseline | hold-103 | consecutive_recipe_repetition |
| 41 | heldout-greedy-baseline | hold-104 | consecutive_recipe_repetition |
| 42 | heldout-greedy-baseline | hold-105 | consecutive_recipe_repetition |
| 43 | heldout-greedy-baseline | hold-106 | consecutive_recipe_repetition |
| 44 | heldout-greedy-baseline | hold-107 | consecutive_recipe_repetition |
| 45 | heldout-greedy-baseline | hold-108 | consecutive_recipe_repetition |
| 46 | heldout-greedy-baseline | hold-109 | consecutive_recipe_repetition |
| 47 | heldout-greedy-baseline | hold-110 | consecutive_recipe_repetition |
| 48 | heldout-greedy-baseline | hold-111 | consecutive_recipe_repetition |
| 49 | heldout-greedy-baseline | hold-112 | consecutive_recipe_repetition |
| 50 | heldout-greedy-baseline | hold-113 | consecutive_recipe_repetition |
| 51 | heldout-greedy-baseline | hold-114 | consecutive_recipe_repetition |
| 52 | heldout-greedy-baseline | hold-115 | consecutive_recipe_repetition |
| 53 | heldout-greedy-baseline | hold-116 | consecutive_recipe_repetition |
| 54 | heldout-greedy-baseline | hold-117 | consecutive_recipe_repetition |
| 55 | heldout-greedy-baseline | hold-118 | consecutive_recipe_repetition |
| 56 | heldout-greedy-baseline | hold-119 | consecutive_recipe_repetition |
| 57 | heldout-greedy-baseline | hold-120 | consecutive_recipe_repetition |
| 58 | agent-benchmark | agent-005 | extraction_mismatch, clarification_mismatch |
| 59 | agent-benchmark | agent-016 | extraction_mismatch, clarification_mismatch |
| 60 | agent-benchmark | agent-017 | extraction_mismatch |
| 61 | agent-benchmark | agent-018 | extraction_mismatch |
| 62 | agent-benchmark | agent-019 | extraction_mismatch |
| 63 | agent-benchmark | agent-024 | extraction_mismatch, clarification_mismatch |
