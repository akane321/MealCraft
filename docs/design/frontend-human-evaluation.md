# Frontend and Human Evaluation Contract

## Purpose

The frontend turns system state into a desktop workflow a user can understand,
inspect and control. Its research contribution is not established by a clean
screen alone: the interface must support measurable task completion and expose
the evidence behind plan, budget and Shopping List decisions.

## Verified baseline

MealCraft currently supports a desktop web product at `1280x720` or larger with
profile, assistant, recipe, product, weekly-plan, Shopping List, check-in,
Dashboard and replanning surfaces. Existing state tests and Playwright tests are
engineering acceptance evidence. They are not, by themselves, comparative
Agent capability or human-utility evidence.

## Accepted target states

For each primary task, design and test:

- initial/loading;
- empty/no-history;
- ready/success;
- needs clarification;
- infeasible/conflicting constraints;
- partial or missing nutrition/product data;
- live/cache/fixture and stale-source state;
- tool/service error with recovery;
- pending confirmation;
- stale replanning preview;
- completed and audit/history state.

The UI should not hide unavailable facts behind a generic success state.

## Evidence the interface must expose

- active hard constraints and soft preferences;
- user-entered nutrition targets and documented tolerance;
- why a recipe was selected or rejected;
- pantry quantities deducted versus unknown pantry items used only for rank;
- product source, observation time, selected package and alternatives where
  useful;
- purchase cost, ingredient-use cost and surplus as separate concepts;
- incomplete mapping and fallback warnings;
- infeasibility and user-controlled relaxation options;
- replanning changes to meals, nutrition, Shopping List and cost;
- non-medical and plan-only Dashboard boundaries.

Explanation text must be grounded in the planner/tool trace rather than newly
generated unsupported claims.

## Human Manual Planning baseline

Use a representative subset of roughly 12-16 frozen scenarios. A participant
receives the same request, recipe packet and FairPrice product packet used by
the compared systems, together with a structured answer sheet. Record:

- time from task start to submitted plan;
- strict task success under the same deterministic validator;
- hard-constraint errors;
- Shopping List line, package and cost errors;
- number and type of manual corrections;
- unanswered ambiguities and declared infeasibility;
- perceived workload and confidence.

The purpose is not to claim that MealCraft is better than all expert dietitians.
It tests whether the product reduces routine coordination work for ordinary
planning under the frozen task definition.

## Human utility study

A practical course-scale study may recruit 6-10 participants. Each participant
reviews 8-12 randomized, blinded paired outputs, with order counterbalanced.
Collect:

- objective task-answer questions, such as identifying violated constraints or
  the correct purchase quantity;
- task-completion time and required assistance;
- pairwise preference;
- Likert ratings for usefulness, clarity, trust and personal fit;
- optional short reasons and observed confusion.

Objective correctness and subjective preference must be reported separately.
Participants should not be told which output is MealCraft until the session is
complete. A small study supports usability evidence, not population-wide
claims.

## Instrumentation contract

The frontend or study harness should preserve scenario ID, anonymized session
ID, system condition, randomized order, task start/end, clarifications, user
edits, confirmations, final result ID and error states. Do not record private
health details or API credentials.

Instrumentation should be event-based and exportable without becoming product
analytics scope. Manual timestamp sheets are acceptable for a small study if
their method is frozen in advance.

## Metrics and analysis

- task-completion rate and median time;
- strict task success after deterministic validation;
- hard-error and Shopping List error rates;
- number of clarifications and manual edits;
- pairwise win/tie/loss counts;
- median and distribution of Likert responses;
- observed recovery rate from infeasible or degraded states;
- qualitative themes linked to concrete cases.

Use paired comparisons when participants see the same scenario under multiple
conditions. Report sample size and uncertainty; do not convert a few preference
ratings into a universal product claim.

## Definition of done

1. Primary workflows expose every authoritative boundary needed for a decision.
2. Error and degraded states are usable, not only technically rendered.
3. Study tasks, order randomization, validator and analysis are frozen before
   final held-out collection.
4. Human Manual Planning uses the same evidence packet as system conditions.
5. Engineering tests and human/capability evidence are labelled separately.
