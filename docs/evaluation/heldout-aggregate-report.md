# Held-out aggregate report

This is apparatus, **not run admission, a freeze, a scored evaluation or a result**. It turns per-case outcomes into
the counts the [sealed handoff procedure](sprint2-heldout-freeze.md) allows to leave the sealed process:
category, language and source denominators. ADR-0074 requires results by category and by language, with real
forum wording and authored questions reported separately.

`backend/app/evaluation/heldout_report.py` takes one `CaseOutcome` per system, run and case and returns counts
and rates for the whole set, each category, each language, each source and each category-language-source cell.

- **Input.** An opaque `case_ref`, `system_id`, `run`, the three labels, a status
  (`success`, `failure`, `timeout`, `error`, `missing`) and a void flag. Question text, gold and provenance are
  not accepted: unknown fields are rejected, so a caller cannot pass them in by mistake.
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

```text
PYTHONPATH=backend python -m pytest backend/tests/test_heldout_report.py -p no:cacheprovider --basetemp <new-temporary-directory>
```
