# Data release v3: quality scan

A rule-based scan of the release's recipes for patterns that point at an incomplete recipe, a wrong portion or
weight, or broken steps. No model reads the recipes: every rule is a regex or a number check in
`data-engineering/scripts/v3_quality_scan.py`, so the same release always gives the same hits.

- `report.md`: per pattern the rule, the count, the share, the split by origin, five examples with evidence; the
  union counts; the caveats. Read the caveats first.
- `hits.csv`: one row per recipe and pattern: `recipe_id,title,origin,course,pattern,evidence`, sorted by recipe_id
  then pattern, UTF-8 without BOM, evidence on one line (at most 300 characters).

## Rerun

From the repository root, standard library only (any Python 3.11 or newer):

```bash
python -X utf8 data-engineering/scripts/v3_quality_scan.py --out data-engineering/docs/v3-quality-scan-<date>
```

Reads `data/release/v3/recipes.jsonl`, `ingredients.jsonl`, `release_manifest.json`, `data/release/v2.2/recipes.jsonl`
and `data/enrichment/v3_selected_wave1.csv`. Run it again after a rebuild of the release (the 11-05 corrections, the
11-07 freeze) into a new dated folder and compare the counts. The output has no timestamps; two runs on the same
release are byte-identical.

## Pick work from the CSV

1. Filter `pattern` to one in the `core` tier of `report.md` (the high-precision list without the trivial patterns), or to
   a family: P1 to P3 completeness (water, fat, pepper, serve-with carrier, named sauce), P4 to P6 portions and
   nutrition, P7 and P8 steps.
2. Read `evidence` and open the recipe. A match is only a candidate; the trivial patterns (P1b salt, P1c pepper,
   P1d greasing fat, P4c juice or zest) and the benign water patterns (P1a2, P1f2) are not defects by themselves.
3. A recipe with several rows (filter by `recipe_id`) is hit by several patterns and usually worth looking at first.
4. `origin` is `v2.2` (carried over from the v2.2 release), `overquota`, `wave1` or `wave2`. `overquota` is found
   by the enricher name in the recipe's `enrichment.by` (`claude/akane321`, `claude/DuJiayu`), the rest by
   `v3_selected_wave1.csv`.
5. Fixes go through the reviewed corrections table (`data/enrichment/v3-corrections.csv`, `scripts/v3_corrections.py`),
   not by editing this output.

## Not included

The planning-pool gates (priced, complete, meal role) are computed by the backend; this tool does not import it, so
the report has no plannable column. `docs/planning-pool-report.json` has the pool totals.
