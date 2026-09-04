# MealCraft Project Guide

## Purpose of This Guide

This guide explains what MealCraft is intended to become, how its major product
capabilities fit together, and which design principles must remain true as the
implementation evolves. It translates the initial project proposal into a
maintainable product reference.

This is a **design target**, not a statement that every capability is already
implemented. Read [Current Status](current-status.md) for verified behaviour and
[MVP Boundary](mvp-boundary.md) for the minimum accepted baseline.

## Product Positioning

MealCraft is not designed merely to answer “What should I eat today?” It creates
an actionable multi-day plan when users need to coordinate:

- planning horizon and household servings;
- allergens, prohibited ingredients, and diet types;
- budget and cooking time;
- cuisine, taste, variety, and recipe preferences;
- optional user-entered calorie and macronutrient targets;
- general preferences such as lower sodium or lower sugar;
- ingredients already available at home;
- real grocery products, package sizes, and observed prices;
- changes that occur after the original plan is created.

Traditional recipe applications usually find individual recipes. One-shot LLM
generation can understand a request but may overlook constraints, invent data,
make arithmetic mistakes, or produce a Shopping List inconsistent with the meal
plan. MealCraft therefore combines:

```text
Language understanding
+ grounded recipe and grocery information
+ deterministic planning and validation
+ a structured product interface
+ repeatable evaluation
```

## Target Users

The primary users are students and young adults who plan and cook their own
meals, have limited time or budget, prefer to plan several days in advance, or
need to account for explicit dietary restrictions and household preferences.

The product may also support small households with shared meals. The current
verified profile model produces one shared plan and applies the union of member
safety constraints. More complex per-member menus require a separate accepted
design rather than an implicit change to this meaning.

## End-to-End Product Journey

### 1. Establish household context

The user records household members, servings, allergens, prohibited ingredients,
diet requirements, budget, cooking time, optional nutrition targets, and
available ingredients. Profile changes are versioned so a plan can be traced to
the exact inputs that produced it.

### 2. Express the current planning request

The user can use a structured form or natural language. The Agent converts
explicit statements into a validated constraint object and asks a focused
question only when missing information materially affects planning.

### 3. Retrieve grounded recipe candidates

The trusted internal catalog is the reproducible core. The final design may
supplement it with external recipes, but external results must pass:

```text
Search -> Parse -> Normalize -> Validate -> Candidate Recipe Pool
```

Semantic retrieval may interpret preferences such as “light”, “home-style”, or
“quick Asian dinner”. Structured metadata must still enforce time, allergens,
diet, equipment, and other exact conditions.

### 4. Construct and validate a multi-day plan

The deterministic planner filters hard violations, scores soft preferences,
selects a varied plan, scales servings, and reports infeasibility rather than
pretending that conflicting requirements were satisfied.

### 5. Ground ingredients in real grocery products

Normalized ingredient demand is mapped to FairPrice products. Product records
include package size, observed price, source, and retrieval time. Actual package
cost is kept distinct from the prorated value of the quantity consumed.

### 6. Derive the Shopping List

The Shopping List is generated only after the plan, ingredient demand, pantry
deduction, product mapping, package calculation, and validation are complete. It
is never freely invented by the LLM.

### 7. Support cooking and plan execution

The product presents recipe attributes, ingredients, instructions, provenance,
and eventually optional cooking-tutorial support for selected meals. Tutorial
content assists execution and does not influence nutrition or planning logic.

### 8. Track MealCraft plan execution

Users mark planned dishes as planned, completed, or skipped. The Dashboard
aggregates only completed MealCraft dishes and displays coverage so its totals
cannot be mistaken for comprehensive real-world dietary intake.

### 9. Replan safely when circumstances change

Users can preview a local change before confirmation. Completed or locked meals
remain protected, the Shopping List is recomputed from the updated plan, and the
event history explains what changed. Temporary decisions must not silently
become permanent preferences.

## Product Principles

### Grounded before generated

Recipes, ingredients, nutrition values, products, packages, and prices require
traceable sources. Missing data must be exposed, not guessed into existence.

### LLM for language; programs for arithmetic and safety

The Agent may parse, clarify, orchestrate tools, and explain. Deterministic code
owns:

- cost and package calculations;
- serving and ingredient scaling;
- nutrition aggregation and deviation;
- pantry deduction;
- hard-constraint validation;
- Dashboard aggregation;
- Shopping List derivation;
- evaluation metrics.

