# Fixed-menu snapshot refresh

`app.planning.fixed_menu_refresh.refresh_fixed_menu` reprices a complete menu
against a new frozen product snapshot. Unlike the recipe-search repair entry
points, it never searches for a different menu. All assignment IDs and roles,
user constraints and pantry facts stay unchanged.

Inputs are a `FinalPlanningProblem`, its complete assignments, a previously
feasible `MixedShoppingResult` and a new `ProductSnapshot`. The old basket is
independently validated before use. The new snapshot must have a different
nonempty version, successful retrieval status, compatible source labels, a
timezone-aware observation time and an accurate product count. Its products
replace the old packet in full; a missing old product cannot remain available
through an implicit merge.

The function runs bounded mixed-package selection for those same assignments
and independently validates the new basket. A feasible result carries the
unchanged assignments, new basket, previous and new snapshot versions and the
retrieval trace. `shopping_delta` records changed allocations, coverage, surplus
or cost per ingredient and unit. Monetary differences use integer cents.
Product identity changes appear even when checkout cost is unchanged.

If only the hard budget fails, the result is `candidate_rejected` with a
`purchase_budget` issue and a complete rejected basket for inspection. It must
not be saved as a valid plan. The function never raises the budget or silently
changes a recipe to make it fit. Missing products, unsupported quantities,
invalid prior results, degraded evidence or an unfinished solve produce no
proposed basket or monetary difference. Search limits do not mean infeasibility.

This is an offline Planning entry point, not an automatic product refresh or
provider request. The caller decides when a price observation needs refreshing
and supplies the complete snapshot. Snapshot retrieval metadata does not replace
the per-product price evidence required for product integration. Persistence,
preview confirmation, allocation display and price evidence must follow the
agreed mixed-purchase consumer contract before a product route uses the result.

`backend/tests/test_fixed_menu_refresh.py` covers price changes, hard budget
boundaries, package unavailability, complete snapshot replacement, equal-cost
product changes and malformed results. The separate
`backend/tests/test_planning_replan_invariants.py` checks the existing product
preview/confirm/reload path for a single-dish replacement, unavailable ingredient
and cancellation within composed meals. Those tests protect every unaffected,
locked and completed entry and check the reported checkout difference against
the persisted plans. They do not establish product support for automatic snapshot
refresh.
