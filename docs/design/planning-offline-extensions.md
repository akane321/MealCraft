# Offline planning repair and relaxation

These tools replay Planning V2 packets without a database or network service.
They use the reference scoring policy and the separate
[mixed-shopping output](planning-mixed-shopping.md). Production integration
follows the [algorithm handoff](algorithm-engineering-handoff.md) and ADR-0014;
mixed allocations and budget semantics follow ADR-0021.

## Snapshot repair

`solve_with_repair` and `solve_mixed_with_repair` accept an injected
`SnapshotProvider`. A request contains canonical ingredient IDs, positive
remaining quantities and units after known pantry deduction. A response contains
a new version, a full product packet and the existing `RetrievalTrace`.

Each accepted packet replaces the preceding products. Recipes, pantry, locks,
safety constraints and budget remain unchanged. A newly selected ingredient
missing from the replacement packet remains unresolved and may require another
round. Provider coverage, transport timeouts and freshness belong to the caller.
A valid initial plan returns immediately.

Attempts retain copies of product records and retrieval evidence, including
degraded responses whose prices are not used. Provider failure, repeated
versions, missing usable demand and the explicit round limit stop the loop.
Successful evidence must identify FairPrice, include an observation timezone and
match its product count. Fixture evidence cannot claim live or cached provenance.
These checks do not establish that the underlying observation is authentic.

The mixed path derives demand before selecting packages and continues to use
mixed shopping in every round. Missing products or budget failure can trigger
retrieval; safety rejection, unknown recipe quantities and package search limits
do not trigger a request for replacement prices.

## Declared relaxation

`propose_relaxations` examines caller-supplied time or budget increases with
explicit costs. It evaluates compatible subsets in cost order and returns a
witness assignment. It never changes the original request or applies a proposal.
The original budget and proposed budgets must use whole cents; sub-cent values
are rejected without rounding.
Allergens, exclusions, diets, locks and nutrition limits are preserved.

`minimal_in_declared_options` applies only to the supplied options, frozen packet
and selected shopping policy. Missing data or an incomplete search prevents a
minimality claim. With `mixed_packages=True`, a basket already within budget
returns an empty change set. The caller must obtain the user's choice before
applying any proposal; this module does not define the team's relaxation costs.

## Command-line use

From `backend`, using the project Python environment:

```bash
python -m app.planning.workbench plan ../data/fixtures/planning-v2/final-scope-multislot.json
python -m app.planning.workbench mixed-plan ../data/fixtures/planning-v2/mixed-package-developer.json
python -m app.planning.workbench oracle problem.json --limit 10000
python -m app.planning.workbench mixed-oracle problem.json
python -m app.planning.workbench packages package-request.json
python -m app.planning.workbench relax problem.json --options permitted-changes.json --mixed-packages
python -m app.planning.workbench repair problem.json --options snapshots.json --rounds 2 --mixed-packages
```

In the backend container the committed fixtures are under `data/` rather than
`../data/`. Tests locate them through `app.core.paths.repository_root()`.

Package input contains `ingredient_id`, `required`, `unit` and `products` using
`PlanningProductOption`. Optional `--cp-sat` applies to `packages` and
`mixed-oracle` and requires the separate OR-Tools dependency.

Relaxation options are a JSON array. Each item has `change_id`, `field`
(`time_limit` or `purchase_budget`), `value`, `cost`, and `slot_id` for a time
change. Repair options are an ordered array of snapshots with `version`,
`products` and `trace`. The CLI accepts fixture provider and mode only.

Nonfinite request numbers produce `invalid_input` with field paths and exit code
2, without echoing malformed values. Schema and other invalid-argument errors
remain exceptions. Output goes to stdout; no plan is persisted.

## Integration boundary

The injected provider is an offline consumer interface. A real Retrieval adapter,
its timeout policy, production API wiring and user confirmation UI require
coordinated integration. Experimental whole-plan scoring and parameter scans are
separate work. Passing fixture tests establishes neither live retrieval success
nor held-out performance.
