# Sprint 1 demo path: response times on the real stack

Generated from the adjacent [`timing.json`](timing.json), measured on 2026-10-17 at source `a7c97b0`.

**Rule (fixture) parser only; OpenAI mode was not measured.** Times are one machine's; they are not a demo acceptance.

## Conditions

- Build: compose.yaml + compose.demo.yaml (production frontend), separate compose project, fresh database
- Machine: 13th Gen Intel Core i5-1340P, 32 GB RAM, Windows 11, Docker Desktop 29.7.2 (16 CPUs, about 15.5 GiB to Docker)
- Parser: AGENT_PARSER_PROVIDER=fixture (rule mode); OpenAI mode not measured: no OPENAI_API_KEY on this machine
- Household: demo-skeleton.md section 0: two members, one peanut allergy, no pork, S$100 a week, at most 60 minutes, dinner = main + vegetable + soup
- Method: Each request's server wait through the HTTP API the frontend calls (POST /api/agent/sessions, .../messages, .../confirm, .../replan/confirm), as the browser Network panel shows it; rendering time is not included. Cold: the first run right after `docker compose restart backend`, sent as soon as /api/health answers. Live prices: the first live run starts with an empty FairPrice cache.
- Budgets from `demo-skeleton.md` section 1 (seconds): step2_send 6, step4_reply 2, step5_reply 3, step6_reply 6

## Runs

| Run | Prices | Step 2 send → week | Plan my week | Step 4 reply | Step 4 confirm | Step 5 reply | Step 5 confirm | Step 6 reply | Week S$ | Distinct dishes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixture-cold | fixture | 5.19 | 0.19 | 0.15 | 0.16 | 0.71 | 0.15 | 7.48 | 96.49 | 16 |
| fixture-warm-1 | fixture | 4.49 | 0.15 | 0.16 | 0.12 | 0.64 | 0.14 | 8.24 | 96.49 | 16 |
| fixture-warm-2 | fixture | 4.41 | 0.15 | 0.16 | 0.15 | 0.92 | 0.14 | 7.17 | 96.49 | 16 |
| fixture-warm-3 | fixture | 4.55 | 0.16 | 0.19 | 0.15 | 0.65 | 0.14 | 7.01 | 96.49 | 16 |
| live-cold | live | 4.49 | 3.18 | 0.13 | 2.65 | 0.7 | 1.6 | 7.46 | 96.46 | 16 |
| live-warm-1 | live | 4.35 | 1.23 | 0.15 | 0.92 | 0.6 | 0.85 | 8.2 | 96.46 | 16 |
| live-warm-2 | live | 4.39 | 2.55 | 0.15 | 0.77 | 0.9 | 0.83 | 6.98 | 96.46 | 16 |
| live-warm-3 | live | 4.93 | 0.84 | 0.16 | 3.13 | 0.61 | 2.52 | 6.75 | 96.46 | 16 |

## Against the budgets

- step2_send: within the budget in every run
- step4_reply: within the budget in every run
- step5_reply: within the budget in every run
- step6_reply: over in fixture-cold, fixture-warm-1, fixture-warm-2, fixture-warm-3, live-cold, live-warm-1, live-warm-2, live-warm-3

Every run planned a full week for the household (its cost and number of distinct dishes are in the table); step 4 and step 5 each offered a preview that was confirmed.
