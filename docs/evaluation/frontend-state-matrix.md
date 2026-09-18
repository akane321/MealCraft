# Frontend evaluation state matrix

This matrix defines the minimum visible states that the Frontend & Evaluation
role must preserve. Unit tests cover state derivation; Playwright covers the
critical browser path against an isolated test backend or the local stack.

| Surface | Loading | Empty / first use | Success | Recoverable error | Constraint / safety state |
|---|---|---|---|---|---|
| Home: entry | film loading (poster shown) | starter prompts | chat opens on send | sign-in required, draft kept | none before sign-in |
| Home: conversation | assistant thinking | "who's eating, what you can spend" prompt | structured clarification, **Plan my week**, reply | request failure shown in the conversation | clarification and non-medical boundary visible |
| Home: week panel | plan loading | "shows up once planned" | 7 dinners with status, tonight, tutorial | tutorial unavailable says so | allergen note on the recipe view |
| Home: kitchen panel | plan loading | "shows up once planned" | cooked nutrition, shopping list against budget | not-priced items listed | price source labelled (FairPrice with date, saved, sample) |
| Home: nutrition details | — | no cooked dinners (actuals zero) | six nutrients, cumulative curve, daily detail | status update failure message | only cooked dinners counted as actual |
| Home: shopping sheet | — | — | printable preview, Export PDF | — | sample prices and allergen caveat printed |
| Replanning preview (in conversation) | previewing | no pending change | before/after with calorie and grocery deltas | invalid or stale change rejected | explicit confirm before persistence |
| Household profile | current profile loading | editable default household | saved version and planning action | validation/API message | allergies limited to the checked list, separated from health preferences |

## Critical task flow

Sign in, describe the week, answer any clarification, plan the week, open the
week and kitchen panels, open a recipe and the nutrition details, preview and
export the shopping list, then preview a single-dinner change in the
conversation before deciding whether to confirm it.

## Browser acceptance criteria

1. The home surface and each remaining route (`/login`, `/profile`, `/system`)
   show the expected identity and are not blank.
2. No unrelated overlay blocks the task, and an open panel never covers the
   conversation.
3. Required loading, success and error feedback is visible and readable.
4. A plan displays exactly seven dinners and a consolidated shopping list.
5. The assistant never presents disease-specific advice as a planning output.
6. The supported 1280×720 desktop viewport keeps primary actions accessible
   without horizontal task-level scrolling.
7. No new uncaught console error is introduced by the tested flow.
