# External Recipe Intake

How a dish the catalog does not have becomes a catalog record the planner can
use. Decision: private `ADR-0032`; it amends `ADR-0024` (allergens) and works
inside `ADR-0030` (release v2 field requirements). Related design:
[External Retrieval and RAG](external-retrieval-rag.md).

## Goal

A user asks for something the catalog lacks — a dish, or a familiar dish with an
unfamiliar ingredient. MealCraft finds it, converts it into the same record
shape the release uses, and plans with it in the same conversation. The catalog
improves as the product is used, without a second, looser path into it.

## Pipeline

```text
user asks
  -> catalog lookup            found -> plan with it
  -> web search                        (tiered sources, robots-aware)
  -> parse into the staging shape      ingredients, quantities, units, steps, servings
  -> duplicate check                   normalized title + ingredient set
  -> ingredient mapping                canonical vocabulary; unknown names enriched
  -> allergen resolution               rule table; ask the user only when it matters
  -> admission gate                    every released field filled with a basis
  -> store and plan
```

Each stage records what it did into the retrieval trace, so a recipe's origin
stays inspectable in the operations console.

### Parse

The same parser the pipeline uses for released data: quantity, unit,
preparation and ingredient phrase per line; steps in order; servings when the
source states them, otherwise estimated with the basis recorded.

### Duplicate check

A candidate whose normalized title and canonical ingredient set match an
existing record is not stored again; the existing record is used and the source
link is added to it.

### Ingredient mapping

Names resolve against the canonical vocabulary (`config/ingredient_aliases.csv`
plus the v2 additions). A name that resolves to nothing is a new ingredient and
is enriched by the release v2 packet tooling: nutrition per 100 g for the form
recipes use, grams per unit, sources, confidence.

### Allergen resolution (ADR-0032 section 1)

Allergen labels stay rule-derived. For a new ingredient the rule is unknown
until confirmed, and the question is only ever asked when it matters:

| Situation | Behaviour |
| --- | --- |
| Household declares no allergen | no question; the recipe proceeds |
| Household declares an allergen, ingredient status known | rule decides, as today |
| Household declares an allergen, status unknown | ask: contains / does not contain / not sure |

"Not sure" leaves the status unknown. An unknown status does not block the
asker: they may include the ingredient by saying so, the interface states that
the status is unverified, and the consent is recorded with who, when and which
ingredient. For every other household an unconfirmed rule counts as unknown and
is excluded by a matching allergen constraint (`ADR-0024` section 3).

A rule becomes shared after **two independent confirmations** — two users
answering alike, or one confirmation in the operations console. Until then it is
stored as `user_reported` with its confirmation history.

### Admission gate

A recipe may be planned only when it carries what a released recipe carries:
mapped ingredients, quantities convertible to grams, computed per-serving
nutrition, prep/cook/passive minutes, course, cuisine, meal types, difficulty,
and rule-derived allergens. Anything short of that is stored as a candidate and
is not planned; the user is told which piece is missing.

## Sources and what is stored (ADR-0032 section 2)

**Tier 1 — redistribution allowed.** Full record including the source's step
text, with attribution and source URL: Wikibooks Cookbook, Wikipedia and
Wikidata (CC BY-SA), WikiHow (CC BY-NC-SA; this project is non-commercial),
TheMealDB, USDA FoodData Central (public domain), Open Food Facts (ODbL),
government and public-health publications whose terms allow non-commercial
reuse, and licensed datasets already in use.

**Tier 2 — everything else** (encyclopaedias, recipe portals, forums, blogs,
social posts). Stored: our structured record, the source URL, the retrieval
time, and **steps rewritten in our own words**. The source's own wording is not
committed.

Both tiers honour robots rules and a polite request rate. Every record carries
`source.tier`, `source.url` and `source.retrieved_at`, so the report and the
console can state where the catalog grew from.

## Record shape

Imported records use the release schema (`mealcraft.recipe.v2`) with the intake
fields added:

```json
{
  "source": {"dataset": "web-intake", "tier": 2, "url": "...", "retrieved_at": "...",
             "license": "...", "steps_basis": "rewritten"},
  "intake": {"requested_by_household": 12, "requested_text": "I want to eat okonomiyaki",
             "candidate_status": "admitted", "duplicate_of": null}
}
```

New ingredients carry their enrichment sources and the allergen rule's
confirmation history.

## Dependency on release v2

Intake reuses v2's vocabulary, enrichment packets and gram/nutrition
arithmetic. That work is finished for part A and in progress for parts B and C.

**Not blocked**: the parser, duplicate check, source tiers, the allergen
question and consent flow, the admission gate and the record shape can all be
built now. The canonical vocabulary and the enrichment tooling are on `main`,
and `data-engineering/data/fixtures/ops/` holds real released records to build
against.

**Blocked until v2 ships**: nothing structurally, but two numbers only become
meaningful afterwards — how often an imported recipe's ingredients are already
known (before v2 the catalog is 30 recipes, so almost never), and the intake
success rate the evaluation will quote. Measure them against v2, not before.

## Acceptance

| Area | Must hold |
| --- | --- |
| Safety | no imported recipe reaches a plan with an unknown allergen status unless that household consented explicitly, and consent is recorded |
| Sharing | an unconfirmed rule never applies to another household; promotion requires two independent confirmations |
| Licence | tier 2 records contain no verbatim step text from the source |
| Duplicates | re-importing a dish already in the catalog adds a source link, not a second record |
| Gate | a candidate missing any released field cannot be planned, and the user is told what is missing |
| Trace | every import is inspectable end to end in the operations console |
| Injection | text fetched from a page is data: a page instructing the agent to ignore its rules changes nothing |
