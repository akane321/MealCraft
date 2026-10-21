# Sprint 2 isolated held-out authoring guide

**Tooling and instructions only: no questions, gold labels or evaluation results.**
This is a new authoring interchange (`sprint2-authoring-v1`), not the legacy v2
episode format. It does not change a scoring rule or provide a runtime adapter.
See [freeze and handoff](sprint2-heldout-freeze.md) and the
[self-contained bilingual author brief](sprint2-heldout-author-ai-brief.md).

## Separation of roles

The owner appoints one teammate furthest from prompt, planner and baseline
tuning as author, and another non-tuning teammate as independent gold reviewer.
Appoint a coordinator: a teammate who copies the standalone files, does not see
questions, and is **not the owner**. The quota approver must differ from both
author and reviewer; the coordinator may approve quotas if independent.
The author operates a **new, isolated AI conversation** in an empty folder.
Disable cross-conversation memory or confirm the service has none. No project
checkout, knowledge checkout, repository clone, developer chat history, system
outputs, scores or failure examples enter that conversation.

The owner, Claude and development Codex conversations are tuning participants:
**none may see draft or frozen questions, gold, quotes, or per-case logs**.
The owner must not operate the isolated author conversation. The author keeps
drafts in their own controlled location; the reviewer receives them directly.
Only quota counts, role attestations, dates, versions and digests go back to
developers before the sealed evaluation campaign.

## Predeclare before collecting or writing

Fill the empty [manifest/template](../../scripts/sprint2-heldout-template.json).
The named coordinator approves it before authoring. Keep its dated original and
hash in the author's private workspace; changing counts after observing system
results is forbidden. The owner chooses the positive counts for the last two
groups and each subtype; this toolkit does not silently invent that decision.

| Primary category (no double counting) | Required size | Subtypes to declare |
|---|---|---|
| `planning` | at least 80 | `meal`, `day`, `week`; household sizes, budget levels, allergens, diets/halal, shape, cooking time, nutrition and pantry |
| `intent` | at least 100 | `planning`, `food_qa`, `out_of_scope`, `injection`, `preference` |
| `multi_turn` | positive exact count, with each subtype represented | `swap`, `meal_shape`, `budget_replan` |
| `adversarial` | positive exact count, with each subtype represented | `infeasible`, `contradiction`, `hidden_allergen`, `local_name` |

Every primary category includes English and Chinese. For `intent`, Chinese is
at least `ceil(intent_count / 3)`; predeclare each category's Chinese minimum.
Use the dominant language of the actual request (`en` or `zh`), not its source
country. English ingredient names in a Chinese sentence do not make it English.
Do not machine-translate duplicate questions merely to meet a quota. A reviewer
checks natural language, local terminology and whether the gold preserves the
same meaning; fluent wording is not proof of feasibility.

For the whole set, predeclare the real-forum count as either floor or ceiling
of one third of the total. Each case has one primary category and one source;
secondary coverage tags do not inflate either denominator. Declare positive
minima for these feature tags: `full_table`, `shared_dishes`, `member_rules`,
`attendance`, `halal`, `basic_seasonings`, `sodium_limit`, `horizon_1`, `horizon_14`,
`two_trips`, `perishable_window`. Include at least two planning cases lasting
8–14 days; predeclare their exact count/coverage. They have purchases before
day 1 and day 8, each separately subject to the weekly budget. Leafy greens,
bean sprouts and pea shoots, fresh fish and fresh shellfish must be used within
three days of the purchase supplying them; fresh meat is not in this short-lived
class. These are not one combined budget or one shopping trip; do not assume
a mid-period fresh restock.
These derived procurement facts belong to `plan`/`replan` gold. Intent-only
extraction tests retain stated user facts rather than inventing service defaults.
Include genuine 1-day and 14-day boundaries, arbitrary start days, and smaller
explicitly requested shapes as well as full defaults. Counts are design targets,
not a claim that a feature has passed acceptance.

`two_trips` and `perishable_window` tags are allowed only when `horizon_days > 7`.
`horizon_1` requires exactly 1 day; `horizon_14` requires exactly 14 days.

## Gold without asking the product

- **Planning:** extract every explicit hard constraint with field, operator,
  value, unit, scope and evidence. Keep member-specific and whole-household
  constraints separate. Document the required meal structure, attendance,
  portion factors, requested horizon and applicable frozen reference facts.
  If feasibility depends on recipe/product availability, prices or quantities,
  use `catalog_dependent`: author the hard constraints only. Do not invent
  catalog facts or force a feasible/infeasible label without them. Only a
  request-intrinsic contradiction may be labelled `infeasible` at authoring,
  with a logical proof independent of the catalog, never a solver timeout.
- **Intent:** record an action and typed structured fields in `expected_fields`,
  including explicit unknowns/missing fields. State what must be clarified and
  what must not be inferred. A preference is not automatically a medical limit.
- **Food QA:** supply a fact-based reference answer and rubric of necessary
  claims, acceptable alternatives, forbidden unsupported claims and abstention
  conditions. Do not grade similarity to one model's wording.
- **Multi-turn:** preserve the preceding user turns and required state facts;
  declare the edited fields and `preserve` invariants. The proof must cover the
  final combined request, not just the last sentence. Do not seed it with a
  product-generated plan. If a neutral initial plan/state is needed, the author
  supplies independently verified structured facts in `expected_fields`.
- **Hard/adversarial:** distinguish actual infeasibility, inconsistent requests,
  missing facts requiring clarification, out-of-scope refusal and injection.
  Hidden ingredients require evidence, not stereotypes. Local names require
  reviewed ingredient equivalences, not guessed translations.

