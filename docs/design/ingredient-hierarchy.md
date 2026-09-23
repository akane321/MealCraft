# Ingredient Hierarchy

> Status: **accepted target**, format and checker verified on `main`; the data is
> being written in three work packages and nothing in the product reads it yet.
> Decision: `decisions/ADR-0039` in the knowledge repository.

## 1. Why it exists

The planner decides whether a household may eat a recipe by matching the
household's excluded ingredients against the recipe's ingredient ids **exactly**
(`backend/app/planning/meal_beam.py`, `final_scope_validator.py`,
`recommendation_engine.py`). Exact matching is only right when every food has one
id and every id means one food. Neither is true:

- **one food, two ids.** The curated catalog calls it `firm_tofu`; release v2.1
  calls it `tofu`. Fifteen curated ids are like this, and no recipe uses both.
- **a food made from another.** `bacon`, `ham` and `bacon_grease` come from
  `pork`, but nothing in the catalog says so.
- **a family with no id of its own.** There is no `alcohol` ingredient; there are
  `white_wine`, `sake`, `mirin`, `beer`, `wine_cooking` and more.
- **names that lie.** `almond_milk` is not milk, `peanut_butter` is not butter,
  `eggplant` is not egg, `milkfish` is not milk.

So a household that says "no pork" today still gets bacon, and one that says "no
alcohol" gets whichever wines the model happened to name. The hierarchy records
what each ingredient belongs to, and an exclusion then removes the ingredient and
everything that belongs to it.

**Allergens are not this table's job.** Every ingredient already carries its
checked allergens (`backend/app/data/allergens.py`), and allergen filtering works
across both catalogs. Do not add an ingredient to a family only because it shares
an allergen: `almond_milk` is not `milk` even though a dairy-free diet avoids milk.

## 2. Semantics

An ingredient has zero or more **parents**. Each link names a relation:

| Relation | Meaning | Example |
| --- | --- | --- |
| `same` | one food under another id; points at the canonical id | `soba_noodle` → `soba_noodles` |
| `variety` | a kind, cut or form of the parent | `cherry_tomato` → `tomato`, `firm_tofu` → `tofu`, `sake` → `group:alcohol` |
| `made_from` | made mostly from the parent; still that food for anyone avoiding it | `bacon` → `pork`, `almond_milk` → `almond`, `bacon_grease` → `bacon` |
| `either_of` | the recipe allows either option, so it may be either | `milk_or_cream` → `milk` and `cream` |
| `may_contain` | often but not always contains the parent; excluded to be safe | `sausage` → `pork`, `rum_extract` → `group:alcohol` |

**Excluding X removes X and everything below it, through every relation.** It
never climbs: excluding `cherry_tomato` does not exclude `tomato`, because a
household that dislikes cherry tomatoes has said nothing about tomatoes. The one
exception is `same`, followed both ways, because it is one food under two ids.

`not_parents` records a look-alike that was considered and rejected
(`almond_milk`: `not_parents: ["milk"]`). It does nothing at run time; it is how
a reviewer sees the question was asked.

### 2.1 Groups

A **group** is a family that no single ingredient id stands for, such as
`group:alcohol`. Groups are declared in one shared file,
`data/ingredients/hierarchy/groups.json`, so any package can point at a group
before the others merge. `group:alcohol` is declared there already. Declare
another only when a real household request needs it, and write that request in
`serves`. Where an ingredient id already names the family
(`pork`, `beef`, `cheese`), use the id as the parent instead of inventing a group.
A group has no parents of its own in this version.

### 2.2 What "belongs" means when the answer depends on the person

Some links are a matter of rule, not chemistry: is `red_wine_vinegar` alcohol,
is `gelatin` pork? The hierarchy records **one** answer per link, the one a
careful host would assume for a guest who stated the restriction, and the
`reason` says what the answer rests on. Where it is genuinely split, use
`may_contain`: the planner then errs toward excluding. The owner of the package
that decides the ingredient makes the call and records it in that file's
top-level `notes` list: the question, the answer chosen, and why.

## 3. Files

Three files, one per work package, so three people can write in parallel
without merge conflicts, and `groups.json` for the groups all three share:

