# Planning extensions and integration boundary

These additions are offline, planner-owned components. They do not change `/api/plans`, persistence, Agent tools, Retrieval providers or frontend behavior.

## Mixed packages

`optimize_packages` enumerates combinations of available products with matching canonical ingredient and unit. It minimizes decimal checkout cost, then surplus and stable IDs. Each product count is bounded by the packages needed to cover demand by itself; exceeding this count cannot improve nonnegative cost or surplus. Oversized searches return `limit_exceeded` before enumeration. Prices must be finite, nonnegative and expressed to cents. No substitution, conversion or stock quantity is invented.

`validate_packages` independently checks identity, integer package counts, coverage, cost and surplus. It validates arithmetic, not the optimizer's claim of minimality. Example: demand 1000g; 600g costs SGD4, 400g costs SGD3. One of each costs SGD7, below repeated single-product purchases.

The V2 ShoppingSelection has one selected_product_id per ingredient. Mixed results use PackageResult.allocations. They now run through a separate offline beam and exhaustive planning path, documented in [Mixed shopping](planning-mixed-shopping.md). A versioned producer/consumer agreement is required to adopt allocations in V2 without breaking existing consumers.

## Bounded snapshot repair

`solve_with_repair` accepts a SnapshotProvider supplied by the Retrieval integration layer. It sends positive normalized remaining demand, accepts a new full product snapshot and reruns planning without changing user constraints. The snapshot is a complete replacement packet, not a patch. The caller must ensure provider coverage for the planned candidate scope; newly selected ingredients absent from that packet remain needs_data and can trigger another bounded round.

Attempts retain snapshot versions, product records, requests and retrieval traces. Known provider failure, degraded evidence, repeated versions, missing normalized demand and resource exhaustion stop explicitly. Fixture evidence cannot claim live provenance. A successful initial frozen plan returns immediately; live freshness refresh is a separate caller responsibility. This module does not implement HTTP retries, timeouts or scraping.

For mixed shopping, `solve_mixed_with_repair` and the CLI `repair --mixed-packages`
retain the mixed-package policy on every round. Demand is derived before product
selection, so missing products can still produce a complete normalized request.
The default V2 path is preserved. See [Mixed shopping](planning-mixed-shopping.md)
for failure routing and examples.

## Explicit relaxation options

`propose_relaxations` accepts declared time or purchase-budget increases and their costs. It tests compatible subsets in cost order using the small assignment oracle, returning a witness without modifying the original problem. The optional `mixed_packages=True` uses the mixed-shopping oracle; the default retains the reference single-product policy. No allergies, ingredient exclusions, diets, locks or nutrition limits are changed. Minimality only applies to the supplied option set, selected shopping policy and fully evaluated candidates. Incomplete evidence prevents a minimality claim. The caller must present proposals and obtain the user's choice before applying anything.

## Offline commands

Run from backend with the project environment:

```text
python -m app.planning.workbench plan ../data/fixtures/planning-v2/final-scope-multislot.json --width 32
python -m app.planning.workbench oracle ../data/fixtures/planning-v2/final-scope-multislot.json --limit 10000
python -m app.planning.workbench packages package-request.json
python -m app.planning.workbench relax problem.json --options permitted-changes.json
python -m app.planning.workbench repair problem.json --options ordered-fixture-snapshots.json --rounds 2
```

Package input contains ingredient_id, required, unit and products using PlanningProductOption. Relaxation options contain change_id, field (time_limit or purchase_budget), value, cost and optional slot_id. Repair snapshots contain version, products and the existing RetrievalTrace; workbench accepts fixture mode/provider only. Output goes to stdout; no database or remote write occurs.

## Pending team decisions and integration

- Planning: proposed whole-plan nutrition/soft preference policies, development validation and rule freezing. Existing reference scores remain active.
- Planning plus schema consumers: agree a versioned mixed-allocation field and missing/provenance semantics before replacing V2 shopping output.
- Retrieval owner: implement the provider adapter, observation completeness, network timeouts and actual FairPrice calls; Planning consumes its typed snapshots.
- Backend/Agent/frontend owners: wire versioned runtime endpoints, ownership/persistence, explicit relaxation confirmation and output rendering. No files in those modules were changed here.
- Evaluation: broader paired developer datasets and held-out experiments remain pending. A hybrid raw-assignment enumeration plus CP-SAT package oracle now supplements the original fixed-policy oracle; see the mixed shopping document for its limits.

Verification covers arithmetic mutations, missing evidence, snapshot source labels, repair failure and limits, declared relaxation search and CLI behavior. Test counts are recorded with each local verification run. No production integration or live-service success is claimed.
