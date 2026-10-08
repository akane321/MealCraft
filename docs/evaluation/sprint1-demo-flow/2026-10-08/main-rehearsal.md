# Latest-main offline demonstration rehearsal

Generated on 2026-10-08 from explicitly named local rehearsal artifacts. Source: `b01bff0`. The adjacent [machine-readable report](main-rehearsal.json) preserves hashes and environment details.

**Scoped offline workflow: passed. Full demonstration acceptance: still open.**

## Environment and scope

Real local backend and PostgreSQL copy, production-built frontend matching the source tree, synthetic household only. Browser plugin not available; regular Playwright Chromium was used. Desktop sizes were 1280 × 720 and 1440 × 900. Fixture parsing and deliberately unavailable FairPrice exercise saved/sample-price fallback. Original containers, database and source checkout were preserved; no migration or worker was started.

New conversation → week confirmation → groceries → daily/meal nutrition → Sunday main-only preview/confirm → single-dish swap/confirm → Chinese low-budget refusal → execute the offered budget choice. Checks compare rendered recipe lists with saved plans, preserve untouched days, and validate portion-scaled nutrients and whole-pack purchase totals.

## Derived results

| Artifact | Desktop viewport | Workflow | Arithmetic assertions | Week-card daily counts |
| --- | --- | --- | ---: | --- |
| fixture-final-1-cold.json | 1280 × 720 | PASS | 1224 | not separately asserted |
| fixture-final-2-warm.json | 1440 × 900 | PASS | 1224 | not separately asserted |
| fixture-final-3-warm.json | 1280 × 720 | PASS | 1224 | not separately asserted |
| fixture-card-check.json | 1440 × 900 | PASS | 1224 | checked |

All recorded arithmetic errors and unverified arithmetic fields are empty. The checker also rejected deliberately corrupted portion, nutrient, package, price and budget values. No browser console errors or horizontal overflow were recorded. Guard counters and actual paid requests remained zero.

The initial screenshot captured a brief asynchronous old overview count after the cost had changed. A strengthened fourth run waited for and checked every daily count, including Sunday's single dish, and passed without changing frontend code. Its first assertion attempt treated trailing whitespace as a difference; correcting that local harness expectation and rerunning is not a product fix.

## Visual evidence

Screenshots inspected in the local task artifact folder: `fixture-final-1-cold-nutrition.png`, `fixture-final-1-cold-groceries.png`, and `fixture-card-check-sunday-confirmed.png`. Both desktop sizes show core controls; all six selected-day/meal nutrient rows are visible. Raw HTTP/browser bodies and synthetic credentials are not committed. Local artifact folder: `D:/Study/StudyFiles/NUS/DSS5105 Data Science Projects in Practice/tmp/main-rehearsal-20261008`.

## Not established by this run

- OpenAI-mode behavior and the response-time gate: no further paid calls were authorized or made.
- Real live FairPrice lookup and physical offline operation: this run used controlled provider failure.
- Recipe-source completeness: known missing fillings, frying oil and broth remain recorded for the data team. Arithmetic agreement does not resolve them.
- Independent comparative Agent capability: this is workflow QA only, with no protected held-out inputs used.

The existing full documentation checker passed, but its markdown traversal has
no explicit protected-directory exclusion and was not independently audited.
Subsequent checks are scoped to the changed documents. Runtime guard counters
cover the backend only; they do not establish zero protected reads across all
validation processes. No held-out evaluation was invoked or used for tuning.

The earlier [workflow report](../2026-10-07/report.md) remains the dated carrier of prior live-model evidence; do not reinterpret it as latest-main verification.
