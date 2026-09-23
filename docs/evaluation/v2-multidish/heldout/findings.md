# What the held-out runs show

Two runs exist on the same frozen 40 episodes, and both are reported here.

- Run 1 (`run-1.md`): the first run, before any fix.
- Run 2 (`latest.md`): the same set re-run after the budget fix described below.

The set was not used to develop the fix; the fix was developed against four new
developer episodes (`md-dev-011`..`014`), as `ADR-0020` section 2 (as amended by
`ADR-0029`) requires. Run 2 is therefore a second measurement of an unchanged
set, not a tuned score, but it is a second look: the set has been spent once
more and its remaining value as an unseen set is lower.

The live-model arms (A, B, D) have not run, so nothing here compares an agent
with anything.

## Run 1: the beam did not plan against a budget, and the exact solver did

`O1` (gold constraints, meal beam) failed 6 of the 40 episodes. `O2` (gold
constraints, CP-SAT) failed none. Every one of the six was an episode with a
weekly budget: `md-ho-005`, `md-ho-008`, `md-ho-019`, `md-ho-020`, `md-ho-021`
and `md-ho-022`. On each, the beam returned "no validated plan" although the
set's own proof carries a witness week within the budget.

The cause was in the search, not in the constraints: the meal beam scored dishes
and never looked at cost, so the plans it kept were the ones it liked, and the
validator then found them over budget. This was a real product weakness, because
the product path runs the same beam.

## The fix, and what run 2 measures

The beam now prices a partial plan the way the validator does — whole packages of
the cheapest product per ingredient, pantry deducted — drops states already past
a hard budget, and reserves a quarter of both the beam and each slot's meal
options for the cheapest candidates. The objective is unchanged, so `O2` still
minimises the same loss.

On the developer set this took `O1` from 10/14 to 14/14 (the four new budget
episodes). On the held-out set, run 2: `O1` 40/40, `O2` 40/40. All six budget
failures are gone and no other episode regressed.

`C`, `E` and `F` are unchanged between the runs (17, 17 and 21 of 40): none of
them reads a budget out of the request in the first place, so the planner fix
cannot help them.

## The rule arms fail mostly at understanding, not at planning

`C` (rules + beam) reaches 17/40, `E` (Strong Rule-only) 17/40 and `F` (greedy)
21/40, and their failure mechanisms are led by `status_matches_class`,
`no_fabricated_plan` and `conflict_named`: they answer with a plan where the
episode is infeasible or needs a question. The rule parser reads none of the
budgets and none of the conflicts, so every infeasible and most clarification
episodes are answered with a plan. Their planning failures (allergens,
exclusions, time, repetition requests) are a smaller share.

That `F`, the weakest planner, scores highest of the three is a symptom of the
same thing: strict success rewards a valid plan, and `F` fabricates one for a
few episodes whose constraints it never read but happened not to break.

## Variety, reported beside success

Run 2: `E` 16.3 distinct recipes with no adjacent repeats, `C` 12.5, `O2` 11.86,
`O1` 9.86, and `F` 2.37 with 426 adjacent repeats.

The budget fix cost `O1` variety: 11.93 distinct recipes and 32 adjacent repeats
in run 1, 9.86 and 74 in run 2. Reserving beam slots for the cheapest candidates
makes the same cheap dishes available in every slot, and the beam takes them.
Repetition is only a failure when the household asked about it (protocol section
4), so this costs no strict success — but it is a visible quality loss and worth
weighing before the beam becomes the product default for budget households.

## Solve time

Medians are all under a fifth of a second. In run 2 `O2`'s 95th percentile is
97.5 s, within the 300 s limit; it proved optimality on 15 of 40. The rest
returned the best plan found within the limit. `O1`'s median rose from 0.098 s
to 0.115 s: pricing partial plans is not free, but it is not near any limit.
