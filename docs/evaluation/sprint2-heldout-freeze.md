# Sprint 2 held-out freeze and sealed handoff

This is a procedure, not an executed freeze or an evaluation result. Follow
the [authoring guide](sprint2-heldout-authoring-guide.md) and
[isolated author brief](sprint2-heldout-author-ai-brief.md).

## Before a freeze

1. Owner assigns the non-tuning author, independent non-tuning reviewer and
   sealed-run operator. Record identities and conflict declarations privately.
   The owner and developers receive counts and attestations, never cases.
   The coordinator is a non-owner teammate who copies files without seeing
   questions. The quota approver is neither the author nor the reviewer.
2. Declare category/language/source/feature/subtype quotas **before authoring**.
   Author and reviewer keep the dated manifest and its SHA-256. Do not use
   tuning weaknesses or observed system outputs to pick cases.
3. Author writes privately in a new isolated conversation; reviewer independently
   extracts fields from original requests before comparing the author's gold.
   Resolve discrepancies against user wording and frozen neutral evidence,
   not what MealCraft or a baseline returned. Record pre-adjudication judgments.
4. Check safety, ambiguity, provenance, bilingual meaning, reference answers and
   request-intrinsic contradiction proofs. Catalog-based planning requests are
   `catalog_dependent`: review the constraints, not an invented feasibility
   label. The future sealed, independent catalog adjudication is a prerequisite
   for scoring these cases; this toolkit does not implement it. That process
   must preserve the original pending label and append digest-linked decisions,
   never infer truth from the evaluated planner's success/failure or a timeout.
   Unknown halal/allergen evidence is not a verified safe ingredient.
5. Resolve authoring errors before freeze without disclosing them to developers;
   catalog dependence is an explicitly retained pending decision, not an error.
   Run the standalone format and readiness checks. Retain private review logs;
   release only aggregate counts, reviewer attestations and tool versions.
6. Pre-register all system arms, information access, catalogs, product/price
   snapshots, model versions, prompts/configuration digests, repetitions,
   budgets, seeds where supported, score definitions and void handling. Confirm
   agreed product features are ready. Unready features are a release prerequisite,
   not a reason to silently remove their question coverage.
7. Before giving the brief to the author, the coordinator checks its reference
   facts against the frozen-release user guide. Shared-member diets, attendance,
   halal and per-person allergen avoidance come from accepted design decisions
   (ADR-0071 and the accepted halal scope), not a claim about today's guide.
   Confirm them against the release guide before use; if absent, pause and have
   the guide corrected without showing questions to developers.
8. Freeze the neutral field dictionary before questions are frozen. The author
   and reviewer review inline field types/units/scopes and any extensions;
   record its exact-byte SHA-256 in `quota_manifest.fields_sha256`. A separately
   reviewed adapter must support this dictionary without seeing sealed cases.
   Developers may inspect the neutral dictionary's keys/types/units, never
   question values. Validate the adapter interface on synthetic data before
   sealing questions; this task does not implement that adapter.

## Fingerprint and lock

The author/reviewer computes SHA-256 on the **exact final bytes**, records the
UTC date/time, byte count, format version, predeclared manifest digest and
reviewer attestation, then puts the file in controlled read-only storage. Also
hash the exact field-dictionary file, template/schema and frozen reference-facts
version. Preserve dictionary bytes (including line endings); do not reformat it
after recording its digest. The adapter uses that same frozen dictionary.
When reviews are recorded in a review attestation (authoring guide, "Several
reviewers, or an AI-executed review"), also hash the exact attestation file and record
the checker's `checker_version`, the reviewers and their `executed_by`, and the
`limitations` the readiness run reported. An AI-executed review stays labelled as
such in every record derived from it.

```powershell
# The author runs this on their own final file; this chat must not open it.
Get-FileHash -Algorithm SHA256 -LiteralPath "X:/author-owned/final-cases.json"
```

The packet contains scenario inputs, gold, provenance and review material with
separate access controls. The release manifest lists a digest for each file.
Catalog-dependent dispositions remain in the immutable author file. The future
sealed adjudicator's own version, catalog/price digests and decisions must be
recorded separately before any system results are used for comparison. Until
that independent mechanism is ready, these cases cannot yield a formal score.
Never paste contents into the owner/developer chat, PR, CI log or issue. The
developer-visible record contains digests, dates, totals and role attestations
only; source URLs and per-case IDs may themselves reveal questions and stay sealed.

## Run without reading

This authoring schema is an interchange, **not a drop-in format for an existing
evaluation runner**. Before formal use, a separately reviewed adapter must be
tested on developer/synthetic data only. It must separate scenario inputs from
gold and provenance, ensure systems never receive the answers, preserve the
frozen bytes, and suppress private case text from logs/artifacts. That adapter
and actual evaluation execution are outside this toolkit's scope.

An authorised operator supplies the sealed path/digest to a fixed automated
process without inspecting cases. That process verifies digests, runs all
pre-registered systems on the same frozen set and reference facts, and emits
only approved aggregates with category, language and source denominators.
Multiple pre-registered repetitions belong to **one formal evaluation campaign**;
an attempted run's failure and retry must be logged, not silently replaced.
Do not tune between repetitions or rerun selectively for a better result.
Any API cost or access requires separate authority; this procedure grants none.

## Mistakes after freeze

Do not edit question, wording, gold or frozen bytes, even to fix a typo. Keep
an append-only void ledger linked to the frozen digest. An independent reviewer
records case reference (in the sealed ledger), reason, evidence, date and
adjudicator. Apply exclusions identically to every arm and report original,
voided and remaining counts plus effects on coverage. Do not void a hard case
because one system failed. If an essential quota becomes invalid, report that
limitation rather than secretly replacing cases in the same release.

An unseen replacement set is a new version and campaign with renewed author
separation, not a revised score on the old set. After the formal campaign,
failure analysis is released only through an authorised controlled review,
with at least the agreed failure coverage and cases where a baseline succeeds.
Once specific cases inform changes, later scores on them are diagnostic only.
