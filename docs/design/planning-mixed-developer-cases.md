# Mixed planning developer cases

`app.planning.mixed_developer_comparison` adds eight synthetic scenarios to the
mixed-shopping developer fixture: two dates, varying household servings, an
optional slot, locked slots, hard daily protein limits, an impossible purchase
budget, missing products and unknown pantry quantity. Every scenario contains
four slots and three recipes; the optional scenario permits an empty slot.
Two normalized ingredients each have two available package sizes.

Run from `backend`:

```text
python -m app.planning.mixed_developer_comparison ../data/fixtures/planning-v2/mixed-package-developer.json
python -m app.planning.mixed_developer_comparison ../data/fixtures/planning-v2/mixed-package-developer.json --cp-sat
```

The dataset ID is `synthetic-mixed-developer-v2`. Output includes each complete
input packet's SHA-256, scoring policy, package solver, recipe-combination count,
search width, status, independent validation issues, loss, certified oracle gap,
repeat consistency and median elapsed milliseconds. The runner compares widths
1, 4 and 16, with two repeats. All methods use the same frozen packet and mixed
shopping policy. The oracle enumerates raw recipe assignments and uses either
package enumeration or CP-SAT for each ingredient. This is an offline developer
diagnostic, separate from the project's formal evaluation dataset and metrics.

The local run on 2026-09-09 produced 24 rows. All six feasible scenarios passed
independent shopping validation at each width. The impossible-budget scenario
was rejected, and missing products remained `needs_data` with incomplete oracle
evidence. All decision outputs repeated identically. The width-16 runs matched
the exhaustive score on the six feasible scenarios. Widths 1 and 4 had positive
gaps in five scenarios; the locked scenario matched at all widths. CP-SAT and
package enumeration agreed on oracle status and loss for all eight scenarios.

No preference gap is reported when the output is invalid, missing data or lacks
a certified oracle optimum. Input-order regression tests reverse slots, recipes
and products. The generator preserves its source fixture.

These small scenarios share a synthetic recipe template and do not cover the
distribution of real household requests. They do not justify selecting width 16
as a default, freezing scoring weights or claiming held-out or production quality.
Repair/provider failure cases remain covered by the separate repair tests.
