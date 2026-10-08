# Frontend evaluation state matrix

This matrix defines the minimum visible states that the Frontend & Evaluation
role must preserve. Unit tests cover state derivation; Playwright covers the
critical browser path against an isolated test backend or the local stack.

| Surface | Loading | Empty / first use | Success | Recoverable error | Constraint / safety state |
|---|---|---|---|---|---|
| Home: entry | film loading (poster shown) | starter prompts | chat opens on send | sign-in required, draft kept (a dish's words with the week they change, until another week is shown or opening; sent from here they reopen its conversation first, and nothing sends until it is back) | none before sign-in |
| Home: conversation | assistant thinking | "who's eating, what you can spend" prompt; on reopening, the conversation that planned the current week, else one ready to plan, else a fresh one (never another conversation's week card) | structured clarification, **Plan my week**, reply | request failure shown in the conversation | clarification and non-medical boundary visible; proven limits carry their number and backed choices; a bounded-search miss is explained without claiming global infeasibility |
| Home: week panel | plan loading | "shows up once planned"; a conversation that planned nothing (new, off topic) shows the current week, and its dish actions change that week in the conversation holding it (reopened), else here (one ready to plan or still asking about a new week asks first, with the question scrolled into view; it goes once it plans one or the composer says something else; the dish's words go once another week is shown, as after **Plan my week**); switching conversations always reloads the panel | configured breakfast, lunch and dinner dishes with status, tonight, tutorial | tutorial unavailable says so | allergen note on the recipe view |
| Home: kitchen panel | plan loading | "shows up once planned" | chosen day/meal's six nutrients, actual versus current plan; shopping list against budget | skipped dishes excluded; not-priced items listed | each item's live, saved or sample source; missing product ID distinguished from timeout; observation/check times available |
| Home: nutrition details | — | no cooked dishes (actuals zero) | six nutrients, cumulative curve, daily detail | status update failure message | only cooked dishes counted as actual, across the selected meals |
| Home: shopping sheet | — | — | printable preview, Export PDF | — | sample prices and allergen caveat printed |
| Replanning preview (in conversation) | previewing | no pending change | before/after with calorie and grocery deltas | invalid or stale change rejected | explicit confirm before persistence |
| Household profile | current profile loading | editable new household with no limit, budget, target or health preference filled in | saved version and planning action | validation/API message | allergies limited to the checked list, separated from health preferences |
| Operations experiments | evaluations, history or evidence drawer loading | no recorded run / no failed case | confirmed job moves queued → running → completed; evidence opens; comparable A/B runs expose parameters, metrics and failure mechanisms | queue, refresh or detail error remains actionable; incompatible runs explain why their delta is not interpreted | fixed developer registry only; held-out and paid providers unavailable; legacy inline entries labelled; developer diagnostics never presented as final claims |
| Operations: catalog jobs | queue refreshing | no recorded catalog jobs | named source queued, live status and attempt count | last recorded state retained with retry | administrators confirm writes; legacy roles cannot enter; only queued/running jobs can be cancelled |
| Operations: data quality | report loading | release evidence unavailable | release coverage, manifest and dropped-candidate evidence | missing or invalid artifact shown as degraded | separate released, imported and planner-eligible counts; field completeness is not independent truth verification |

## Critical task flow

Sign in, describe the week, answer any clarification, plan the week, open the
week and kitchen panels, open a recipe and the nutrition details, preview and
export the shopping list, then preview a dish or affected-meal change in the
conversation before deciding whether to confirm it.

## Browser acceptance criteria

1. The home surface and each remaining route (`/login`, `/profile`, `/system`)
   show the expected identity and are not blank.
2. No unrelated overlay blocks the task, and an open panel never covers the
   conversation.
3. Required loading, success and error feedback is visible and readable.
4. A plan displays the configured week's days, meals and dish roles, with a
   consolidated shopping list; the legacy one-dish condition displays seven dinners.
5. The assistant never presents disease-specific advice as a planning output.
6. The supported 1280×720 desktop viewport keeps primary actions accessible
   without horizontal task-level scrolling.
7. No new uncaught console error is introduced by the tested flow.
