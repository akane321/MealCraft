# Mixed purchase handoff proposal

This is a Planning-side prototype for contract review under ADR-0021 section 3.
It is not an accepted replacement for `PlanningShoppingSelection` or
`GroceryLineEstimate`, and no product route calls it. The existing single-product
API and storage remain unchanged.

`prepare_mixed_purchase` in `app.planning.mixed_purchase_handoff` takes a frozen
planning problem, complete assignments, a mixed shopping result, and observations
and `PriceEvidence` keyed by planner product ID. The producer supplies observations
already normalized to the packet's units, using the existing product input rules.
The function performs no retrieval or unit inference.

Before returning a payload it independently recomputes the basket, including
demand, pantry, package coverage, prices and hard budget. It then checks each
used observation against the solved product option and checks the evidence fact
ID, time and source/mode. Conflicting observations for the same fact fail. These
checks establish consistency with the supplied frozen records; they do not
authenticate the external source or certify ingredient mapping.

## Proposed structure

- One item per ingredient and unit carries total demand, pantry deduction,
  remaining demand, supplied quantity, surplus and checkout cost.
- Each item contains `allocations`, one per selected package product. Every
  allocation carries its integer count, whole-cent cost, complete observed
  product and original price evidence.
- `planning_product_id` stays separate from the provider's `external_id`. The
  existing `external_id@ingredient` alias represents separate purchases for two
  ingredients; it does not share a purchased package between them.
- A fully pantry-covered item has no allocations, zero checkout cost and no
  invented product or price evidence.
- Catalog, product snapshot and policy versions, a planning-input digest and a
  content digest bind the result to its inputs. The payload excludes raw
  household constraints and detaches observations from mutable input objects.

Success is called `ready_for_contract_review`. Missing evidence, mismatched
observations, invalid arithmetic, a sub-cent budget or an unsuccessful basket
returns `not_ready` with issue codes and no partial items. Readiness here does not
mean the database or UI can consume the payload.

## Work needed before enabling this in the product

The backend owner needs to agree an additive versioned allocation representation
and persistence design. `MealPlanGroceryItem` has a unique `(plan_id,
ingredient_name)` key and one set of product columns; multiple old-style rows for
one ingredient violate that key and duplicate pantry/demand. A parent item with
allocation children is one possible design, subject to owner review and migration.

Quantity precision also needs agreement. Existing database quantities use three
decimal places; the mixed arithmetic contract refuses lossy conversion. A value
that is exact in the prototype must not be rounded silently on save and reload.
The meaning of consumed cost across mixed allocations must be agreed before
populating that existing field. This prototype reports checkout cost only.

The frontend owner needs to render the ingredient once and show each purchased
package beneath it. Replanning and grounding consumers need to recompute totals
over allocations and preserve each allocation's evidence. Existing plans require
a defined compatibility path.

After those contracts are agreed, Planning can connect the solver to the product
path and test request, save, reload and replan end to end. Required cases include
a mixed basket that fits a hard budget while either single size fails, one cent
over budget, known and unknown pantry, mixed provenance modes, quantity precision,
and a product snapshot changed during replanning.

The local prototype tests are in `backend/tests/test_mixed_purchase_handoff.py`.
The fixed-menu and solver-scale experiments are documented in
[Purchasing Comparison](planning-purchasing-comparison.md).