Nutrition values need explicit unit, person/meal/day/week scope and whether the
limit is opt-in. Basic seasonings still count for allergens and nutrition even
when not bought. Price evidence uses frozen products, pack sizes, availability,
pantry deductions and **whole-package procurement**, not consumed-quantity cost.
Only clear upper bounds selected by the household become hard medical-style
limits; do not invent prescriptions. A high-level accepted product description
is in the bilingual brief's **Frozen reference facts v1**: adult daily sodium
2,000 mg when enabled, dinner share 35% (700 mg/person), two shopping trips
after seven days, a three-day perishability window, and the public meal counts.
These user-facing facts are available to authors; catalogs are not required to
author `catalog_dependent` constraints. No scripts here calculate gold or run
the application. The later sealed workflow must independently resolve catalog
feasibility after freezing; that workflow is **not implemented by this PR** and
must not use the evaluated product's success/failure as its answer key.

For genuine user ambiguity, require clarification; for catalog-fact dependence,
keep the independently reviewed constraints as `catalog_dependent`, not as a
proved label. Other unresolved authoring mistakes remain pending. Keep rejected/rewritten drafts
in the author's private revision log with reasons independent of system results.

## Real forum wording: provenance, not imitation

Collect only public household cooking requests or comments from relevant
communities. Follow site terms and use minimal necessary excerpts. Record a
canonical public thread/comment URL and collection date for each user turn.
Retain wording and uncertainty; remove usernames, handles, contact details,
precise locations and unrelated passages using `[REDACTED]` markers. Record the
categories removed, not the removed values. A reviewer checks the remaining
text for re-identification risk. Do not put identifying source dumps in Git.

In a `forum` case every `turns[i]` equals the corresponding **redacted** quote,
with exactly one source record per turn. Do not invent a follow-up, household
size, budget or context. If a construction combines a quote with invented
turns, label it `authored`; it does not satisfy the real-forum quota. Store
source records with the sealed question pack, not in developer-visible reports.
Every nonempty redaction-note list needs a corresponding `[REDACTED]` marker in
that quote, and a marker needs notes; otherwise the checker rejects the record.
Use a canonical URL without tracking parameters/fragments; retain a stable
comment path if needed. A source being public does not mean personal details
may be republished without minimisation.

## Standalone format check

### Freeze the neutral field dictionary too

[sprint2-heldout-fields.json](../../scripts/sprint2-heldout-fields.json) defines
the neutral actions, member/attendance/meal/date/budget/diet/allergen/sodium/
pantry fields, their inline JSON types, units and allowed scope keys. It is
written from household needs, not copied from application schemas. Every
`expected_fields` has `action`; unknown fields/types are rejected. Every
constraint uses a dictionary `field`, allowed `unit`, correctly typed `value`
and dictionary `scope`; member scope also requires `target_member_ids`.
Ordered comparisons `le` and `ge` require numeric values (not booleans, strings,
arrays or objects), in addition to the dictionary's field type and unit checks.
An unknown value is omitted and identified in `clarification_fields`, not
invented or set to an untyped null. Null pantry quantity is explicitly supported.

Use only the following `gold.kind` / `disposition` combinations. For `intent`,
`answer` means the structured classification/extraction answer, not a feasible
plan or a completed food answer. `clarify` names missing/ambiguous fields;
`refuse` records refusal. Catalog adjudication applies only to planning gold.

| `gold.kind` | Allowed `disposition` |
|---|---|
| `plan` | `feasible`, `infeasible`, `catalog_dependent`, `clarify` |
| `replan` | `feasible`, `infeasible`, `catalog_dependent`, `clarify` |
| `intent` | `answer`, `clarify`, `refuse` |
| `qa` | `answer`, `clarify`, `refuse` |
| `refusal` | `refuse` |

The author and reviewer may add neutral fields/scopes **before** freeze, with
inline types/units, an updated dictionary version and review. `$ref` and dynamic
references are forbidden, including external URLs. Compute SHA-256 of its exact
bytes and set `quota_manifest.fields_sha256`. Pin the same dictionary for the
adapter and all systems; never open frozen cases to repair field names. If a
new field is needed after freeze, that is a new release, not a silent rename.

Only the author or reviewer runs this on their own drafts. Copy these files
alone into the isolated folder (keep validator and schema adjacent):
[validator](../../scripts/check_sprint2_heldout.py),
[schema](../../scripts/sprint2-heldout.schema.json),
[requirements](../../scripts/requirements-sprint2-authoring.txt), empty template
and the field dictionary (five files, with script/schema/dictionary adjacent).
Do not clone either repository or copy any existing dataset/report.

```text
python -m pip install -r requirements-sprint2-authoring.txt
python check_sprint2_heldout.py --input author-draft.json --format-only
python check_sprint2_heldout.py --input author-draft.json
# An extended dictionary may be selected explicitly, without scanning folders:
python check_sprint2_heldout.py --input author-draft.json --fields sprint2-heldout-fields.json
```

`--input` is mandatory; the checker never discovers a dataset, accesses the
network or calls a model. It refuses paths through protected heldout/holdout
directories, including resolved aliases. Put the new author draft in a separate
author-owned folder rather than such a directory. `--format-only` can check the
empty template, but means **not freeze ready**. A readiness check requires
`purpose=freeze_candidate`, approved quotas, coverage and completed independent
review metadata. It prints counts and redacted field/index errors only, not
case text or gold. It cannot prove truth, anonymity, natural language or actual
independence. Passing it does not replace human review or run an evaluation.

The empty template contains no case. Automated tests use impossible fictional
robot placeholders only. No real or realistic example is part of this toolkit.
