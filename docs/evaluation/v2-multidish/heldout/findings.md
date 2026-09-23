# What the held-out runs show

Three runs exist on the same frozen 40 episodes, and all three are reported.

- Run 1 (`run-1.md`): the deterministic arms, before any fix.
- Run 2 (`run-2.md`): the same arms after the budget fix below.
- Run 3 (`latest.md`): every arm, including the live-model arms A, B and D
  (`gpt-5.4-mini`, 80 calls, 280,201 tokens, the owner's key and token cap).
- Three further passes of the live arms alone (`live-pass-1.md`..`live-pass-3.md`),
  because the protocol asks for at least three runs of any arm that calls a model.

Nothing here was used to develop anything: the budget fix was built against four
new developer episodes (`md-dev-011`..`014`), as `ADR-0020` section 2 (as amended
by `ADR-0029`) requires. But the set has now been looked at three times, and its
remaining value as an unseen set is lower for it.

## Run 3: the bounds, the agent arms, the rule arms

| Arm | Who understands | Who solves | Strict success |
| --- | --- | --- | ---: |
| O1 | gold | meal beam | 40/40 |
| O2 | gold | CP-SAT | 40/40 |
| A | live model | meal beam | 31/40 |
| B | live model | CP-SAT | 31/40 |
| C | rule parser | meal beam | 17/40 |
| D | live model | live model | 10/40 |
| E | rule parser | Strong Rule-only | 17/40 |
| F | rule parser | greedy | 21/40 |

`O1` and `O2` are bounds, not competitors (protocol section 5).

## A and B fail on the same nine episodes, and the solver is never the reason

`A` and `B` share one understanding call per episode and differ only in who
solves. They fail the same nine episodes with the same checks. Every failure is
in the reading of the request, and the gap to the bounds (40/40 with the same
solvers) is entirely the constraints they hand the planner.

What the model gets wrong, read off the nine:

- It writes constraints in its own words instead of the catalog's ids: for the
  no-alcohol household it excludes `cooking wine` where the catalog says
  `wine_cooking`, so the exclusion silently does nothing while a different one
  bites.
- It over-constrains. Told of a dairy allergy it also excludes butter, cheese and
  milk by name; told "soup may repeat" it also sets "no recipe twice"; told the
  household is Muslim it invents a `Muslim` dietary tag. Six episodes that have a
  plan were answered "infeasible" because nothing survived the constraints it
  added.
- It does not ask when it should: `md-ho-038` says "our usual weekly grocery
  budget" and the gold requires asking which budget; the model planned anyway.
- On `md-ho-028` it planned where the gold is a conflict.

The comparison ADR-0037 asked for therefore lands the other way round from the
guess written before the runs: swapping the beam for CP-SAT (A → B) changes
nothing at all, while who reads the request decides everything. The solver only
becomes visible at the bound, where the constraints are correct by construction.

**No fix is made here.** A prompt or a vocabulary change is a parameter change and
may be developed only against the developer set.

## The live arms move between passes, so a few episodes are not a difference

Same prompts, same key, `temperature=0`, three passes:

| Arm | Pass 1 | Pass 2 | Pass 3 | Passed in all three | Passed in at least one |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 32/40 | 31/40 | 31/40 | 29 | 34 |
| B | 32/40 | 31/40 | 31/40 | 29 | 34 |
| D | 14/40 | 12/40 | 13/40 | 9 | 19 |

`A` and `B` are identical in every pass, episode by episode. `D` swings by two
episodes in the totals and by ten between "always" and "ever": half of what `D`
gets right, it gets right only sometimes.

An earlier pass, before the timing fix, gave `A` 31/40, `B` 31/40 and `D` 15/40;
its report was overwritten and is not kept, but the number belongs on the record.

So a gap of a few episodes between live arms is not evidence of anything here.
Paired statistics over repeated runs remain open work (`ADR-0028`).

## D, the model planning by itself, is the weakest arm

`D` reaches 10/40 and fails in every way the scorer can name: it leaves required
roles empty, puts a dish in the wrong course, breaks the per-meal time limit,
misses the budget, serves an allergen, and plans where it should have refused or
asked. It is not a weak planner so much as an unconstrained one; nothing checks
it before it answers.

## The rule arms fail mostly at understanding, not at planning

`C` 17/40, `E` 17/40 and `F` 21/40, led by `status_matches_class`,
`no_fabricated_plan` and `conflict_named`: they answer with a plan where the
episode is infeasible or needs a question. The rule parser reads none of the
budgets and none of the conflicts. That `F`, the weakest planner, scores highest
of the three is the same effect: strict success rewards a valid plan, and `F`
fabricates one for a few episodes whose constraints it never read but happened
not to break.

## Run 1 → 2: the beam did not plan against a budget, and the exact solver did

In run 1 `O1` failed 6 of 40, every one an episode with a weekly budget
(`md-ho-005`, `008`, `019`, `020`, `021`, `022`): the beam scored dishes and never
looked at cost, so the validator found its plans over budget. The beam now prices
a partial plan the way the validator does — whole packages of the cheapest product
per ingredient, pantry deducted — drops states already past the budget, and keeps
the cheapest candidates in reach. Developer set: `O1` 10/14 → 14/14. Held-out:
34/40 → 40/40, with no other episode regressing. `C`, `E` and `F` did not move,
because none of them reads a budget from the request at all.

## Variety, reported beside success

Run 3: `E` 16.3 distinct recipes with no adjacent repeats, `D` 13.37, `C` 12.5,
`O2` 11.86, `B` 10.41, `O1` 9.86, `A` 9.06, and `F` 2.37 with 426 adjacent
repeats.

The budget fix cost the beam variety: `O1` had 11.93 distinct recipes and 32
adjacent repeats in run 1, and 9.86 and 74 in run 3. Reserving beam slots for the
cheapest candidates makes the same cheap dishes available in every slot. Repetition
is only a failure when the household asked about it (protocol section 4), so this
costs no strict success, but it is a visible quality loss.

## Solve time

Medians: `F` 0.02 s, `E` 0.04 s, `O1` 0.09 s, `C` 0.13 s, `O2` 0.16 s, `A` 1.41 s,
`B` 1.53 s, `D` 2.75 s. The live arms' time is dominated by the model call, which
is counted for both A and B even though they share it. `B`'s 95th percentile is
12.7 s (CP-SAT at 30 s) and `O2`'s is 88.7 s (CP-SAT at 300 s, optimality proved
on 15 of 40). The cost of the exact solver is real but bounded; on this set it
buys nothing that the beam does not already reach.