### Hard constraints and soft preferences are different

Hard constraints include allergens, prohibited ingredients, incompatible diet
types, and explicit user-entered numeric limits. Soft signals include variety,
cuisine preference, ingredient reuse, `use_soon`, lower cost, shorter cooking
time, and broad lower-sodium or lower-sugar preferences.

The interface and validation report must make this distinction visible.

### Nutrition is non-medical and source-aware

MealCraft may calculate descriptive nutrition and evaluate targets explicitly
entered by the user. It does not diagnose disease, prescribe clinical diets,
calculate BMR/TDEE automatically, or formulate weight-loss and muscle-gain
targets on the user's behalf.

Broad preferences such as lower sodium should use a sourced, versioned policy
and controlled tolerance. A public reference is a ranking signal, not proof of a
medical outcome or official certification. When source, basis, or coverage is
missing, the system must not claim that a recipe passed the corresponding
nutrition check.

### Live product value and repeatable evaluation coexist

The user path may query current public FairPrice information. Development and
evaluation use frozen, date-stamped fixtures so website changes do not invalidate
experiments. The product must expose whether data came from live lookup, cache,
or fixture fallback.

### Replanning minimizes unnecessary disruption

A local event should change the affected meal and downstream demand where
possible. It should not rewrite unrelated completed, locked, or unaffected meals.

### Evidence is part of the product

Success is not “the menu looks plausible”. Claims require versioned inputs,
explicit metrics, comparable baselines, failure cases, reproducible commands,
and clearly stated limitations.

## Functional Model

| Capability | Final responsibility |
| --- | --- |
| Household profile | Persist household context, member safety constraints, defaults, pantry declarations, and immutable versions |
| Recipe knowledge | Maintain high-dimensional, source-aware recipe and ingredient objects suitable for retrieval, validation, calculation, and display |
| Agent | Parse explicit intent, clarify material ambiguity, maintain conversation state, call tools, and explain structured results |
| Retrieval | Combine semantic preference matching with deterministic metadata filtering and validated external supplementation where useful |
| Planner | Generate a varied multi-day plan under hard constraints and scored soft preferences |
| Validator | Recompute safety, time, serving, nutrition, grocery, and budget conditions and explain infeasibility or relaxation |
| Grocery grounding | Map normalized ingredients to purchasable FairPrice products, packages, observed prices, and timestamps |
| Shopping engine | Aggregate final demand, deduct known pantry quantities, round packages, and derive an auditable Shopping List |
| Recipe execution | Present selected recipe attributes, quantities, instructions, provenance, and optional tutorial support |
| Dashboard | Track planned/completed/skipped MealCraft dishes and calculate plan-based daily and weekly nutrition |
| Replanning | Preview, validate, confirm or discard local changes while preserving history and Shopping List consistency |
| Operations | Expose health, data quality, mapping, plan, Agent, and evaluation diagnostics needed to maintain the product |
| Evaluation | Measure extraction, clarification, validity, cost, shopping consistency, nutrition, infeasibility, robustness, and user-facing behaviour |

## Core Data Semantics

### Recipe

A recipe is a structured object rather than a dish name and free-text paragraph.
The final schema should support identity, aliases, meal context, preparation and
cooking time, servings, normalized ingredients, protein and vegetable content,
cuisine, taste, spiciness, cooking method, equipment, difficulty, diet tags,
allergens, nutrition, instructions, provenance, image, and tutorial-search data.

The exact field set may evolve, but every field used for planning or evaluation
requires a defined meaning and validation rule.

### Existing ingredient

- Known compatible quantity: deduct it from aggregated purchase demand.
- Unknown quantity: use it only as a recipe-ranking signal.
- `use_soon`: increase ranking preference without inventing expiry or waste
  predictions.

### Product observation

A product observation records retailer, product identity, package quantity and
unit, observed price, promotion when available, source, retrieval time, and
whether the value is live, cached, or frozen.

### Nutrition target

Explicit user targets have priority. Broad natural-language preferences map to
versioned, explainable soft policies. Nutrition values carry source, basis,
confidence, and missing-field state where available.

### Plan and Shopping List

The plan is the upstream decision. The Shopping List is a deterministic function
of the final plan, serving scale, existing ingredients, products, and packages:

```text
ShoppingList = f(FinalPlan, Servings, ExistingIngredients, Products, Packages)
```

### Dashboard

