# Input diagnostics and quantity precision proposal

## Implemented diagnostic

Run from `backend`:

```text
python -m app.planning.input_audit ../data/fixtures/planning-v2/mixed-package-developer.json
```

`audit_problem` returns sorted field paths, codes, severity and descriptions.
It reports nonfinite numbers, unknown recipe quantities/units, unknown pantry
quantity, repeated product/pantry identities, blank version identifiers and
fractional-cent prices. The current V2 schema accepts positive infinity in some
numeric fields; the regression test demonstrates this before checking the audit.

The diagnostic does not filter recipes, modify inputs or certify completeness.
Missing data in an unused candidate may coexist with another feasible plan.
Unknown pantry quantity is a policy notice because it can affect preference but
cannot be deducted. Empty allergen lists are not reinterpreted as missing data;
the current schema has no completeness flag that would support that distinction.
Source-level nutrition/allergen provenance also cannot be verified from these
fields. These checks are not wired into production request validation yet.

The offline workbench rejects nonfinite numbers in request JSON and options
before calculation, and checks normalized problem/product records again after
schema coercion. It emits strict JSON with `status: invalid_input`, field paths
and diagnostic codes, then exits with code 2. Invalid numeric values are not
echoed in the response. Known missing quantities represented by null remain
subject to existing missing-data policies. The seven workbench operations are
covered by tests for positive infinity, negative infinity and NaN, with additional
checks for coerced infinity, options and unknown pantry quantity.

The workbench JSON response and exit code are specific to that CLI. Direct
BeamPlanner candidate search/solve, exhaustive_assignments, exhaustive_mixed_plan
and score_plan now call require_finite_problem. Mixed beam and both repair paths
inherit the check through candidate search. A malformed numeric packet raises
NonfinitePlanningInput (a ValueError subclass) with structured issues and paths,
before search or scoring. This checks the entire frozen packet, including unused
candidates. It does not reinterpret null quantities or blank allergen lists.

The reference planner's solve method and compile_constraints now enforce the
same check; compile_search_domains and Beam candidate search inherit it through
the compiler. Beam does not repeat the same input scan before compilation.

Direct V2 validator calls now check non-product problem numbers and submitted
shopping numbers before arithmetic. Invalid values produce input_numeric failure
checks with field paths; purchase_total and any budget check are indeterminate.
The required numeric total field remains zero as an unevaluated placeholder,
not a computed free purchase. Consumers must inspect report/check status.
Selected product evidence retains the existing product_numeric handling.

Mixed assignment checks also reject nonfinite non-product input with
input_numeric:<field-path>. Both mixed shopping construction and independent
mixed validation use this check, including when no nutrition target is present.
Product and submitted purchase arithmetic retain their dedicated checks.

Finite input values can still overflow after aggregation. The V2 validator marks
nonfinite nutrition aggregates indeterminate, without emitting an actual value or
margin. Overflow in package price multiplication or the running purchase total
produces purchase_numeric failure and leaves budget evaluation indeterminate.
The retained total is only a computed partial amount in this case; it is not a
complete checkout estimate. These paths have strict JSON serialization tests.

This is not universal schema enforcement: private helper calls retain their
existing handling. Existing
package functions retain their own input handling. Production request validation
and a consistent error adapter remain separate integration work.

## Quantity precision decision to review

Status: proposal, not an accepted contract or implemented rounding change.

Current mixed shopping computes with rational values, but its output fields are
floats. A demand such as 100g divided among three recipe servings cannot round-trip
through a decimal float exactly and currently returns `quantity_not_representable`.
Silently rounding this demand down could permit too little package coverage.

The preferred proposal is to preserve exact rational quantities inside planning
and independent validation, then round only display text. A versioned output can
carry numerator/denominator or exact decimal strings where applicable, together
with a separate display value. Source serving units and conversion provenance
must be retained. This needs agreement with API, persistence and UI consumers.

An alternative is an explicit per-unit integer scale with conservative upward
rounding for purchase demand. That is easier to serialize but changes the physical
quantity represented and can require an additional package at a boundary. Its
rounding error and display semantics must be defined and evaluated before use.
No default scale or rounding rule is introduced here.

Budget handling also needs alignment: mixed shopping compares exact decimal
amounts, while the original V2 validator applies a rounding allowance. The proposed
direction is whole-cent product prices and deterministic cent arithmetic, with
an explicit policy for user budgets containing fractional cents. The adapter must
reject or clarify unsupported precision rather than changing a user's limit.

## Acceptance checks before adopting a shared contract

- One-third serving calculations remain traceable through serialization.
- Package coverage uses the calculation quantity, not rounded display text.
- Pantry is deducted once in a compatible unit; unknown stock stays unknown.
- Prices and budgets have explicit accepted precision and finite values.
- Old V2 consumers remain compatible until the versioned migration is complete.
- Candidate-level missing data is not treated as proof that every plan is invalid.

The diagnostic and this proposal do not complete the schema-hardening work package.
Shared completeness/provenance fields and runtime rejection rules remain open.
