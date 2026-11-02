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
  compared after trimming and lower-casing; list fields compare as sets (order and repeats do not matter, so
  `["a", "a"]` equals `["a"]`). A boolean never equals a number (`true` does not match `1`). An expected value the
  system did not state fails, with one exception: the echo cannot tell "stated none" from "not stated", so an expected
  value that is empty is satisfied by silence. That is `false` (the product drops a false flag from its echo), an
  empty list, `None`, an empty string, and for `cooking_time_minutes` the no-limit value (the product's 240, which the
  field mapping already reads as not stated; the dictionary's own encoding of "no limit" is for the sealed side to
  confirm). A stated value against an expected empty one still fails (expected no allergen, echoed `peanut`).
- **Refuse and clarify turns.** On a turn that refuses or asks a question the product may not have extracted the
  constraints yet, so an expected field then reads as "not stated" and fails. That is the conservative direction, and
  the sealed side decides it when it registers the scoring definition.
- **Outcomes.** `pass`, `fail`, or `not_scorable`. A mismatch anywhere is a `fail` even if another part is
  `not_scorable`. `not_scorable` means the output cannot show the expected thing: an action such as a swap, a
  meal-structure change or a budget change; a field the product's echo cannot carry (this includes `start_date`,
  which the product fills with a default, see the field mapping); a case that is not an intent case (planning
  feasibility needs the validator and the sealed catalog adjudication, question answering needs the rubric). The kind
  is checked first, so a planning or question-answering gold block without `expected_fields.action` is `not_scorable`
  and does not raise; an intent block without an action is still rejected. It is reported as not scorable, never as
  a wrong answer.
- **Known gap: limits-type refusals.** The product states a refusal in the refusal slot only for an out-of-scope,
  restricted or adversarial request. A refusal from the limits (an impossible budget and the like) reaches the output
  as a reply or a clarifying question, so a gold block that expects `refuse` and an output that shows only an answer
  or a question is `not_scorable`: a limits refusal cannot be told from a plain answer or question. A plan against an
  expected refusal is still a `fail`. This hides a system that never refuses by limits; whether to score it another
  way is for the sealed side to decide when it registers the scoring definition.

Not covered: pre-registered scoring and void definitions, how `not_scorable` enters the aggregate report (the report
has no such status yet; the caller must not fold it into success), matching the questions a system asked to
`clarification_fields` (that needs language understanding), the sealed dictionary's extra fields, and everything
that needs the sealed set.

```text
PYTHONPATH=backend python -m pytest backend/tests/test_intent_scorer.py -p no:cacheprovider --basetemp <new-temporary-directory>
```
