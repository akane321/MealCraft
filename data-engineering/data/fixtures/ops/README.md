# Operations console fixtures

Real output of `scripts/build_release_v2.py`, produced on 2026-09-20 from **part A
only** of the enrichment packets. Every value here was computed by the real
pipeline from real enrichment results; nothing is invented.

It is a **partial build**: a recipe is released only when every one of its
ingredients has been enriched, and parts B and C were still in progress, so only
12 recipes and 29 ingredients qualified. The shapes, field names, units and
bases are final; the counts are not.

Use these files to build and test the operations console's data-quality views
before release v2 exists. When v2 is cut, point the code at
`data/release/<version>/` and these fixtures stay as test data.

- `quality_summary.json` — what `GET /api/ops/data-quality` returns
- `release_recipes.sample.jsonl` — released recipe records (12)
- `release_ingredients.sample.jsonl` — released ingredient records (29)
- `dropped.sample.jsonl` — dropped candidates with their reason
