# MVP Boundary

This document records the minimum accepted product baseline and the semantics of
the currently verified implementation. It is not the final-product scope or a
reason to stop improving a completed module. Capabilities beyond this baseline
must be prioritized by user value, evaluation benefit, implementation cost,
dependencies, and risk, then integrated with tests, documentation, and evidence.

## Core User Flow

1. The user saves a versioned household profile containing member servings and
   safety constraints plus shared budget, time, nutrition, and pantry defaults.
2. The system generates a seven-day meal plan.
3. Recipe ingredients are mapped to FairPrice products.
4. The system produces a grocery list with package quantities and prices.
5. The user marks planned dishes as consumed.
6. The dashboard displays daily nutrition and weekly trends.
7. The user may preview and confirm a minimal meal-plan adjustment; the system
   updates the affected shopping demand and keeps an event history.

## Included

- Seven-day meal planning
- Versioned household profile and profile-linked planning
- Validated 30-recipe reference catalog with normalized ingredients
- Allergen and prohibited-ingredient constraints
- Low-sodium, low-sugar, and similar general health preferences
- Optional user-provided calorie and macronutrient targets
- Budget and cooking-time constraints
- FairPrice product queries
- Known-quantity ingredient deduction
- Unknown-quantity ingredient ranking preference
- Planned-meal check-in
- Nutrition dashboard
- User-triggered replacement, cancellation, meal locking, and unavailable-item events
- Preview-before-confirmation with plan revisions and Shopping List deltas
- Repeatable scenario evaluation with CI quality gates

## Current Constraint Semantics

- Allergens, prohibited ingredients, dietary requirements, cooking-time limits,
  and user-entered numeric ceilings are hard constraints.
- Low-sodium, low-sugar, lower-calorie, nutrition-target alignment, and pantry
  usage are soft ranking preferences.
- A known pantry quantity affects coverage when its unit matches the recipe.
- An unknown pantry quantity only improves recipe ranking.
- The default low-sodium preference is deliberately flexible; only a user-entered
  sodium ceiling removes a recipe.
- Product pricing has an explicit reproducible fixture mode and a live FairPrice
  mode with cache and visible fallback.
- Budget compares the prorated value of ingredients used by the meal. Package
  checkout cost and excess quantity remain visible as separate estimates.
- Known pantry quantities are deducted from purchase demand; unknown quantities
  affect recipe ranking only and are never silently deducted.
- The current weekly baseline plans one main meal per day for seven days. It avoids
  consecutive repetition whenever at least two eligible recipes exist.
- Weekly nutrition is reported per person and contains only planned MealCraft
  recipes; unplanned food is not inferred or recorded.
- Each planned dish has one of three execution states: `planned`, `completed`,
  or `skipped`. Only `completed` dishes contribute to actual nutrition totals
  and weekly trends.
- Repeating the same status update is idempotent. A completion timestamp is
  recorded when a dish first changes to `completed` and cleared when it is
  changed back to `planned` or `skipped`.
- The weekly shopping list combines repeated ingredients before applying pantry
  deductions and product package rounding.
- Dynamic replanning never changes completed or locked meals. A preview is tied
  to the current plan revision and is rejected as stale after another confirmed
  change.
- Event-driven replanning changes one selected meal at a time. The deterministic planner chooses
  an eligible alternative; the Agent may interpret intent but does not directly
  mutate a plan.
- Member allergens, prohibited ingredients, and dietary requirements are merged
  into one shared-plan safety boundary. The current implementation does not generate a separate
  menu for each member.
- Every profile edit appends an immutable version. Profile-driven plans store the
  exact version and retain the complete effective-constraint snapshot.
- Replanning after a profile edit creates a new linked replacement week and
  reports changed constraint groups; it never rewrites the previous plan.

## Current Non-goals

These items are not part of the currently verified baseline. Except for the
non-medical safety boundary, they are not permanent product exclusions and may
enter the roadmap through an explicit design decision.

- Medical diagnosis or treatment advice
- Automatic BMR or TDEE target generation
- Recording unplanned foods
- Complete inventory management
- Food-waste prediction
- Multi-platform price comparison
- Ordering and payment
