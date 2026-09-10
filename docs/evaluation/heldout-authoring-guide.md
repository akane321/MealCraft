# Authoring held-out evaluation episodes

This guide is for the six contributors writing the v2 held-out set. It covers
the format, the rules a program checks for you, and the judgement calls it
cannot check.

Read `docs/design/comparative-evaluation-v2.md` sections 8 to 10 first if you
want the reasoning. This page is the working instructions.

## Why you are writing episodes for somebody else's module

The set exists to answer one question: compared with reasonable alternatives,
does MealCraft complete a real weekly planning task more reliably?

An answer is only worth reporting if the questions were written by someone who
did not know where the system is weak. If you own the planner, you know which
constraint combinations strain it. You would avoid them without meaning to, or
over-select them out of conscientiousness. Either way the number stops measuring
the system and starts measuring your expectations of it.

So: **you author episodes for categories that test modules you do not own.**
`data/evaluation/heldout/v2/set-manifest.json` maps each category to the systems
it evaluates, and `scripts/check_heldout_episodes.py` refuses an episode whose
author or reviewer owns one of them.

The same reasoning gives the set its deadline. Under
`ADR-0020` section 2 the set must be frozen **before** the components it
evaluates are tuned. This ordering cannot be repaired afterwards: once
parameters have been fitted with knowledge of these cases, no amount of later
disclosure makes the split independent again. If we miss it, the honest move is
to report that MealCraft has no independent test set, and that costs us the part
of the evaluation grade this work exists to earn.

## What one episode is

One JSON file in `data/evaluation/heldout/v2/episodes/`, named after its
`episode_id`. Generate the skeleton rather than copying by hand:

```bash
python scripts/new_episode.py --category safety_diet --author retrieval --language zh
```

That fills in the parts with no judgement in them - a free id, the meal slots, a
candidate recipe pool, and **the product ids that cover every ingredient in that
pool**. The last one matters: the packet compiler requires full product
coverage, and picking those by hand usually surfaces a gap only when
compilation fails much later. The tool also refuses outright if you are not an
eligible author for that category.

Everything that carries meaning is written as a `TODO:` placeholder, and the
checker rejects an episode that still contains one. Add `--dry-run` to preview,
`--recipes slug-a,slug-b` to choose the pool yourself, and `--seed` to make the
draw reproducible.

`data/evaluation/heldout/v2/TEMPLATE-episode.json` remains a filled-in worked
example to read when a field is unclear.

An episode has two halves.

**`scenario`** is the situation, and every system under comparison receives it
identically: the user's words, the household, the pantry, the meal slots, the
candidate recipes, and the frozen product facts. Nothing in here is an answer.

**`gold`** is how a correct response is recognised. It is deliberately *not* a
model answer. Many different weekly plans can be correct, and a set that
demands one particular week measures taste rather than capability. Gold instead
declares the class of the episode and the rules any acceptable answer must
satisfy.

## Choosing the class

Every episode is exactly one of three, and this choice matters more than any
other field.

**`feasible`** - the request is complete and a valid plan exists. Success means
a full assignment for every required slot, zero hard-constraint violations,
arithmetic that holds, and no invented recipe, product or price.

**`needs_clarification`** - something required is missing or genuinely
ambiguous. Success means asking for it before planning. List exactly which
fields must be asked about in `required_clarification_fields`. If you also know
which questions would be *unnecessary*, list them in
`forbidden_clarification_fields`: a system that interrogates the user about
things it was already told is failing differently, and we want to see that.

**`infeasible`** - no valid plan exists within the given candidates and
constraints. Success means refusing to fabricate compliance **and naming the
conflict**. A bare refusal is not a pass, so `conflict_reason` is required.

Be careful with the difference between "the bounded search did not find a plan"
and "no plan exists". Only label an episode `infeasible` when you can point at
the specific contradiction - a budget below the cheapest possible basket, an
allergen that excludes every candidate. If you are not certain, it is a
`feasible` episode with a tight constraint, and that is still a good episode.

## Rules the checker enforces

Run this from the repository root whenever you save a file. No container, no
setup:

```bash
python scripts/check_heldout_episodes.py
```

It will tell you if:

- you authored or reviewed an episode for a module you own;
- a recipe slug, product id, or ingredient name does not exist in the committed
  catalogs, which would make the packet impossible to compile;
- an `infeasible` episode has no `conflict_reason`, or a `needs_clarification`
  episode names no missing field;
- a relaxation option offers to drop one of the household's own allergens or
  excluded ingredients - safety constraints are never negotiable, and a system
  that offers to relax one has failed, not adapted;
- a pantry item with unknown quantity is marked deductible. Unknown quantity may
  raise a recipe's ranking; it may never reduce what the user has to buy;
- a replanning episode does not declare what should have stayed unchanged.

Before freezing, `--strict` additionally requires the full quota, the declared
language balance, and a reviewer on every episode.

## What the checker cannot judge

**Whether the episode is worth a slot.** Eighty episodes is not many. An episode
that only differs from another by a recipe name is wasted. Write the
`author_rationale` field first, in one sentence: what would a plausible-looking
wrong answer look like here? If you cannot answer that, the episode is not
testing anything.

**Whether the constraint combination is realistic.** These should read like
something a household would actually say, in the words they would use. Awkward
synthetic phrasings make the language understanding look worse than it is, and
that is not the capability under test.

**Whether the difficulty is honest.** Do not construct an episode you already
know MealCraft passes, and do not construct one designed to trip it. Write the
situation, then work out the gold from the constraints - not the other way
round.

## Language

The plan is 32 English, 32 Chinese, 16 mixed, declared before authoring. Spread
them across categories: `min_languages_per_category` is 2, so no category may be
single-language. If all the hard episodes were in one language, language would
silently become a difficulty proxy and the comparison would be unreadable.

Mixed means what people actually do - a Chinese sentence with an English
ingredient or brand in it - not a translation exercise.

## Review

Each episode needs one reviewer who is neither its author nor an owner of a
system under test. The reviewer checks that the class is right, the conflict or
missing field is real, and the gold does not encode one arbitrary correct plan.
Record disagreements in `review_notes` and resolve them before the freeze.

## A known limitation, stated up front

The committed catalog holds 30 recipes and 34 ingredients, with six allergens
(dairy, egg, fish, gluten, sesame, soy) and six dietary tags. That bounds what
these episodes can express: there is no way to write a peanut allergy or a
no-pork household today.

This is a real constraint on the set, not a reason to delay it. Each episode
freezes its own candidate pool, so the set stays valid when the catalog grows
under `ADR-0012`. But the evaluation report must say plainly that safety
coverage spans six allergens rather than a realistic range, and that will read
better than letting a reader assume otherwise.

## After the set is frozen

Do not edit an episode. A corrected label creates a new set version with a new
digest, so that anything already reported stays interpretable. Silent edits to a
frozen set destroy the only property that makes it worth having.
