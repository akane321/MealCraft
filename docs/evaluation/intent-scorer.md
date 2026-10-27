# Intent scorer for the held-out run

This is apparatus, **a draft that needs an independent review and registered scoring definitions**, not run
admission, a freeze, a scored evaluation or a result. It is tested on invented gold only and loads no sealed file.

`backend/app/evaluation/intent_scorer.py` compares one system output with the expected action and expected fields of
one gold block (the shape is in `scripts/sprint2-heldout.schema.json`). It reads `kind`, `expected_fields` and
nothing else: `reference_answer`, `rubric`, `preserve` and every other key are ignored, and a test shows that changing
them does not change the verdict.

- **Observed action.** From the output slots: a plan wins over everything else (a refusal or a question next to a
  plan is not a clean refusal or clarification); then refusal, then clarification, then a plain answer
  (`food_qa`).
- **Fields.** The echoed request fields are read through the [field mapping](field-mapping.md). Strings are
  compared after trimming and lower-casing; list fields compare as sets. An expected value the system did not state
  fails. The product drops a false flag from its echo, so silence satisfies an expected `false` and nothing else.
- **Outcomes.** `pass`, `fail`, or `not_scorable`. A mismatch anywhere is a `fail` even if another part is
  `not_scorable`. `not_scorable` means the output cannot show the expected thing: an action such as a swap, a
  meal-structure change or a budget change; a field the product's echo cannot carry; a case that is not an intent
  case (planning feasibility needs the validator and the sealed catalog adjudication, question answering needs the
  rubric). It is reported as not scorable, never as a wrong answer.

Not covered: pre-registered scoring and void definitions, how `not_scorable` enters the aggregate report (the report
has no such status yet; the caller must not fold it into success), matching the questions a system asked to
`clarification_fields` (that needs language understanding), the sealed dictionary's extra fields, and everything
that needs the sealed set.

```text
PYTHONPATH=backend python -m pytest backend/tests/test_intent_scorer.py -p no:cacheprovider --basetemp <new-temporary-directory>
```
