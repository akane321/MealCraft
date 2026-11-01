# Held-out aggregate report

This is apparatus, **not run admission, a freeze, a scored evaluation or a result**. It turns per-case outcomes into
the counts the [sealed handoff procedure](sprint2-heldout-freeze.md) allows to leave the sealed process:
category, language and source denominators. ADR-0074 requires results by category and by language, with real
forum wording and authored questions reported separately.

`backend/app/evaluation/heldout_report.py` takes one `CaseOutcome` per system, run and case and returns counts
and rates for the whole set, each category, each language, each source and each category-language-source cell.
The same outcome may carry already-scored named `binary_metrics` and `continuous_metrics`; the aggregate report
ignores them, while the paired analysis below consumes them without changing their scoring.

- **Input.** An opaque `case_ref`, `system_id`, `run`, the three labels, a status
  (`success`, `failure`, `timeout`, `error`, `missing`), a void flag and optional already-scored metric maps. Question
  text, gold and provenance are not accepted: unknown fields are rejected, so a caller cannot pass them in by mistake.
- **`case_ref` is never reported.** It is used only to check that every system and run covers the same cases,
  that a case keeps one set of labels, and that the void flag is identical for every system and run. A violation
  raises an error rather than producing a report.
- **Unknown is not success.** Timeouts, errors and missing outputs stay in the denominator. A missing output is a
  recorded `missing` status; an absent record is an error. Voided cases leave the denominator and are reported:
  declared, voided and remaining counts.
- **Repeated runs.** Rates are computed per run and then averaged; per-run rates are listed. Declared, voided
  and remaining counts are the same in every run by construction.
- **Output.** Sorted-key JSON with an LF ending, byte-identical for the same records in any order.

Not covered: a cell with very few cases can identify a single question; whether to suppress small cells is not
decided here. The report does not choose failure cases for analysis, load the sealed file, run any system or
decide which cases are void.

By default the coverage checks are relative to the supplied records. `aggregate(records, expected)` also takes an
`ExpectedManifest` from the sealed side, made of aggregate counts only: the expected systems, the number of runs per
system, the declared number of cases in each category-language-source cell (voided ones included) and the declared
number of voided cases. A different system set, a missing run, a different cell count, an unexpected cell or a
different void count raises an error, so an omission shared by every system and run is caught. The manifest holds no
case reference or text. A wholly failed run must still supply one `missing`, `timeout` or `error` outcome for every
expected case. Without a manifest this module is not a completeness gate, and it is still not a disclosure gate:
small-cell policy remains a prerequisite for formal use.

```text
PYTHONPATH=backend python -m pytest backend/tests/test_heldout_report.py -p no:cacheprovider --basetemp <new-temporary-directory>
```

## Paired statistical comparison

`backend/app/evaluation/heldout_statistics.py` compares the declared product with every other system using the same
validated `CaseOutcome` records. It never loads a question, gold label, system output or scorer. `success` is built in;
other binary and continuous metrics must be named in `MetricSpec` and supplied by the sealed scoring process. Pass the
same optional `ExpectedManifest` as `expected=` to reject an omission shared by every arm and run before analysis.

- Repeated runs are combined per episode before pairing. A continuous metric becomes its mean across runs. A binary
  metric first becomes the proportion of successful runs; for the episode-level rate, Wilson interval and McNemar
  table it is successful when that proportion is at least `0.5`. Per-run means and their population standard deviation
  remain in the output, so stochastic variation is not discarded.
- Binary comparisons report each arm's episode-level rate and 95% Wilson interval, the paired absolute rate
  difference with a percentile paired-bootstrap 95% interval, and an exact two-sided McNemar test.
- Continuous comparisons orient differences so positive always favours the product, then report the paired mean and
  median differences, their percentile paired-bootstrap 95% intervals, and the difference IQR.
- Voided episodes are excluded exactly as in the aggregate report. `failure`, `timeout`, `error` and `missing` remain
  unsuccessful. An absent declared binary metric on a `timeout`, `error` or `missing` row is a failure. Otherwise, if
  an optional named metric is absent, that episode is absent only from that metric's pair count; the reported
  `paired_n` and unpaired counts make the denominator explicit.
- Bootstrap randomness uses the reported seed (default `365`) plus stable comparison/metric labels. Sorted JSON from
  `heldout_report.render` is byte-identical for the same records in any order.
- Grouped comparisons are disabled by default because small-cell disclosure policy is unresolved. Setting
  `include_groups=True` emits category, language, source and category-language-source cells. This is apparatus, not
  permission to disclose them.
- Every product-baseline comparison includes the Issue #365 planning approximation
  `sqrt(0.6 / paired_episodes)`: about 60 paired episodes are needed to detect an absolute difference around ten
  percentage points. It is labelled as planning guidance, not a post-hoc power claim. Small observed differences are
  not evidence of equivalence.

The default is 10,000 bootstrap resamples. Tests use fewer resamples only to keep the synthetic suite fast.

```python
from app.evaluation.heldout_statistics import MetricSpec, compare

report = compare(
    outcomes,
    product_system_id="mealcraft",
    metrics=[
        MetricSpec(name="hard_valid", kind="binary"),
        MetricSpec(name="total_cost_sgd", kind="continuous", higher_is_better=False),
        MetricSpec(name="member_diversity", kind="continuous"),
    ],
    seed=365,
    include_groups=False,
)
```

This API accepts in-memory records deliberately: the sealed-side runner owns file locations and disclosure. Tests use
fictional identifiers only and make no model or network call.
