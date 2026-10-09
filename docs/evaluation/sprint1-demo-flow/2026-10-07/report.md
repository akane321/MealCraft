# Sprint1 workflow QA — 7 October 2026

Generated from explicitly named synthetic demo artifacts; machine-readable details and input SHA-256 values are in [report.json](report.json). This is workflow QA, not a comparative Agent evaluation, held-out score, or proof of source-data completeness.

## Result and changes

The exercised functional path completes in fixture and OpenAI modes: clean New plan → two-person peanut-allergy/no-pork S$100 dinner week → groceries → day/meal nutrition → Sunday main-only preview and confirmation → single-dish swap preview and confirmation → Chinese S$10/four-person refusal → an executable budget button and new week. Three final consecutive runs per provider cover cold/warm price-cache conditions and both desktop sizes. The unchanged response-time gate is **not passed**.

The repairs concern household wording, replayable budget suggestions, stale conversation responses/startup restore, panel space, six-nutrient day/meal access, and honest per-product price evidence. No recipe release, candidate filters, planning search policy, migrations, model timeout, ADR, dependencies or mobile support changed.

## Verification

- Backend Ruff: eight affected files passed; focused Pytest: 343 passed, zero network calls and zero protected-file reads.
- Frontend ESLint passed; Vitest: 72 passed in 12 files; typecheck exited 0 with existing Nuxt peer-module warnings; production build passed.
- Affected Playwright suites: 47 passed across the two desktop sizes (1280 × 720 and 1440 × 900), no mobile project.
- Independent arithmetic/invariant review: fixture 12 plan snapshots / 3,657 assertions, OpenAI 12 snapshots / 3,657 assertions plus 57 consistency checks; no detected arithmetic errors or unverified arithmetic items. Assertion counts are not new test-case counts.
- Three OpenAI confirmed-plan dashboard readbacks match revision 3 and the confirmed recipe IDs. Both desktop readbacks show the new Kimchi Chahan recipe and S$100.27, with no console errors. A final fixture repeat additionally waits for all displayed recipe names and the confirmed cost after every confirmation.

The original OpenAI screenshot wait covered the changed price before the async dashboard had necessarily refreshed its recipes. Later read-only checks resolved that evidence gap; they did not require another model call. The stored week is replaced after the alternative week is created, so its Change controls correctly disappear. The fixture checker was corrected to inspect the Meals tab rather than look for hidden meal rows on the Nutrition tab.

## Observed timings — not a passing speed benchmark

Seconds below are action click → HTTP response. The initial column sums the request and confirmation, excluding reading, thinking and rendering time. The initial send-to-week budget is ≤6s; the Chinese refusal reply budget is ≤6s. Even these partial measurements exceed those limits; do not claim the one-minute rehearsal passed. Fixture warm run 2 overlapped CPU tests; this further prevents treating the table as a controlled performance comparison.

| Run | Desktop | Initial request + confirm | Sunday reply | Swap reply | Chinese refusal reply |
|---|---|---:|---:|---:|---:|
| fixture-final-1-cold.json | 1280 × 720 | 8.756 | 0.12 | 0.521 | 8.086 |
| fixture-final-2-warm.json | 1440 × 900 | 9.046 | 0.189 | 0.884 | 22.657 |
| fixture-final-3-warm.json | 1280 × 720 | 6.643 | 0.107 | 0.534 | 9.651 |
| openai-final-1-cold.json | 1280 × 720 | 10.543 | 0.125 | 2.127 | 10.711 |
| openai-final-2-warm.json | 1440 × 900 | 10.915 | 0.119 | 1.462 | 12.754 |
| openai-final-3-warm.json | 1280 × 720 | 8.622 | 0.119 | 1.148 | 10.518 |

## Budget and evidence interpretation

The offered S$53 option actually confirms a 21-dish week costing S$51.99. Reducing the synthetic household to two people did not produce a cheaper verified amount in this bounded search, so the reply explains that instead of offering a misleading cheaper button. A found witness is not a proof of a globally cheapest possible week.

OpenAI swaps explicitly preview S$100.30 (+S$0.30) and confirm S$100.27 (+S$0.27) after selected-product repricing, with truthful over-budget flags and warnings. This is the existing ADR-0060 fallback, not a new policy allowing silent overspend. The arithmetic review does not independently establish the search's least-excess optimality.

Actual nutrition includes cooked entries only; Current plan excludes skipped entries and does not scale portion shares twice. Displayed nutrition is for recorded plan dishes, not all food eaten. Package arithmetic is for recorded ingredient quantities, not proof that the original recipe lists all required ingredients.

## Remaining risks and operating boundary

Known recipe omissions include filling, broth and frying oil. The owner chose to record and hand these to the data team, not modify the released data or filter candidates here. They prevent an unqualified claim that groceries and nutrition are complete for actual cooking. Price-source labels distinguish live, cached/snapshot, no-real-product sample and timeout fallbacks; an observed price timestamp is not the time of a failed check attempt.

The owner-authorized allowance was used exactly: **24/24 actual OpenAI HTTP attempts**, including embeddings and any retries. Twelve belonged to the earlier API-only repeats and twelve to the final three flows. Fixture tests and read-only UI/API checks used zero additional requests. The isolated backend is returned to fixture mode; original database volumes are unchanged. No held-out scenario data was read for debugging or tuning. Stale-response protection does not cancel already-sent requests or undo backend writes.

Local screenshots, raw synthetic responses and the guarded request ledger remain in the task's local QA directory; no credentials or private household data are copied into this public report. Do not infer current-main deployment or full acceptance from the existence of these branch results.
