# Experimental whole-plan scoring

Status: experimental implementation, pending team review and parameter freezing. The original reference policy remains the default. Enable this candidate policy with `WholePlanPolicy()` or workbench `--whole-plan` for plan, oracle and repair.

## Rules in whole-plan-experiment-v1

Weights come from the existing problem.preference_weights contract. Each active loss is between zero and one. The weighted sum is divided by active positive weights. A dimension with no observations is omitted. All zero weights yield zero. Hard validation remains lexicographically ahead of preference loss.

- Nutrition: only user-entered soft bands contribute. Values are per person, with per-slot, per-day and current validator horizon-average scopes. Deviation outside the band, less the configurable numeric tolerance (default 1e-6), is divided by max(1, supplied lower, supplied upper), capped at one. The unit floor of one is an explicit experimental normalization choice, not a target. Observations across bands are averaged equally; differing scope counts can affect their relative influence and require development review.
- Variety: (number selected - unique recipe count)/(number selected - 1), inactive for zero or one selection.
- Time: mean cooking time divided by each selected slot's explicit time limit, capped at one. Slots without limits are omitted.
- Pantry: fraction of declared priority ingredient IDs not used. Unknown quantities may participate in this preference; no quantity deduction or savings claim follows.
- Health: sodium uses the accepted energy-proportional reference curve. Lower-sugar and lower-calorie preferences use the selected nutrient's position in the frozen candidate catalog's min/max range. Constant ranges are inactive. This is relative ranking, not a recommended intake. Catalog changes can affect scores and must be versioned.

The result reports policy version, total loss, component losses, weights and reasons. The scorer rejects incomplete mandatory assignments but does not replace the hard validator.

## Search and oracle

Completed beam candidates are ranked by the selected whole-plan objective after validity. Partial experimental states use an optimistic soft-nutrition lower bound; other losses contribute a zero lower bound, and reference loss breaks ties. The bound uses maximum possible observation/weight denominators to avoid overestimation. Reference state dominance is disabled in experimental mode because it does not preserve every new component, such as which time-limited optional slot was used.

The small exhaustive oracle accepts the same scoring policy. Its optimality scope remains the finite candidate packet and fixed reference shopping policy. Mixed-product shopping is not integrated into this V2 output.

## Reproducible developer comparison

From backend:

```text
python -m app.planning.developer_comparison ../data/fixtures/planning-v2/final-scope-multislot.json
python -m app.planning.workbench plan ../data/fixtures/planning-v2/final-scope-multislot.json --whole-plan --width 32
```

The comparison creates eight synthetic packets from the fixture: four protein lower bounds and two nutrition/time weight settings. Each has three slots and three recipes. It compares greedy, reference Beam and experimental Beam at widths 1/4/16/32, with three repeats and the same inputs. It records input hashes, whole-plan loss, oracle gap, status, deterministic output and elapsed time. No held-out data or live API is used.

Observed local mean gaps to the experimental oracle were 0.2222 for greedy and 0.00694/0.00347/0.00347/0 for experimental widths 1/4/16/32. All eight scenarios were feasible under every tested method. This deliberately small, nutrition-focused developer set demonstrates the mechanism and known width sensitivity; it does not prove production superiority or justify a final weight choice.

Verification: 184 targeted Planning tests passed on the upload candidate; Ruff checks passed. Hand-calculated target deviations, each scope, masking, unknown pantry preference, hard-constraint priority, relative sugar ranking and exhaustive lower-bound checks are included.

## Still pending

Broader independent scenarios, quality/runtime tradeoffs, policy review and final freezing are required. Production endpoints, persistence, Agent and UI consumers have not been changed. The mixed-package result contract and Retrieval provider adapter still require cross-module integration. No overall-project completion claim is made.
