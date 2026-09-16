# Normalized Planning preview

`app.planning.preview.preview_plan` accepts a `FinalPlanningProblem` and explicit
search limits. It uses the mixed Beam Search and reference scoring policy,
without database access, network calls or writes. The result is an offline
integration boundary, not a new public HTTP contract.

```python
from app.planning.preview import preview_plan

preview = preview_plan(problem)
if preview.validated:
    # Present the independently checked mixed-shopping candidate.
    print(preview.to_json())
```

The input is validated into a detached packet. Versions must be nonempty,
numbers finite, and budgets and product prices expressed in whole cents.
Unknown pantry quantity remains a diagnostic and is never deducted. Missing
facts on unused candidates are not automatically treated as a failed plan.

The result records the normalized input SHA-256, preview version, Beam limits,
package enumeration limit, input diagnostics and the mixed-planning result.
The digest includes list order and identifies input only; limits are separate.
Callers must retain the original packet to replay it. The digest is neither a
permission token nor a database revision or proof of source authenticity.

Each feasible candidate is checked again by `validate_mixed_shopping`. A failed
check changes its status to `candidate_rejected` and leaves `validated` false.
`validation_issues=None` means no feasible candidate was available for this final
check. An empty tuple means the final check ran and passed. Consumers must use
`validated` before presenting the candidate as independently checked.

`candidate_issues` contains sorted, deduplicated shopping issues encountered in
retained completions. These may describe rejected alternatives even when a valid
candidate exists; they are not violations of the selected plan. They do not
include every compiler rejection or describe candidates pruned before completion.
Package-limit issues and the separate expansion-limit flag preserve resource
exhaustion evidence. No preview outcome establishes global infeasibility.

The preview uses the separate mixed allocation output under ADR-0021. It does
not convert legacy consumed-cost budgets, invent nutrition target scopes or
write mixed packages into the single-product V2 Shopping shape. Production
mapping, persistence, confirmation and versioned API adoption require the
coordination described in the [algorithm handoff](algorithm-engineering-handoff.md).
