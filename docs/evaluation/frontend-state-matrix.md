# Frontend evaluation state matrix

This matrix defines the minimum visible states that the Frontend & Evaluation
role must preserve. Unit tests cover state derivation; Playwright covers the
critical browser path against an isolated test backend or the local stack.

| Surface | Loading | Empty / first use | Success | Recoverable error | Constraint / safety state |
|---|---|---|---|---|---|
| Home | backend status pending | no saved plan | services ready | backend unavailable | fixture/live source labelled |
| Household profile | current profile loading | editable default household | saved version and planning action | validation/API message | allergies separated from health preferences |
| Weekly plan | generating | no generated plan | 7 days + nutrition + shopping list | infeasible or API failure | warnings and budget status visible |
| Dashboard | loading plan | no plan selected | daily values and weekly trend | unknown plan / API failure | only product-generated meals counted |
| Planning assistant | restoring session | starter prompt | structured constraints + ready/planned state | parser/API failure | clarification and non-medical boundary visible |
| Replanning preview | previewing | no pending event | before/after + nutrition/grocery deltas | invalid/stale event | explicit confirm before persistence |

## Critical task flow

Create or update a household profile, generate a seven-day plan, inspect the
shopping list and dashboard, then preview a single-meal replan before deciding
whether to confirm it.

## Browser acceptance criteria

1. Each visited route shows the expected page identity and is not blank.
2. No unrelated modal or overlay blocks the task.
3. Required loading, success and error feedback is visible and readable.
4. A plan displays exactly seven meal cards and a consolidated shopping list.
5. The assistant never presents disease-specific advice as a planning output.
6. Desktop and narrow mobile layouts keep primary actions accessible.
7. No new uncaught console error is introduced by the tested flow.
