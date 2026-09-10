# Beam Search bounds and local validation

> **Scope of this document.** It is a component contract: what the component
> promises, what it refuses, and what it must never be read as proving. Run
> counts, local timings and per-PR verification logs are not contracts - they go
> stale on the next commit - and live in the pull request and in the private
> task history instead. Current test status comes from CI.

The standalone BeamPlanner consumes compiled slot domains and retains a bounded set of partial plans. It uses the existing reference local loss and repetition penalties; weights have not been tuned. Slot traversal stays chronological so adjacency retains its established meaning.

SearchBounds adds an optimistic remaining-loss bound: each required future slot contributes its cheapest local loss plus repetitions already incurred by its candidate. Future adjacency and future repetition increments are omitted because they are nonnegative. Optional future slots contribute zero. The bound orders beam candidates; it is not an optimality certificate.

For hard daily nutrition bands, the search adds the minimum and maximum possible remaining nutrient amounts to the partial total. It rejects a state only when this interval cannot reach the target. Soft bands never prune. Horizon-average bounds are used only when every represented date has a required or locked meal. When optional-only dates can be skipped, pruning is deferred to avoid assuming a denominator inconsistent with the existing validator.

Dominance uses the per-day multiset of recipe IDs and requested servings, plus the last selected recipe. These retain nutrition, shopping demand, repetition counts and future adjacency. For equivalent states the lower accumulated loss wins; stable assignment IDs break ties. This deliberately conservative key avoids approximate quantity bucketing.

Every retained complete plan goes through independent validation. A resource limit returns candidate_rejected without a partial plan. Trace warnings include expansion counts, width pruning, nutrition pruning and dominance counts. No global infeasibility or optimality claim is made.

Required test coverage for this component: bound admissibility, preservation of valid nutrition completions, and agreement with the exhaustive objective on a toy packet. Passing these does not establish production performance on realistic packets.

**The default width of 32 and expansion cap of 10000 are development settings, not selected production parameters.** They have never been fitted against an evaluation set, and under `ADR-0020` they must not be fitted against the held-out set at all: the held-out episodes for this component have to be frozen before its parameters are chosen. Choosing them requires a developer-split parameter study plus a controlled ablation, and the resulting values belong in `OPEN_QUESTIONS.md` item 15 until that study exists.
