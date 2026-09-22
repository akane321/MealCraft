# Evaluation protocol v2-multidish

Status: **draft, fixed before any system is run on it.** This protocol extends
[Comparative Evaluation v2](../design/comparative-evaluation-v2.md) to meals of
several dishes (decision ADR-0036). It fixes the comparison arms and the
solve-time metric of decision ADR-0037. Every rule below is stated before a
result exists. A later change is a new protocol version with the change
disclosed (ADR-0020 section 3), as protocol v1.1 was.

## 1. What is evaluated

A household asks, in natural language, for a week of dinners. Each dinner is
several dishes filling the roles the household's composition names: for
example a main, a vegetable, and an optional soup. The task is to understand
the request, choose one dish per role for every dinner, and buy what the plan
needs.

## 2. Episodes

An episode is a v2 held-out episode (`heldout-episode-v1`, see
`data/evaluation/heldout/v2/TEMPLATE-episode.json`) with three additions.

- **`scenario.household_profile.meal_composition`**: the household's dish roles,
  in the shape of `PlanningMealRole`: `role_id`, `courses`, `required`. It is a
  profile setting, so every arm receives it as structured context, as a profile
  holds it in the product. The natural-language request may add constraints to
  it, but never replaces it.
- **The catalog is release v2.1**, not the 30 curated recipes. Recipes are
  priced through the FairPrice v2 mapping (`data/products/fairprice-v2-snapshot.json`)
  at package grams. Only recipes whose every ingredient can be priced are
  eligible.
- **`scenario.recipe_candidate_slugs` is drawn by a script, not by the
  author.** A script samples a fixed number of eligible
  recipes for every course the composition admits, from a seed per episode. The
  pool deliberately contains dishes that break the episode's constraints, so
  that filtering is part of the task. An author who picks the pool knows the
  answer; a drawn pool does not.

The gold label is unchanged: class, hard constraints, pantry ground truth,
conflict reason. **No episode states a nutrition target.** Release recipes carry
no computed nutrition (`not_computed`), so a target could not be scored. This
is a limitation of the protocol and is reported as one.

## 3. The answer

The common output (`backend/app/evaluation/common_output.py`) gains one field.
`assignments[].role_id` names the dish role an assignment fills, and
`servings` is what that dish is cooked for. A system that omits `role_id`
fills no role, and the meal fails its composition check.

## 4. Scoring

Strict end-to-end success, as in v2 section 10: every applicable check holds,
and an indeterminate hard check is a failure. The multi-dish checks are
recomputed by the scorer's own implementation. They are not the planner's
helpers, for the reason the scorer already gives for units: a shared bug would
mark the planner's output correct. A test holds the two implementations equal
on every composition the set uses.

| Check | Rule |
| --- | --- |
| `meal_roles_filled` | Every required role of every required slot holds exactly one dish, an optional role at most one, and no assignment names an unknown role. |
| `meal_role_courses` | A dish's released `course` is one its role admits. |
| `meal_distinct_dishes` | No meal holds the same recipe twice. |
| `servings_feed_household` | Each dish is cooked for at least `household_size × share`, and the shares of a meal reach one whole meal. Shares are the ADR-0036 defaults: 1.0; 0.75 / 0.5; 0.6 / 0.4; 0.5 / 0.35. The main takes the first number and every other dish the second. |
| `cooking_time_respected` | The meal's one-cook estimate is at most the stated limit: the sum of `prep + 0.5 × cook`, plus the longest `0.5 × cook`, plus 5 minutes per extra dish, rounded up to 5. A one-dish meal is its own `prep + cook`. |
| Allergens, exclusions, diets | Checked for every dish, as in v2. |
| Shopping, pantry, budget | As in v2. Demand is each dish's ingredients scaled to its stated servings. |

These values are recorded in the set manifest, as the tolerances are.

## 5. Arms (decision ADR-0037)

| Arm | Understands the request | Solves | Role |
| --- | --- | --- | --- |
| A. MealCraft | agent (OpenAI parser) | meal beam | system under test |
| B. Agent + exact | agent (OpenAI parser) | CP-SAT | quality ceiling for the agent |
| C. Rules + beam | rule parser | meal beam | isolates the agent's contribution |
| D. Context-matched LLM-only | LLM | LLM | as v2 B2 |
| E. Strong Rule-only | rule parser | rule selector per role | as v2 B1 |
| F. Greedy | rule parser | best dish per role, every day | weak floor |
| O1. Gold + beam | gold constraints | meal beam | diagnostic |
| O2. Gold + exact | gold constraints | CP-SAT | upper bound |

- **O1 and O2 are never reported as competitors.** They split the loss into:
  - parsing loss: A against O1;
  - search loss: O1 against O2;
  - the optimality gap under the time limit: B against O2.
- **Arms A, B and D call a live model.** They run only when the owner authorises
  them with a budget cap. Each is run at least three times (v2 section 7), and
  every run is reported.

## 6. Solve time

Every arm reports wall-clock time per episode (median and 95th percentile), its
timeouts, and the machine. CP-SAT runs under the ADR-0037 section 3 limits:
- B: 30 s wall clock;
- O2: 300 s wall clock;
- both: a deterministic-time limit calibrated to those on the reference
  machine, with 8 workers in deterministic interleaved search.

Each CP-SAT result states whether optimality was proven. A timed-out episode is
scored on what the arm returned, and as a failure if it returned nothing. It is
never dropped.

## 7. Sets

- **Developer set.** Written by the implementation agent. It may be inspected
  and used to fix code and calibrate the deterministic-time limit.
- **Held-out set.** 40 episodes, the owner's choice. They are drafted by an AI
  agent from a sealed packet (the catalog facts, this protocol's episode shape
  and the authoring rules, with no code and no results), then reviewed by the
  owner and frozen before any arm runs on them. Nothing is tuned against them.

With 40 episodes, a paired difference smaller than about 20 percentage points
cannot be told from noise (v2 section 12). Results are reported per category as
counts and failure mechanisms (ADR-0028), including every category a baseline
wins.
