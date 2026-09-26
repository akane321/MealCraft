# What the held-out runs show

Four runs exist on the same frozen 40 episodes, and every one is reported.

| Run | Files | What changed before it |
| --- | --- | --- |
| 1 | `run-1.md` | nothing: the deterministic arms, first look |
| 2 | `run-2.md` | the meal beam learned to plan against a budget |
| 3 | `run-3.md`, `live-pass-v1-1..3.md` | the live-model arms A, B and D were added |
| 4 | `latest.md`, `live-pass-v2-1..3.md` | the live arms were given the catalog's vocabulary |

Neither fix was developed here. Both were built against developer episodes written
for the purpose (`md-dev-011`..`014` for the budget, `md-dev-015`..`020` for the
vocabulary), as `ADR-0020` section 2 (as amended by `ADR-0029`) requires. But those
developer episodes were written *after* reading the held-out failures, so they
carry what the held-out set taught, and the set has now been looked at four times.
Runs 2 and 4 are checks that a fix generalises, not unseen evidence. The next
claim this protocol makes should come from a fresh set.

The live arms call `gpt-5.4-mini` with the owner's key under a token cap
(`--max-live-tokens`); every pass is roughly 280,000 tokens.

## Run 4: where the arms stand

| Arm | Who understands | Who solves | Run 4 | Live passes (run 4 + three more) |
| --- | --- | --- | ---: | --- |
| O1 | gold | meal beam | 40/40 | |
| O2 | gold | CP-SAT | 40/40 | |
| A | live model | meal beam | 38/40 | 38, 37, 38, 37 |
| B | live model | CP-SAT | 38/40 | 38, 37, 38, 37 |
| C | rule parser | meal beam | 17/40 | |
| D | live model | live model | 14/40 | 14, 18, 17, 15 |
| E | rule parser | Strong Rule-only | 17/40 | |
| F | rule parser | greedy | 21/40 | |

`O1` and `O2` are bounds, not competitors (protocol section 5).

## A and B: every failure is a misreading, and the solver never matters

`A` and `B` share one understanding call per episode and differ only in who solves.
In every pass of both prompts they fail the same episodes with the same checks,
and with the gold constraints both solvers reach 40/40. The whole gap between
them and the bounds is what the model hands the planner.

So the order guessed before any run (solver plus agent above either alone) does
not hold in the form it was written: swapping the beam for CP-SAT changes nothing
on this set. What decides the result is whether the request is turned into the
right constraints.

### What the first prompt got wrong (run 3)

With the first prompt `A` and `B` reached 31–32 of 40. Read off the nine failures:

- Constraints written in the model's own words rather than the catalog's ids:
  `cooking wine` where the catalog says `wine_cooking`, so the exclusion matched
  nothing.
- Constraints the household never stated: a dairy allergy also written as
  butter, cheese and milk; "soup may repeat" also written as "no recipe twice"; a
  `Muslim` dietary tag. Six weeks that have a plan were answered "infeasible"
  because nothing survived.
- Not asking when it should: "our usual weekly grocery budget" was planned
  around instead of asked about.

### The fix (run 4)

The prompt now lists the words a constraint may be written in (the ingredient ids
in the episode's pool, the nine checked allergens, the four dietary tags and the
household's dish roles) and states four rules: an allergy is an allergen and
nothing more; a religion or cuisine is not a dietary tag; wanting to use something
up is a request, not an exclusion; a limit pointed at without its number must be
asked about.

On the developer set (20 episodes, three passes each way): 16, 16, 16 before;
20, 20, 20 after, and 19 in a fourth pass. On the held-out set: 31–32 before,
37–38 after. Thirty-five episodes pass in all four passes and all 40 pass in at
least one.

Two failures remain in run 4:

- `md-ho-001`: a long no-pork, no-alcohol list; the model still misses some of the
  ids the gold names, so an excluded ingredient reaches the plan.
- `md-ho-023`: a feasible week answered "infeasible", from constraints tighter
  than the household stated.

They are recorded, not fixed: fixing them against these episodes would be tuning
on the held-out set.

## The live arms move between passes

`temperature=0` does not make the model repeatable. Across four passes of the
vocabulary prompt, `A` and `B` pass 35 episodes every time and 40 at least once;
`D` passes 8 every time and 25 at least once. A gap of a few episodes between live
arms is therefore not a difference. Paired statistics over the recorded runs are in
`paired.md` (`scripts/paired_multidish.py`): exact McNemar on run 4 for six comparisons
fixed in advance, and per-episode pass shares over the four live passes.

## D, the model planning by itself

`D` reached 10–15 of 40 with the first prompt and 14–18 with the vocabulary
prompt, the weakest live arm either way. It fails in every way the scorer can
name: empty required roles, dishes in the wrong course, meal time over the limit,
budget missed, allergens served, plans where it should have refused or asked. The
vocabulary helps it read the request, but nothing checks its plan before it
answers. That is the argument for the split the product uses: the model reads,
the solver plans, the validator checks.

## The rule arms fail at understanding, not at planning

`C` 17/40, `E` 17/40 and `F` 21/40 in every run. They answer with a plan where the
episode is infeasible or needs a question, because the rule parser reads none of
the budgets and none of the conflicts. That `F`, the weakest planner, scores
highest of the three is the same effect: strict success rewards a valid plan, and
`F` fabricates one for a few episodes whose constraints it never read but
happened not to break.

## Run 1 to 2: the beam did not plan against a budget

In run 1 `O1` failed 6 of 40, every one an episode with a weekly budget: the beam
scored dishes and never looked at cost, so the validator found its plans over
budget. The beam now prices a partial plan the way the validator does (whole
packages of the cheapest product per ingredient, pantry deducted), drops states
already past the budget, and keeps the cheapest candidates in reach. Held-out:
34/40 to 40/40, with no other episode regressing.

## Variety, reported beside success

Run 4: `E` 16.3 distinct recipes with no adjacent repeats, `C` 12.5, `O2` 11.9,
`O1` 9.9, and `F` 2.4 with 426 adjacent repeats. The budget fix cost the beam
variety: `O1` had 11.9 distinct recipes and 32 adjacent repeats in run 1, and 9.9
and 74 after it, because the cheapest dishes are now in reach in every slot.
Repetition is only a failure when the household asked about it (protocol section
4), so this costs no strict success, but it is a visible quality loss.

## Solve time

Run 4 medians: `F` 0.03 s, `E` 0.04 s, `O1` 0.12 s, `C` 0.15 s, `O2` 0.17 s, `A`
1.46 s, `B` 1.60 s, `D` 2.90 s. The live arms' time is the model call, charged to
both `A` and `B` even though they share it. CP-SAT's cost is real but bounded
(`O2` at 300 s proved optimality on 15 of 40); on this set it buys nothing the beam
does not already reach.
