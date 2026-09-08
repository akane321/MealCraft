# Beam Search bounds and local validation

The standalone BeamPlanner consumes compiled slot domains and retains a bounded set of partial plans. It uses the existing reference local loss and repetition penalties; weights have not been tuned. Slot traversal stays chronological so adjacency retains its established meaning.

SearchBounds adds an optimistic remaining-loss bound: each required future slot contributes its cheapest local loss plus repetitions already incurred by its candidate. Future adjacency and future repetition increments are omitted because they are nonnegative. Optional future slots contribute zero. The bound orders beam candidates; it is not an optimality certificate.

For hard daily nutrition bands, the search adds the minimum and maximum possible remaining nutrient amounts to the partial total. It rejects a state only when this interval cannot reach the target. Soft bands never prune. Horizon-average bounds are used only when every represented date has a required or locked meal. When optional-only dates can be skipped, pruning is deferred to avoid assuming a denominator inconsistent with the existing validator.

Dominance uses the per-day multiset of recipe IDs and requested servings, plus the last selected recipe. These retain nutrition, shopping demand, repetition counts and future adjacency. For equivalent states the lower accumulated loss wins; stable assignment IDs break ties. This deliberately conservative key avoids approximate quantity bucketing.

Every retained complete plan goes through independent validation. A resource limit returns candidate_rejected without a partial plan. Trace warnings include expansion counts, width pruning, nutrition pruning and dominance counts. No global infeasibility or optimality claim is made.

Local verification: 63 tests passed across bounds, beam, shopping validation, compiler and original V2 tests; Ruff passed. Small exhaustive tests check bound admissibility, preservation of valid nutrition completions and agreement with the exhaustive objective on a toy packet. These tests do not establish general production performance.

A five-repeat developer smoke benchmark compared greedy and widths 1/4/16/32 on the existing fixture and a synthetic six-slot/four-recipe packet. All runs were feasible and deterministic. Synthetic median times were 0.106 ms for greedy and 0.330/1.248/3.307/5.386 ms for beam. These local measurements do not select production parameters. Broader datasets, objective-quality comparisons and controlled ablations remain necessary before evaluation claims or parameter freezing. The default width 32 and expansion cap 10000 remain development settings.
