# Acceptance sample for the v3 model-tag batch (`recipe-tags-v1/llm-v3-20261103`)

Plain summary. Data release v3 added recipes that v2.2 does not have. The tag rules decided most of their tags.
Where the rules left `meal_role` open, a model decided it. Those values form their own batch. They are model
estimates, not human labels. This sample covers only the 100 recipes in that batch; it does not estimate accuracy
for all v3 tags. The planner does not read them until the owner accepts the batch (ADR-0094's route, ADR-0111).

## The batch (re-asked 2026-11-06, issue #426 E)

The first batch (2026-11-03, `gpt-5.4-mini`, 116 recipes) forced non-meal roles on mains and sides that had no
meal role to choose (baked beans as sauce or dessert, scalloped potatoes as breakfast). Issue #426 E1-E4 changed how
the batch is made, and the whole batch was asked again (`--reask-v3`). Two routes, with their counts:

- **Not asked (E1):** a main or side whose allowed roles hold no meal-filling role (protein_main, one_bowl, staple,
  vegetable) is no longer sent to a model. Its `meal_role` stays null and open for a human reviewer, who still sees
  `review_roles` (staple and one_bowl added). 121 such recipes at the time of the issue; earlier model answers for
  them are dropped.
- **Asked:** 126 open recipes (93 baked goods, 18 sides, 9 mains, 6 soups) were exported with
  `python -m app.data.recipe_tags --reask-v3 --export-open data-engineering/data/staging/tag-v3/open.jsonl` and
  answered by a Claude model (`claude-opus-5-5`, run as a workflow subagent) following the PROMPT's meal_role part,
  with `protein_sources` always null, then loaded with
  `--reask-v3 --answers data-engineering/data/staging/tag-v3/answers.jsonl --answers-model claude-opus-5-5`.
  No OpenAI call was made. 24 answers are null (no allowed role fits, e.g. a sourdough starter, a quiche or
  lasagna whose only allowed role is staple, cornbread with no staple option). 2 dessert answers for sides were
  dropped by E2 (the rules had found a protein), so 100 recipes hold a batch value.
- The batch now holds 233 values (100 `meal_role`, 100 `contains_staple`, 33 `protein_sources` set to [] by a
  dessert role). Every value is `method: llm`, `reviewed: false`. The frozen `recipe-tags-v1/llm` batch and the
  v2.2 entries were not touched. The tag file's `llm_usage` header keeps the earlier OpenAI spend; its `models`
  field lists both (`gpt-5.4-mini`, `claude/claude-opus-5-5`).

| Role in the batch | Recipes |
| --- | ---: |
| staple | 36 |
| dessert | 33 |
| breakfast | 14 |
| snack | 10 |
| soup | 6 |
| vegetable | 1 |

## The sample

- Drawn by `data-engineering/scripts/v3_tag_sample.py`, seed 20261103, from the tag file:
  `uv run --project backend --with openpyxl python -I -X utf8 data-engineering/scripts/v3_tag_sample.py`.
- 40 recipes, 93 rows, one row per field. At least one recipe in every meal-role stratum: breakfast 6, dessert 13,
  snack 4, soup 2, staple 14, vegetable 1.
- `sample.xlsx` is the blank sheet for the reviewer. The reviewer columns ("value after looking" and
  "checked in person") are empty. The sheet does not show the source or any other batch value.
- `sample-filled.xlsx`, `accuracy.md` and `accuracy.json` belong to the first draw (the 2026-11-03 `gpt-5.4-mini`
  batch). They are superseded by this draw and do not score the current batch.
- `sample.json` is the draw record.
- Calibration before the scoring (owner 2026-11-04): two people label the same 30 of the 126 asked recipes on their
  own, without the model's answers, drawn with seed 20261104; at least 24/30 agreement before the 40-recipe scoring.
  The draw is `calibration-30.json` (titles and allowed roles only, no answers), made by
  `random.Random(20261104).sample(sorted(keys of open.jsonl), 30)`. Not labelled yet.

## Scoring

After the reviewer fills `sample.xlsx` in person:

```text
uv run --project backend --with openpyxl python -I -X utf8 data-engineering/scripts/review_table_accuracy.py <filled.xlsx> --sample data-engineering/docs/tag-sample-20261103/sample.json --out data-engineering/docs/tag-sample-20261103/accuracy.md
```

Acceptance line (owner 2026-11-04): meal_role correct in at least 36 of 40, and no savoury main or side tagged
sauce, dessert or drink. Only rows marked 是 count. The report shows a strict all-checked agreement rate and a determinate rate excluding all
reviewer nulls, even when the batch value is also null; each rate has a Wilson 95% interval. In the strict rate, a null
counts as agreement only when it equals the batch value. Publish the
accuracy with the filled sheet. Then the owner decides:

```text
uv run --project backend python -m app.data.recipe_tags --accept-batch recipe-tags-v1/llm-v3-20261103
```

It marks only this batch's `llm` values reviewed. It does not touch `recipe-tags-v1/llm` or the review-table batch.

## Not covered

Rule-decided tags of the new recipes (3,784 role values) are not gated and not sampled here.
The planner reads them now. That was already true for v2.2 and is the owner's call (see the PR notes).
