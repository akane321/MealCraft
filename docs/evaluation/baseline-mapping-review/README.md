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

The input may be one completed `baseline-comparison-raw-v1` result or a
`baseline-comparison-v1` report. For a comparison report, all completed runs in
that report form one review population; failed runs have no mapping rows and are
not included.

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

For current mapping outputs, method is a faithful status-derived description:
`exact` for accepted mappings, `candidate_suggestion` for rows requiring review,
and `none` for unmatched rows. No method is recomputed. An optional AI field may
be added by a future schema, but it must not populate any human field.

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

## Developer dry run

The checked-in dry run was generated without new API calls from the existing
developer comparison output under
`.local/evaluation/sprint2-live-baseline-smoke-2026-10-25/comparison.json`.
It contains all suspicious rows plus the required seed-364 matched sample. The
generated pre-review report is the authority for its counts. The table
deliberately contains no human decisions.

- `developer-smoke-2026-10-25.review.jsonl` is the blank review table.
- `developer-smoke-2026-10-25.prereview.json` is the computable pre-review
  summary. Its accuracy, correction, and safety rates remain null or zero until
  a person completes the table; they are not claims of correctness.
