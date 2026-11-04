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

## No checked-in review table yet

No review table is committed. An earlier revision of this directory carried a
283-row dry-run table and its pre-review summary, said to come from a local,
untracked `comparison.json`. Those files were not reproducible: the input is not
in the repository, and their `mapping_method` and `review_reason` values
(`exact`, `fixed_seed_matched_sample`, `candidate_suggestion`,
`mapping_requires_human_confirmation`) are not what this tool writes. They were
removed on 2026-11-02, and the table must not be filled in by hand.

The repository holds no `offline-algorithm-comparison-dev-v1` output at the
moment, so there is no input from which to regenerate a table. Once a
development-set comparison output is committed (or its location is named here),
add the exact `generate` command and the output file names to this section so
anyone can reproduce the table byte for byte; the tool is deterministic for a
given input and seed. Do not hand out a table for review until then.