| File | Package | Owns |
| --- | --- | --- |
| `data/ingredients/hierarchy/wp1-curated.json` | WP1 | the curated catalog's ids that release v2.1 names differently (15) |
| `data/ingredients/hierarchy/wp2-animal-drink-prepared.json` | WP2 | release ids in food groups `protein`, `dairy`, `fat`, `beverage`, `prepared`, `condiment` (320) |
| `data/ingredients/hierarchy/wp3-plant-pantry.json` | WP3 | release ids in `vegetable`, `grain`, `seasoning`, `fruit`, `flavoring`, `herb`, `sweetener`, `leavening`, `plant_milk`, `liquid` (381) |

Ownership is by the ingredient being decided, not by its parents: a WP3 entry may
name a WP2 id or a group declared in any file as its parent.

```json
{
  "schema_version": "ingredient-hierarchy-v1",
  "package": "WP2",
  "title": "Meat, fish, eggs, dairy, fats, drinks, condiments and prepared foods",
  "drafted_by": "the agent or person that wrote the entries, and the model if an agent",
  "accepted_by": "the package owner who read and accepted every entry",
  "notes": [
    "red_wine_vinegar: not alcohol. Fermentation has turned the alcohol into acid, and vinegar is commonly accepted by households avoiding alcohol."
  ],
  "entries": {
    "bacon": {
      "parents": [{"id": "pork", "relation": "made_from"}],
      "not_parents": [],
      "reason": "Cured, smoked pork belly; recipes write it as bacon strips or slices. Turkey bacon has its own id."
    },
    "carrot": {
      "parents": [],
      "not_parents": [],
      "reason": "A root vegetable, a family of its own; no other catalog id is carrot or contains it."
    }
  }
}
```

### 3.1 Unknown and undecided

- An ingredient **with no entry** is undecided. The planner treats it as
  belonging to nothing, which is today's behaviour.
- `"parents": []` is a **decision**: it belongs to nothing. It needs a reason
  like any other entry.
- There is no "unknown" parent. If you cannot tell, look at how recipes write it
  (`--show`); if it is still split, use `may_contain`.

## 4. Rules the checker enforces

`python scripts/check_ingredient_hierarchy.py` fails on any of these. CI runs it
on every pull request.

1. every entry key and parent is a catalog ingredient id or a declared group;
2. each ingredient is decided in the file of the package that owns it, and once;
3. every entry has a `reason` of at least 20 characters, and no reason text is
   used more than three times across all files — a repeated reason is a
   template, not a judgement;
4. relations are one of the five above; `same` points at one canonical id that is
   not itself an alias, and never at a group;
5. no cycles;
6. **every look-alike is decided**: if an id's name contains another id as whole
   words (`almond_milk` contains `almond` and `milk`), that id must be reachable
   as an ancestor or listed in `not_parents`;
7. groups are declared only in `groups.json`, each with a `description` and a
   `serves`.

`--require-complete WPn` additionally fails while any id the package owns is
undecided; acceptance runs it. With all three packages named, it also fails on a
group nothing belongs to.

## 5. Consumers

| Consumer | Uses it for | Owner |
| --- | --- | --- |
| Planning product path and recommendation engine | expanding a household's excluded ingredients before eligibility is checked | WP1 |
| Agent constraint vocabulary | offering groups (`group:alcohol`) as words the model may use | WP1 |
| Evaluation scorers | **nothing, for now.** A system that expands exclusions only becomes more conservative; letting the scorer expand them changes what a pass means and is a separate, disclosed decision | — |

Loading goes through `backend/app/data/ingredient_hierarchy.py` only; nothing
else parses these files.

## 6. Tools for authors

```
python scripts/check_ingredient_hierarchy.py                          # errors + progress
python scripts/check_ingredient_hierarchy.py --next WP2 --count 40    # the next ids to decide
python scripts/check_ingredient_hierarchy.py --show bacon             # evidence for one id
python scripts/check_ingredient_hierarchy.py --expand pork            # what excluding it removes
python scripts/check_ingredient_hierarchy.py --require-complete WP2   # acceptance gate
```

`--show` prints how real recipes write the ingredient. Decide from that, not from
the id: `sausage` in these recipes is often pork but not always, and `vanilla`
is sometimes an alcohol-based extract and sometimes a bean.