Only `completed` MealCraft plan entries contribute to actual totals. Planned,
skipped, and off-plan foods are excluded. Coverage must remain visible.

## Final Product Baseline

The final product should meet or exceed the ambition of the initial proposal in
the following outcomes:

1. A coherent product workspace spanning requirements, plan, recipe execution,
   groceries, Shopping List, check-in, Dashboard, and replanning.
2. Authenticated persistent user or household context with per-account data
   separation.
3. A substantially expanded, validated, high-dimensional recipe benchmark with
   traceable nutrition and provenance.
4. Trusted internal recipe retrieval plus validated external supplementation
   and semantic preference retrieval where they provide measurable value.
5. Real FairPrice product, package, observed-price, cache, and fallback handling.
6. Explainable hard constraints, elastic preferences, nutrition deviation, and
   infeasibility reporting.
7. A deterministic, package-aware Shopping List consistent with the latest plan
   and known pantry quantities.
8. Recipe execution support through structured details, provenance, and optional
   tutorial search after selection.
9. Plan-based nutrition tracking with correct completed-meal aggregation.
10. Robust local replanning and stress tests for realistic changes.
11. Multiple fair baselines, separated development/validation/held-out evidence,
    category metrics, and concrete failure analysis.
12. Reliable setup, error recovery, accessibility, testing, documentation, and
    a repeatable demonstration path.

The proposal-scale evaluation ambition is:

| Evaluation asset | Final design target |
| --- | ---: |
| Human-verified natural-language requests | 150-200 |
| Verified high-dimensional recipes | 150-250 |
| Planning scenarios with feasibility labels | 80-120 |
| Grocery snapshot | Complete mapping coverage for benchmark ingredient demand |

The final evaluation should treat engineering checks as supporting validity and
make comparative Agent capability the main research question. It should include
a weak greedy lower bound, a credible Rule-only Planner, a context-matched
LLM-only baseline, a supplementary Plain General-purpose LLM condition, Human
Manual Planning on a representative subset, and the complete MealCraft
pipeline. All controlled comparisons must use comparable requests, recipe
candidate pools, pantry states, FairPrice snapshots, planning horizons and
output schemas. Development, validation, and final held-out evidence must remain
separated. See [Comparative Evaluation v2](design/comparative-evaluation-v2.md).

The primary planned endpoint is strict end-to-end task success: every applicable
requirement for interpretation/clarification, feasibility, hard constraints,
nutrition semantics, pantry use, product packages, cost and Shopping List
consistency must pass. Average preference or diversity cannot compensate for a
hard-constraint failure.

Implementation technologies may change without reducing this ambition. Nuxt may
replace Next.js, direct PostgreSQL may replace Supabase, and different retrieval
or optimization libraries may be selected when they preserve or improve the
same responsibility and evidence.

## Scope Boundaries

The following are not primary objectives unless a later accepted decision gives
them clear value, evidence, and delivery capacity:

- mobile and tablet layouts, touch-specific interaction patterns, and
  mobile-device browser acceptance; the supported product and demonstration
  surface is desktop web at a minimum viewport of 1280×720;
- OCR, food-image recognition, and barcode scanning;
- ordering, payment, and multi-store route optimization;
- social or community functions;
- complete automatic inventory accounting;
- expiry prediction or food-waste reduction as a causal outcome;
- comprehensive off-plan dietary tracking;
- long-term health or weight-loss prediction.

Clinical nutrition advice and disease-treatment claims remain outside the
product safety boundary.

## Responsibility Domains

Contributors may work across domains, but changes should identify the capability
they affect:

- product and interaction design;
- domain data and nutrition provenance;
- Agent and requirement understanding;
- retrieval and grocery grounding;
- planning, validation, and explainability;
- backend, persistence, reliability, and operations;
- frontend implementation and accessibility;
- evaluation, testing, and reproducibility.

These are responsibility boundaries, not permanent personal branches or named
assignments. Integration occurs through reviewed contracts, fixtures, tests, and
short-lived task branches. The [module design contracts](design/README.md) make
each producer/consumer dependency and evaluation-readiness gate explicit.

## Success Definition

MealCraft succeeds when a new user can express a realistic household request,
understand any clarification, inspect why a plan is valid or relaxed, see what
must actually be purchased, follow and update the plan, and trust the origin and
limits of the displayed information. A new contributor must also be able to run,
inspect, test, and extend the system without relying on undocumented knowledge.
