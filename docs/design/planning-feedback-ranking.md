# Offline feedback ranking

`app.planning.feedback_ranking` provides a default-off candidate ordering hook and
a chronological developer replay. It does not run in the product, record real
check-ins or train a production personalization model. The versioned feedback
format is an input contract for synthetic or explicitly supplied developer data.

## Boundary and experimental rule

The caller supplies an already filtered list of unique recipe IDs. Disabled mode
returns exactly that order. Enabled mode may only return a permutation of those
IDs. The permutation guard rejects added, missing or duplicate candidates and
falls back to the input order. The hook has no access to recipe quantities,
allergen rules, prices, nutrition or package decisions. Full-plan validation is
still required after ordering; locally eligible candidates do not guarantee a
feasible combination.

The replaceable experimental rule `experimental-cooked-share-v1` sorts by cooked
events divided by all cooked, skipped and swapped events for that recipe. It uses
exact fractions, with recipe ID as the tie-break. An unseen recipe gets zero;
when no eligible recipe has prior feedback, the baseline order is retained.
This simple rule exercises the mechanism. Skipping or swapping is not necessarily
a dislike, and the rule can favor repeatedly exposed dishes. It must not be
described as a validated preference model.

Each feedback event has a unique event ID, scope ID, recipe ID, outcome and
timezone-aware `available_at`. That time means when feedback became available,
not the meal's scheduled time. A decision uses only events from its own scope,
for its eligible recipes, strictly before its decision time. It never reads its
own outcome or another household's history. A future product adapter must derive
the scope from authenticated household identity and preserve event availability
times; these strings are not an authorization mechanism.

## Reproduce the synthetic replay

From the repository root, set `PYTHONPATH=backend` and run:

```text
python -m app.planning.feedback_ranking data/fixtures/planning-v2/feedback-ranking-developer-v1.json
```

The schema accepts `synthetic` or `developer` sources only. This label is a caller
declaration, not proof of dataset provenance. Do not rename held-out data and
pass it to this tool. Each replay decision records its eligible order and links
to one later outcome in the same scope. Reused event/decision IDs, outcomes that
predate their decisions, missing choices and cross-scope labels are rejected.

The output records the dataset version, complete input digest, policy version,
decision count, orders and actually used history IDs. It compares off and enabled
conditions by the number of recorded cooked choices ranked first. Swapped and
skipped outcomes remain visible but are excluded from that match count. There are
no inferred labels for unchosen dishes. The fixture includes a match and a miss
for each condition; it demonstrates reproducibility, not an improvement claim.

These counts measure agreement with logged choices. Without randomized exposure
or another justified design they do not measure causal benefit, ranking quality
for unseen recipes or personalized product success. Earlier outcomes can enter a
later decision's history only after they became available. No network, model API
or database is used by this replay.

## Remaining P7 integration

Product check-in export, console activation, model training and natural-language
theme translation are outside this increment. The Planning-side proposal gate is
described in [Theme Parameters](planning-theme-parameters.md). Activation must record the
ranking condition and training data, leave the default off, preserve the existing
hard-filter and final-validation boundaries, and use agreed producer/consumer
interfaces. This module alone does not complete P7 product integration.
