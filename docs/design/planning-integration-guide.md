# Planning consumer integration

The recipe and product adapters turn existing response models into explicit
Planning inputs. Their contracts are documented in
[recipe inputs](planning-recipe-input.md) and
[product inputs](planning-product-input.md). Conversion success establishes
structural compatibility; callers still own mapping evidence, data completeness
and the meaning of user constraints.

## Build the input packet

1. Resolve canonical ingredient identities and units upstream. Retain rejected
   observations as diagnostics so a filtered product list is not mistaken for a
   complete catalog.
2. Call `recipe_input` with explicit allowed meal types and a confirmed
   `per_serving` nutrition basis. Retain its detached source, including the
   database ID and slug. Empty allergen labels do not establish reviewed safety.
3. Call `product_input` with the canonical ingredient ID and required unit.
   Retain the detached observation, mapping evidence and retrieval trace under
   the same snapshot version as the projected options.
4. Assemble `FinalPlanningProblem` with explicit slots, servings, locks,
   exclusions, nutrition bounds and versions. Check identities across the whole
   packet. Do not infer hard nutrition bounds from legacy single-value targets.
5. Supply the purchase budget as the whole-package checkout amount. The legacy
   consumed-cost budget has a different meaning and needs an explicit consumer
   decision before mapping.

The existing mixed planner accepts this packet. Follow the
[mixed-shopping contract](planning-mixed-shopping.md) for arithmetic and
independent validation. Preserve the frozen packet and search settings to replay
the result. A bounded search failure does not establish global infeasibility.

## Optional preview and repair composition

The following composition requires `app.planning.preview` and
`app.planning.mixed_repair` to be present in the checkout as well as the input
adapters. The adapters themselves do not import these modules. This section
describes their consumer boundary; it does not introduce a production route or
assume every checkout contains the combined implementation.

Call `preview_plan` with the assembled packet and explicit resource limits.
Only `validated=True` identifies a candidate that passed its independent final
check. `validation_issues=None` means that check did not run. Shopping issues
collected from rejected alternatives can coexist with a validated candidate.

For a supported product-evidence failure, `solve_mixed_with_repair` accepts an
injected snapshot provider. Each accepted response replaces the entire product
packet. The provider owns transport timeouts, coverage and freshness. Safety
conflicts and unknown recipe quantities cannot be repaired by changing prices.

After successful repair, locate the attempt matching the solution's product
snapshot version. Reconstruct the packet using that attempt's products and
version, then call the preview on that packet. Do not validate new shopping
against old prices. A degraded final attempt can contain evidence that was not
used, so consumers must not select evidence solely by its position in the list.

Keep conversion diagnostics, input versions, accepted observations, attempts,
search limits and validation results together. The preview input digest is an
input identifier, not an authorization token or a database revision.

## Consumer acceptance checks

| Consumer concern | Required check |
|---|---|
| Invalid conversion | No candidate or option is promoted to valid input; issue codes remain available. |
| Missing facts | Unknown quantities and incompatible units are not replaced with zero or guessed conversions. |
| Product refresh | The chosen result and retained evidence refer to the same accepted snapshot. |
| Search limits | Exhaustion remains visible and is not presented as proof that no solution exists. |
| Mixed shopping | Every package allocation is retained; a multi-product line is not collapsed into one product ID. |
| Replanning | Storage entries map explicitly to slots; completed and locked entries follow the agreed policy. |
| Confirmation | The backend checks permissions and the current storage revision before committing a user-approved result. |
| Relaxation | Proposals are not automatically applied; safety restrictions remain protected. |

Routing, transactions, storage migrations, real retrieval and confirmation UI
require coordinated implementation under the
[algorithm handoff](algorithm-engineering-handoff.md). Fixture verification does
not establish live-service integration or formal evaluation performance.
