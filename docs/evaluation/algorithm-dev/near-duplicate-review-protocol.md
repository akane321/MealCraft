# Near-duplicate review and threshold freeze

This is the review path for product swap acceptance. It is developer evidence,
not held-out evaluation.

1. A producer prepares pairs without assigning the review verdict. The packet
   records stable recipe IDs, titles, ingredient evidence and preparation text.
2. A reviewer who is not the producer records `near`, `distinct` or `unsure`,
   their reviewer identifier, the review date and a short rationale. `unsure`
   pairs are retained but excluded from threshold fitting and accuracy counts.
3. Exploratory fitting may use only the reviewed `near` and `distinct` rows. Its
   output stays separate from product policy and cannot update runtime code.
4. A product threshold freeze names the reviewed packet digest, policy version,
   exact inclusive boundaries and unresolved rows. Runtime boundary tests must
   fail if any frozen number changes without a new policy version.

`NearDuplicateReviewBatch` in
`backend/app/planning/acceptance_evidence.py` makes reviewer independence,
source digest, unique pair IDs and unresolved freeze status executable. It does
not manufacture a reviewer or convert the supplied unattributed notes into an
independent review.

`NearDuplicateThresholdFreeze` is the formal freeze carrier. Its verifier binds
the canonical review-batch bytes to the exact runtime policy version and four
inclusive thresholds. It rejects an `unsure` row, changed review bytes or any
runtime threshold drift. A final freeze artifact must not be committed until an
identified independent reviewer supplies a freeze-ready batch; creating one
now would fabricate the missing evidence.

The current runtime freeze is `product-swap-acceptance-v1`: title overlap
`>= 0.20`, ingredient overlap `>= 0.05`, cosine `>= 0.75`, with cosine
`>= 0.64` only for pairs whose two titles independently identify the fried-rice
preparation. Exact-boundary tests live in
`backend/tests/test_peer_near_policy.py`.

The supplied review cannot yet complete step 2: reviewer identity was not
recorded and `PAIR-030` remains `unsure`. The runtime thresholds are therefore
frozen operational acceptance boundaries, not independently measured accuracy
or full-catalog acceptance evidence.
