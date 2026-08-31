# MVP Boundary

## Core User Flow

1. The user enters household size, budget, cooking-time limit, allergens,
   health preferences, optional nutrition targets, and available ingredients.
2. The system generates a seven-day meal plan.
3. Recipe ingredients are mapped to FairPrice products.
4. The system produces a grocery list with package quantities and prices.
5. The user marks planned dishes as consumed.
6. The dashboard displays daily nutrition and weekly trends.

## Included

- Seven-day meal planning
- Allergen and prohibited-ingredient constraints
- Low-sodium, low-sugar, and similar general health preferences
- Optional user-provided calorie and macronutrient targets
- Budget and cooking-time constraints
- FairPrice product queries
- Known-quantity ingredient deduction
- Unknown-quantity ingredient ranking preference
- Planned-meal check-in
- Nutrition dashboard

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

## Excluded

- Medical diagnosis or treatment advice
- Automatic BMR or TDEE target generation
- Recording unplanned foods
- Complete inventory management
- Food-waste prediction
- Multi-platform price comparison
- Ordering and payment
