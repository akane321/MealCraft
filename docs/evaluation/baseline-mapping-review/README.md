# Baseline ingredient mapping review

This directory contains the independent review workflow required by Issue #364
and ADR-0069. It reads mapping records already present in baseline comparison
outputs. It does not invoke a model, remap an ingredient, or modify mapping
thresholds and aliases.

## Generate a review table

From `backend/`:

```bash
python -m app.evaluation.baseline_mapping_review generate \
  path/to/comparison.json path/to/review.jsonl
```

The input is an `offline-algorithm-comparison-dev-v1` report produced by the
current baseline comparison runner, or one or more `*.jsonl` record files of the
conversation-protocol arms (`app.evaluation.baseline_arms`, see
[baseline-arms.md](../baseline-arms.md)) and the pure-LLM runner, read together as
one population in the order given:

```bash
python -m app.evaluation.baseline_mapping_review generate \
  rag.jsonl general-agent.jsonl path/to/review.jsonl
```

In record files, an answered case with a scored plan contributes its mapping
rows; a clarification, a refusal and an invalid output have none. All completed runs in that report form one
review population; failed runs have no mapping rows and are not included.

The default seed is `364`. Every `needs_review` and `unmatched` row is retained.
The tool then uses Python's fixed-seed random sampler to select 200 `matched`
rows, or every matched row when fewer than 200 exist. Selected rows are sorted
by system, episode, run, and stable row ID, so output order does not depend on
the random draw order. `--matched-sample-size` may increase, but not reduce, the
200-row target.

Each JSONL row uses schema `baseline-mapping-review-v1` and contains:

- `row_id`, a SHA-256-derived ID over the run identity, mapping values, and
  duplicate occurrence number;
- `system_id`, `episode_id`, and `run_id`;
- original text and grams;
- mapped canonical ID and display name, where present;
- method, status, review reason, and candidate IDs/names;
- source-population counts and sample seed;
- blank human fields: `decision`, `corrected_ingredient`, `notes`,
  `personally_reviewed`, `safety_error`, and `safety_error_type`.

Mapping method and review reasons are copied from the shared mapping result
without recomputation. Methods therefore retain the current mapping vocabulary:
`id`, `name`, `alias`, `similarity`, `hierarchy`, or null for an unmatched row.
An optional AI field may be added by a future schema, but it must not populate
any human field.

Human reviewers set `personally_reviewed` to `true` and `decision` to `correct`
or `incorrect`. An incorrect decision requires `corrected_ingredient`. A safety
error additionally sets `safety_error` to `true` and selects
`allergen_omission` or `false_allergen_assignment`. A reviewer may set
`personally_reviewed` to `false` to mark an unusable/invalid review row; it is
counted as invalid and excluded from accuracy.

## Produce the accuracy report

```bash
python -m app.evaluation.baseline_mapping_review report \
  path/to/review.jsonl path/to/accuracy.json
```

Malformed JSON, missing fields, duplicate IDs, inconsistent population counts,
invalid decisions, and decisions not backed by `personally_reviewed=true` are
rejected.

Accuracy is reported separately for ordinary `matched` rows and suspicious
rows (`needs_review` plus `unmatched`) with 95% Wilson intervals. Only rows with
`personally_reviewed=true` and a valid decision enter either denominator;
unreviewed and invalid rows are never assumed correct. An unmatched row enters
the suspicious denominator only after review: `correct` means leaving it
unmatched was right, while `incorrect` requires the corrected ingredient.

The suspicious proportion uses every source mapping row, not merely the review
table: `source_suspicious_row_count / source_mapping_row_count`. The corrected
rate uses all valid reviewed rows as its denominator. Allergen omissions and
false allergen assignments are reported separately and list their row IDs.

## The checked-in review table (development records, 2026-11-07)

`review.jsonl` is the review table of the development records of the conversation-protocol arms, filled in;
`accuracy.json` is its report. Inputs: the strong-rule arm on the 21 `v3-meal-day-week` development episodes
(regenerated on `main` 9389a45, `docs/evaluation/baselines/dev/strong-rule.jsonl`), and the 11-04 RAG (6 episodes)
and general-agent (3 episodes) trial records in the same folder. No held-out record is read.

From `backend/`:

```bash
python -m app.evaluation.baseline_arms --arm strong-rule \
  --episodes data/evaluation/dev/v3-meal-day-week/episodes --anchor-date 2026-09-28 \
  --output docs/evaluation/baselines/dev/strong-rule.jsonl
python -m app.evaluation.baseline_mapping_review generate \
  ../docs/evaluation/baselines/dev/strong-rule.jsonl \
  ../docs/evaluation/baselines/dev/rag.jsonl \
  ../docs/evaluation/baselines/dev/general-agent.jsonl \
  review-blank.jsonl
python -m app.evaluation.baseline_mapping_review report \
  ../docs/evaluation/baseline-mapping-review/review.jsonl \
  ../docs/evaluation/baseline-mapping-review/accuracy.json
```

The blank table has 275 rows (all 75 `needs_review` and `unmatched` rows, 200 sampled `matched` rows, seed 364)
from 3,403 source mapping rows. Two runs gave byte-identical files, sha256
`78aa043f8b09c8825326b83c50e7ad21cfbc2d9cfa627ab83d70383c5091bc9d`. The strong-rule output differs between runs
only in `elapsed_seconds`, which the table does not read.

How the human fields were filled: AI suggested a decision for each row from rules Liu-ub set (listed in the
2026-11-07 Knowledge task record); Liu-ub then checked every row and set `personally_reviewed` herself
("逐行由 AI 辅助核验，Liu 已亲自核对"). The two `noodles` → `pasta` rows are incorrect, but the dish
("Stir-fried chicken noodles") does not say which noodles and the catalog has no generic noodles, so their
`corrected_ingredient` says so and `safety_error` stays null.
