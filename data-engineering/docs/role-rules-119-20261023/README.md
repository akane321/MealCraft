# Evidence-only role refinements: second-edition worksheet

This dated review implements the owner's staple/component refinements and
conditional tuber-vegetable rule, documented in ADR-0085. It is not an
acceptance tool and does not certify worksheet suggestions as human gold labels.
The entire failed model batch remains gated.

## Files and interpretation

- [119-source.csv](119-source.csv): the 119 unique recipe IDs, titles and
  proposed roles from the supplied worksheet's `3 被规则挡住` tab. Private
  reviewer notes and the workbook itself are not copied into the public repo.
- [119-comparison.md](119-comparison.md) and its JSON: per-ID comparison,
  retained reasons, all-catalog rule/allowed-role changes and a fixed-seed
  sample awaiting human review. The worksheet's bean decisions predate the
  owner's no-protein-main-promotion decision; pupusas now follow the owner's
  staple decision, not the worksheet's one-bowl suggestion.
- [review.md](review.md) and its JSON: formal non-model tag changes, all
  frozen-field suggestions, preservation assertions and ingredient evidence.
  Rule-owned fields can refresh; model-owned values/provenance/review marks
  and usage cannot. Counts of suggested changes are not release counts.
- [report-comparison.md](report-comparison.md) and its JSON: authorised
  developer report differences from the baseline in `review.json`.
  They are archive comparisons, not a fresh baseline replay, a single-rule
  ablation or a new held-out experiment. Timing files are not regenerated.

## Reproduction

Use the baseline revision recorded in `review.json` for `<base>` below. From
the repository root, with `backend` on `PYTHONPATH` and an offline environment
that does not load `.env`:

```text
python -m app.data.recipe_tags
python data-engineering/scripts/role_rules_review.py --base <base> --previous-review <base> --output-dir data-engineering/docs/role-rules-119-20261023
python data-engineering/scripts/role_rules_119_review.py --base <base> --input data-engineering/docs/role-rules-119-20261023/119-source.csv
```

The second script reuses the prior dated review at the baseline to compare
seasoned-vegetable content admissions. The third compares exact listed
ingredients against both source-rule versions and never writes reviewed tags.
Only run the four developer reports authorised in the task; do not run any
protected evaluation or batch-acceptance tool. Document integrity checks that
read protected reports are left to CI. Human review remains a separate step.
