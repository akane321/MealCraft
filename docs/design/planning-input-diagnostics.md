# Planning input diagnostics and numeric boundaries

The Planning V2 schema accepts positive infinity in several numeric fields.
Nothing stopped such a value from reaching nutrition aggregation or cost
arithmetic, where it produces a plan that looks ordinary and is wrong. Failing
loudly at the boundary is cheaper than explaining an impossible Shopping List.

## The diagnostic

```bash
docker compose exec backend uv run --no-sync python -m app.planning.input_audit \
  data/fixtures/planning-v2/mixed-package-developer.json
```

`audit_problem` returns sorted field paths, codes, severity and descriptions. It
reports nonfinite numbers, unknown recipe quantities and units, unknown pantry
quantity, repeated product or pantry identities, blank version identifiers and
fractional-cent prices.

What it deliberately does not do:

- filter recipes, modify inputs, or certify completeness. Missing data in an
  unused candidate can coexist with a perfectly good plan;
- reinterpret an empty allergen list as missing data. The schema has no
  completeness flag that would support that distinction, and guessing here would
  be a safety claim with nothing behind it;
- treat unknown pantry quantity as an error. It is a policy notice: it may
  affect ranking, and it may never be deducted.

## Where the guard runs

`require_finite_problem` runs before search or scoring in the reference planner,
the constraint compiler and the exhaustive oracle. Beam search inherits it
through the compiler. It checks the whole frozen packet, including unused
candidates, and raises `NonfinitePlanningInput` - a `ValueError` subclass -
carrying structured issues and field paths.

The independent validator checks non-product problem numbers and submitted
shopping numbers before arithmetic. Invalid values produce `input_numeric`
checks with field paths, and both `purchase_total` and any budget check become
**indeterminate**. The numeric total stays zero as an unevaluated placeholder,
not a computed free purchase; consumers must read the check status rather than
the number. Selected-product evidence keeps its existing `product_numeric`
handling.

Invalid values are never echoed back in a report. A diagnostic that repeats the
malformed number invites a consumer to parse it.

## Overflow after valid input

Finite inputs can still overflow once aggregated. Nutrition aggregates that
become nonfinite are reported as indeterminate with no actual value and no
margin. Package cost multiplication and the running purchase total are checked
the same way and reject rather than continue.

## Budget comparison

Budgets compare at cent granularity with no tolerance in either direction, per
[`ADR-0021`]. The previous half-cent allowance agreed with this on every
cent-valued input; it differed only for sub-cent money, which is now reported as
a data problem instead of being rounded into compliance.

`ADR-0021` is recorded in the private knowledge repository, which holds accepted
decisions; this document describes the resulting behaviour.
