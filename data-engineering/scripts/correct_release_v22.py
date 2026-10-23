"""Release v2.2: release v2.1 with its whole-item and container unit weights corrected (owner, 2026-10-23).

    python scripts/correct_release_v22.py        # reads data/release/v2.1/, writes data/release/v2.2/

Why a correction step and not a rebuild: `build_release_v2.py` reads `data/staging/` (the enrichment set and
the merged enrichment results), which is git-ignored and exists only on one machine, so v2.1 cannot be rebuilt
from the repository. This step reads only the committed v2.1 files, rewrites the grams of the lines below, and
recomputes each changed recipe's per-serving nutrition from the same ingredient nutrition the build used (the
`nutrition_per_100g` of the line's form in `ingredients.jsonl`). Every other byte of a recipe stays as v2.1
wrote it. v2.1 itself is never touched.

A corrected weight comes only from the line's own text, the same ingredient entry's own units, or a cited public
reference (`SOURCES`). The classes, applied to each line in this order:

1. `red_pepper_alias`: "red pepper" was aliased to cayenne. A line that is fresh pepper (counted, measured in
   cups, or chopped/diced/sliced/seeded/cut) moves to bell pepper and is weighed with bell pepper's own units.
   A count whose text names a spoon measure (typos included: "1/4 tespoon") is not a counted pepper. Flakes, crushed, ground, dried, powder and a bare "1 tsp. red pepper" stay cayenne.
2. `stated_weight`: a counted line whose text states a mass the build's package pattern missed (mixed numbers,
   fractions, ranges, "about 2 lb", no parentheses). One item: the mass is the item's. Several items: only with
   "each", "total", or the mass in parentheses right after the count ("2 (1 1/2 pound) pork tenderloins");
   otherwise it is ambiguous and left. A line offering an alternative (" or ") is left.
3. `n_times_total`: the build multiplied the count by a parenthetical mass that is the total ("20 shrimp (8 oz.)"
   = 4,536 g). When the parentheses do not follow the count directly, carry no "each" and name no container,
   the mass is the line's total.
4. `whole_bird`: "1 whole chicken" / "1 fryer, cut up" with no stated mass, weighed as one 100 g piece. One
   chicken's edible meat and skin (the entry's own basis, bones excluded) is USDA FDC 171447's "0.5 chicken,
   bone removed" = 460 g, twice. A bird with a stated mass is class 2 and keeps that bone-in market mass: the
   mixed basis is listed as open in the quality report.
5. `whole_head`: a whole cabbage, cauliflower, lettuce or broccoli weighed as one leaf or floret (the same
   lines and test as `backend/app/planning/vegetable_led.py` `whole_grams`), at the entry's own `head` weight.
   A whole fresh pineapple weighed as one canned chunk (14 g) takes USDA FDC 169124's "1 fruit" = 905 g.
6. `pizza_crust`: a whole pizza crust or dough weighed as one slice (43 g) takes the entry's own `loaf` weight,
   "one whole 12-inch prebaked crust" = 340 g.
7. `lasagna_sheet`: a dry lasagna noodle weighed as one spaghetti strand (1 g) takes 18 g, FDC 2495617's
   label serving "3 pieces" = 54 g.

Guards (warnings in the quality report, never silent changes): an entry whose piece weight is under 30% of its
own head or loaf weight; a counted line whose parenthetical mass times its count is over 3 kg; a recipe whose
corrected energy is outside the build's plausible range.
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_release_v2 import ENERGY_PER_SERVING, NUTRIENTS, PACKAGE, PACKAGE_UNIT, grams  # noqa: E402

SOURCE = ROOT / "data" / "release" / "v2.1"
TARGET = ROOT / "data" / "release" / "v2.2"
VERSION = "v2.2"
CREATED_AT = "2026-10-23T00:00:00+00:00"  # fixed, so a rerun writes the same bytes

# The food-details pages render in the browser; the record JSON behind each (portal-data/external/<id>) shows the
# cited row as text (foodMeasures for SR Legacy, servingSize/householdServingFullText for branded).
SOURCES = {
    "whole_bird": "USDA FoodData Central 171447, Chicken, broilers or fryers, meat and skin, raw: portion "
    "'0.5 chicken, bone removed' = 460 g (https://fdc.nal.usda.gov/food-details/171447/nutrients; "
    "record https://fdc.nal.usda.gov/portal-data/external/171447)",
    "whole_pineapple": "USDA FoodData Central 169124, Pineapple, raw, all varieties: portion '1 fruit' = 905 g "
    "(https://fdc.nal.usda.gov/food-details/169124/nutrients; record https://fdc.nal.usda.gov/portal-data/external/169124)",
    "lasagna_sheet": "USDA FoodData Central 2495617 (branded), LASAGNA SEMOLINA, Flora's Distributors: serving "
    "54 g = '3 pieces' (https://fdc.nal.usda.gov/food-details/2495617/nutrients; "
    "record https://fdc.nal.usda.gov/portal-data/external/2495617)",
}
WHOLE_CHICKEN_G = 920.0
WHOLE_PINEAPPLE_G = 905.0
LASAGNA_SHEET_G = 18.0
GUARD_PIECE_SHARE = 0.3
GUARD_TOTAL_G = 3000.0

COUNT_UNITS = {
    "piece", "head", "loaf", "slice", "can", "package", "bag", "jar", "box", "bottle", "packet", "container",
    "envelope", "stalk", "ear", "rib", "stick", "square",
}  # fmt: skip
NUM = r"(\d+[\s-]+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
MASS_UNIT = {"lb": 453.592, "pound": 453.592, "oz": 28.3495, "ounce": 28.3495, "kg": 1000.0, "g": 1.0, "gram": 1.0}
MASS = re.compile(
    rf"{NUM}(?:\s*(?:-|–|to)\s*{NUM})?[\s-]*(lbs?|pounds?|oz|ounces?|kg|kilograms?|grams?|g)\.?(?![a-z])", re.I
)
LEADING_PAREN_MASS = re.compile(rf"^\s*{NUM}\s*\(\s*(?:about\s+)?{NUM}", re.I)
CONTAINER = re.compile(r"\b(cans?|jars?|bags?|packages?|pkgs?|boxe?s?|bottles?|cartons?|containers?|tins?)\b", re.I)
# A container counted as the item ("1 small can mushrooms", "1 large bag spinach").
COUNTED_CONTAINER = re.compile(rf"^\s*{NUM}\s+(?:\w+\s+)?(?:cans?|jars?|bags?|boxe?s?|packages?|pkgs?)\b", re.I)
ALTERNATIVE = re.compile(r"\bor\b", re.I)

RED_PEPPER = re.compile(r"\bred\s+peppers?\b", re.I)
NOT_FRESH = re.compile(r"cayenne|flake|crushed|ground|dried|powder|hot|chil|paprika", re.I)
FRESH_PREP = re.compile(r"chop|dice|slic|minc|strip|seed|julienn|chunk|\bcut\b", re.I)
# A spice measure, typos included ("1/4 tespoon of red pepper" parses as unit `piece`): not a counted pepper.
SPICE_MEASURE = re.compile(r"spoon|\bt[be]?sp|\btbl", re.I)

# The same whole-vegetable test as backend/app/planning/vegetable_led.py (`WHOLE`, `PARTS`, `COUNT`).
WHOLE_HEADS = {"ING_CABBAGE", "ING_CAULIFLOWER", "ING_LETTUCE", "ING_BROCCOLI"}
PARTS = re.compile(r"\b(?:leaf|leaves|florets?|spears?|hearts?|handfuls?|pieces?)(?![a-z])", re.I)
WHOLE_PINEAPPLE = re.compile(rf"^\s*{NUM}\s+(?:(?:large|small|medium|fresh|whole|ripe|none)\s+)*pineapples?\b", re.I)
WHOLE_BIRD = re.compile(r"\b(?:whole|fryers?|broilers?|roasters?|roasting|stewing|chickens|hens?)\b|\bchicken\b", re.I)
BIRD_PARTS = re.compile(
    r"breast|thigh|\blegs?\b|wing|drumstick|tender|fillet|cutlet|liver|giblet|gizzard|feet|neck|\bbacks?\b"
    r"|strip|nugget|boneless|cooked|\bmeat\b|cube|pieces? of|broth|stock|bouillon|patt",
    re.I,
)
# Words that make the counted noun a part, not the whole item ("8 pieces chicken", "2 pineapple slices").
COUNTED_PART = re.compile(r"\b(?:pieces?|quarters|halves|slices?|rings?|chunks?|tidbits?|wedges?)\b", re.I)
SIZE_PAREN = re.compile(rf"^\s*{NUM}\s+(?:small|medium|large|big)\s*\(", re.I)
COMPOUND_MASS = re.compile(r"(?:lbs?|pounds?)\.?,?\s*(?:and\s+)?\d+(?:\s+\d+/\d+|/\d+)?\s*(?:oz|ounces?)\b", re.I)


def number(text: str) -> float:
    text = text.strip()
    if "/" in text:
        parts = re.split(r"[\s-]+", text)
        whole = float(parts[0]) if len(parts) == 2 else 0.0
        numerator, denominator = parts[-1].split("/")
        return whole + float(numerator) / float(denominator)
    return float(text)


def mass_grams(match: re.Match) -> float:
    low, high, unit = match.group(1), match.group(2), match.group(3).lower().rstrip("s")
    value = number(low) if high is None else (number(low) + number(high)) / 2
    unit = {"kilogram": "kg", "lb": "lb"}.get(unit, unit)
    return value * MASS_UNIT[unit]


def quantity(line: dict) -> float | None:
    low, high = line["quantity_min"], line["quantity_max"]
    if low is None:
        return None
    return (low + high) / 2 if high is not None else low


def stated_mass(line: dict) -> float | None:
    """The line's grams from a mass its own text states, or None when there is none or it is ambiguous."""
    text, count = line["original_text"], quantity(line)
    if not count or line["unit"] not in COUNT_UNITS or ALTERNATIVE.search(text) or COMPOUND_MASS.search(text):
        return None
    found = list(MASS.finditer(text))
    if not found:
        return None
    if count == 1 and line["quantity_max"] in (None, 1):
        return mass_grams(found[0])
    for match in found:
        after = text[match.end() : match.end() + 12].lower()
        if "total" in after:
            return mass_grams(match)
    for match in found:
        if "each" in text[match.end() : match.end() + 12].lower():
            return count * mass_grams(match)
    # "8 (1 1/4 lb) chicken thighs" reads as each but is a total: over the guard it is left, not multiplied.
    if LEADING_PAREN_MASS.match(text) and found[0].start() < text.find(")"):
        each = count * mass_grams(found[0])
        return each if each <= GUARD_TOTAL_G else None
    return None


def n_times_total(line: dict) -> float | None:
    """A parenthetical total the build multiplied by the count ("20 shrimp (8 oz.)"), as that total."""
    text, count = line["original_text"], quantity(line)
    if line["grams_basis"] != "stated_package" or not count or count <= 1:
        return None
    package = PACKAGE.search(text)
    if package is None or LEADING_PAREN_MASS.match(text) or SIZE_PAREN.match(text) or "each" in text.lower():
        return None
    unit = PACKAGE_UNIT[package.group(2).lower()]
    if unit not in MASS_UNIT or ALTERNATIVE.search(text) or CONTAINER.search(text[: package.start()]):
        return None
    return float(package.group(1)) * MASS_UNIT[unit]


def is_fresh_red_pepper(line: dict) -> bool:
    text = line["original_text"]
    if line["canonical_ingredient_id"] != "ING_CAYENNE" or not RED_PEPPER.search(text) or NOT_FRESH.search(text):
        return False
    counted = line["unit"] in {"piece", "cup"} and not SPICE_MEASURE.search(text)
    return counted or bool(FRESH_PREP.search(text))


def counted_noun(text: str) -> str:
    """The words before the first comma or parenthesis: what is counted ("1 head cauliflower, cut into florets")."""
    return re.split(r"[,(]", text, maxsplit=1)[0]


def form_key(line: dict) -> str:
    cid = line["canonical_ingredient_id"]
    return f"{cid}#cooked" if "cooked" in (line.get("preparation") or []) else cid


def counted_as(line: dict, weights: dict[str, float], unit: str) -> bool:
    """Whether the line's grams are exactly its count times the entry's `unit` weight."""
    count = quantity(line)
    return bool(count) and unit in weights and abs(line["grams"] - round(count * weights[unit], 1)) <= 0.05


def correct_line(line: dict, forms: dict[str, dict]) -> tuple[dict, str, str] | None:
    """(the corrected line, its class, its source) or None when the line is left as v2.1 has it."""
    new = dict(line)
    classes = []
    if is_fresh_red_pepper(line):
        new["canonical_ingredient_id"] = "ING_BELL_PEPPER"
        if form_key(new) not in forms:
            return None
        weights = {u["unit"]: u["grams"] for u in forms[form_key(new)]["unit_grams"]}
        weighed = grams(quantity(new) or 0, new["unit"] or "", weights) if quantity(new) else None
        if weighed is None:
            return None
        new["grams"] = round(weighed, 1)
        classes.append(("red_pepper_alias", "ingredient entry ING_BELL_PEPPER unit_grams"))
    cid, text = new["canonical_ingredient_id"], new["original_text"]
    weights = {u["unit"]: u["grams"] for u in forms[form_key(new)]["unit_grams"]}
    count = quantity(new)
    if (mass := stated_mass(new)) is not None and new["grams_basis"] == "stated":
        new["grams"] = round(mass, 1)
        classes.append(("stated_weight", "the line's own text"))
    elif (total := n_times_total(new)) is not None:
        new["grams"] = round(total, 1)
        classes.append(("n_times_total", "the line's own text"))
    elif MASS.search(text) or ALTERNATIVE.search(text) or COUNTED_PART.search(counted_noun(text)):
        pass  # a mass the rules above could not place, an alternative, or a counted part: left as v2.1 has it
    elif cid == "ING_CHICKEN" and form_key(new) == cid and new["unit"] == "piece" and counted_as(new, weights, "piece"):
        if WHOLE_BIRD.search(text) and not BIRD_PARTS.search(text):
            new["grams"] = round(count * WHOLE_CHICKEN_G, 1)
            classes.append(("whole_bird", SOURCES["whole_bird"]))
    elif cid in WHOLE_HEADS and new["unit"] == "piece" and not PARTS.search(counted_noun(text)):
        if counted_as(new, weights, "piece") and "head" in weights:
            new["grams"] = round(count * weights["head"], 1)
            classes.append(("whole_head", f"ingredient entry {cid} unit_grams head"))
    elif cid == "ING_PINEAPPLE" and new["unit"] == "piece" and WHOLE_PINEAPPLE.match(text):
        if counted_as(new, weights, "piece") and not CONTAINER.search(text):
            new["grams"] = round(count * WHOLE_PINEAPPLE_G, 1)
            classes.append(("whole_head", SOURCES["whole_pineapple"]))
    elif cid == "ING_PIZZA_CRUST" and new["unit"] == "piece" and "slice" not in text.lower():
        if counted_as(new, weights, "piece"):
            new["grams"] = round(count * weights["loaf"], 1)
            classes.append(("pizza_crust", "ingredient entry ING_PIZZA_CRUST unit_grams loaf"))
    elif cid == "ING_PASTA" and form_key(new) == cid and new["unit"] == "piece" and re.search(r"lasagn", text, re.I):
        if counted_as(new, weights, "piece"):
            new["grams"] = round(count * LASAGNA_SHEET_G, 1)
            classes.append(("lasagna_sheet", SOURCES["lasagna_sheet"]))
    if not classes or (
        new["grams"] == line["grams"] and new["canonical_ingredient_id"] == line["canonical_ingredient_id"]
    ):
        return None
    new["grams_correction"] = "+".join(name for name, _ in classes)
    return new, new["grams_correction"], "; ".join(source for _, source in classes)


def contribution(line: dict, forms: dict[str, dict]) -> dict[str, float]:
    eaten = line.get("grams_consumed", line["grams"])
    per_100 = forms[form_key(line)]["nutrition_per_100g"]
    return {k: eaten * per_100[k] / 100 for k in NUTRIENTS}


def correct_recipe(recipe: dict, forms: dict[str, dict], entries: dict[str, dict]) -> tuple[dict, list[dict]]:
    """The recipe with its lines corrected and nutrition recomputed, and one record per changed line."""
    changes, lines = [], []
    delta = dict.fromkeys(NUTRIENTS, 0.0)
    for index, line in enumerate(recipe["ingredients"], 1):
        corrected = None if "grams_consumed" in line else correct_line(line, forms)
        if corrected is None:
            lines.append(line)
            continue
        new, name, source = corrected
        entry = entries[new["canonical_ingredient_id"]]
        new["canonical_name"] = entry["canonical_name"]
        new["allergens"] = entry["allergens"]
        before, after = contribution(line, forms), contribution(new, forms)
        for k in NUTRIENTS:
            delta[k] += after[k] - before[k]
        lines.append(new)
        changes.append(
            {
                "recipe_id": recipe["recipe_id"],
                "line": index,
                "class": name,
                "original_text": line["original_text"],
                "v2_1": {"canonical_ingredient_id": line["canonical_ingredient_id"], "grams": line["grams"]},
                "v2_2": {"canonical_ingredient_id": new["canonical_ingredient_id"], "grams": new["grams"]},
                "source": source,
            }
        )
    if not changes:
        return recipe, []
    out = dict(recipe)
    out["ingredients"] = lines
    nutrition = dict(recipe["nutrition"])
    for k in NUTRIENTS:
        nutrition[k] = round(max(nutrition[k] + delta[k] / recipe["servings"], 0.0), 1)
    out["nutrition"] = nutrition
    assert sorted({a for line in lines for a in line["allergens"]}) == recipe["allergens"], recipe["recipe_id"]
    return out, changes


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guards(recipes: list[dict], entries: dict[str, dict]) -> dict[str, list]:
    piece_entries = []
    for _, entry in sorted(entries.items()):
        for key, form in sorted(entry["forms"].items()):
            weights = {u["unit"]: u["grams"] for u in form["unit_grams"]}
            whole = {u: weights[u] for u in ("head", "loaf", "whole") if u in weights}
            if "piece" in weights and any(weights["piece"] < GUARD_PIECE_SHARE * w for w in whole.values()):
                piece_entries.append({"form": key, "piece": weights["piece"], **whole})
    totals, energy = [], []
    for recipe in recipes:
        for line in recipe["ingredients"]:
            count = quantity(line)
            if line["grams_basis"] == "stated_package" and count and count > 1 and line["grams"] > GUARD_TOTAL_G:
                totals.append({"recipe_id": recipe["recipe_id"], "text": line["original_text"], "grams": line["grams"]})
        kcal = recipe["nutrition"]["energy_kcal"]
        if not ENERGY_PER_SERVING[0] <= kcal <= ENERGY_PER_SERVING[1]:
            energy.append({"recipe_id": recipe["recipe_id"], "title": recipe["title"], "energy_kcal": kcal})
    return {"piece_under_30pct_of_whole": piece_entries, "n_times_total_over_3kg": totals, "energy": energy}


CONTAINER_OPEN = (
    "container counted as one piece, not re-weighed (a canned-only entry already weighs one can; "
    "the rest need a cited can weight)"
)


def open_items(recipes: list[dict]) -> dict[str, int]:
    """Lines of the corrected classes that this round leaves, by reason (counted on v2.2)."""
    counts = collections.Counter()
    for recipe in recipes:
        for line in recipe["ingredients"]:
            text, cid = line["original_text"], line["canonical_ingredient_id"]
            if "grams_correction" in line:
                continue
            if line["unit"] in COUNT_UNITS and line["grams_basis"] == "stated" and MASS.search(text):
                counts["stated mass left (several items, no each/total, or an alternative)"] += 1
            if line["unit"] == "piece" and COUNTED_CONTAINER.match(text) and not MASS.search(text):
                counts[CONTAINER_OPEN] += 1
            if cid == "ING_CAYENNE" and RED_PEPPER.search(text) and not NOT_FRESH.search(text):
                counts["bare 'red pepper' by teaspoon/tablespoon, kept cayenne"] += 1
            if cid in {"ING_PORK", "ING_BEEF", "ING_LAMB", "ING_HAM"} and line["unit"] == "piece":
                if re.search(r"roast|brisket|shoulder|tenderloin|loin|leg|butt", text, re.I):
                    counts["large cut with no stated mass"] += 1
            if cid == "ING_PASTA" and re.search(r"lasagn", text, re.I) and form_key(line) != cid:
                counts["cooked lasagna noodle"] += 1
    return dict(counts.most_common())


def report_section(changes: list[dict], guard: dict, left: dict, before: dict, after: dict) -> str:
    by_class = collections.Counter(c["class"] for c in changes)
    recipes_by_class = collections.defaultdict(set)
    for c in changes:
        recipes_by_class[c["class"]].add(c["recipe_id"])
    rows = "\n".join(f"| `{k}` | {v} | {len(recipes_by_class[k])} |" for k, v in sorted(by_class.items()))
    sources = "\n".join(f"- `{k}`: {v}" for k, v in SOURCES.items())
    guard_entries = "\n".join(
        f"| `{g['form']}` | {g['piece']} | {', '.join(f'{u} {g[u]}' for u in ('head', 'loaf', 'whole') if u in g)} |"
        for g in guard["piece_under_30pct_of_whole"]
    )
    totals = "\n".join(f"- `{t['recipe_id']}` {t['text']!r}: {t['grams']} g" for t in guard["n_times_total_over_3kg"])
    energy = "\n".join(f"- `{e['recipe_id']}` {e['title']}: {e['energy_kcal']} kcal" for e in guard["energy"])
    opened = "\n".join(f"| {k} | {v} |" for k, v in left.items())
    digests = "\n".join(f"| `{name}` | `{before[name][:16]}` | `{after[name][:16]}` |" for name in sorted(after))
    return f"""
## Unit-weight corrections (v2.2, owner 2026-10-23)

v2.2 is v2.1 with the lines below re-weighed by `scripts/correct_release_v22.py`; the recipe set, ids and every
other field are unchanged. v2.1 cannot be rebuilt from the repository (`data/staging/` is git-ignored), so the
step corrects v2.1's committed lines and recomputes each changed recipe's per-serving nutrition from the same
`nutrition_per_100g` the build used. Every changed line is in `corrections.jsonl` with its v2.1 and v2.2 grams
and its source. Size words (small, medium, large) are not part of this round.

| Class | Lines | Recipes |
| --- | ---: | ---: |
{rows}

{len(changes)} lines in {len({c["recipe_id"] for c in changes})} recipes changed.

Sources beyond the line's own text and the entry's own units:

{sources}

### Left open in this round

| Reason | Lines |
| --- | ---: |
{opened}

Open question, mixed gram basis: a `whole_bird` line with no stated mass takes 920 g of edible meat and skin
(bones excluded, the entry's own basis), but a `stated_weight` line keeps the stated market weight, which for a
bird, a bone-in roast or shoulder, a lobster or a whole pineapple ("1 (4 lb) pineapple" = 1,814 g against the
905 g edible fruit) includes bone, shell or rind. Those recipes' per-serving nutrition and cost-per-gram basis
are therefore high. The owner's rule is stated weight first; an edible-yield factor needs a cited yield per food
and is not applied in this round.

### Guard: piece weight under 30% of the entry's own head or loaf weight

| Form | Piece g | Whole g |
| --- | ---: | --- |
{guard_entries}

### Guard: counted lines whose parenthetical mass times the count is over 3 kg

{totals or "- none"}

### Guard: per-serving energy outside {ENERGY_PER_SERVING[0]}-{ENERGY_PER_SERVING[1]} kcal

{energy or "- none"}

### Files

| File | v2.1 sha256 | v2.2 sha256 |
| --- | --- | --- |
{digests}
"""


def main() -> int:
    entries = {row["ingredient_id"]: row for row in read_jsonl(SOURCE / "ingredients.jsonl")}
    forms = {key: form for row in entries.values() for key, form in row["forms"].items()}
    recipes, changes = [], []
    for recipe in read_jsonl(SOURCE / "recipes.jsonl"):
        corrected, changed = correct_recipe(recipe, forms, entries)
        recipes.append(corrected)
        changes += changed
    TARGET.mkdir(parents=True, exist_ok=True)
    with (TARGET / "recipes.jsonl").open("w", encoding="utf-8", newline="\n") as out:
        for recipe in recipes:
            out.write(json.dumps(recipe, ensure_ascii=False, sort_keys=True) + "\n")
    used = collections.Counter(line["canonical_ingredient_id"] for r in recipes for line in r["ingredients"])
    with (TARGET / "ingredients.jsonl").open("w", encoding="utf-8", newline="\n") as out:
        for cid in sorted(entries):
            if used[cid]:
                out.write(
                    json.dumps({**entries[cid], "recipe_occurrences": used[cid]}, ensure_ascii=False, sort_keys=True)
                    + "\n"
                )
    with (TARGET / "corrections.jsonl").open("w", encoding="utf-8", newline="\n") as out:
        for change in changes:
            out.write(json.dumps(change, ensure_ascii=False, sort_keys=True) + "\n")
    for name in ("dropped.jsonl", "ATTRIBUTION.md"):
        shutil.copyfile(SOURCE / name, TARGET / name)

    by_class = dict(sorted(collections.Counter(c["class"] for c in changes).items()))
    manifest = json.loads((SOURCE / "release_manifest.json").read_text(encoding="utf-8"))
    manifest.update(release_version=VERSION, created_at=CREATED_AT)
    manifest["derived_from"] = {
        "release_version": "v2.1",
        "step": "scripts/correct_release_v22.py",
        "decision": "owner 2026-10-23: unit-weight corrections",
        "corrected_lines": len(changes),
        "corrected_recipes": len({c["recipe_id"] for c in changes}),
        "corrected_lines_by_class": by_class,
        "v2_1_sha256": {n: sha256(SOURCE / n) for n in ("recipes.jsonl", "ingredients.jsonl")},
    }
    (TARGET / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    summary = json.loads((SOURCE / "quality_summary.json").read_text(encoding="utf-8"))
    summary.update(release_version=VERSION, created_at=CREATED_AT)
    summary["nutrition_per_serving"]["median_energy_kcal"] = sorted(r["nutrition"]["energy_kcal"] for r in recipes)[
        len(recipes) // 2
    ]
    summary["unit_weight_corrections"] = by_class
    (TARGET / "quality_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    names = ("recipes.jsonl", "ingredients.jsonl", "release_manifest.json")
    before = {n: sha256(SOURCE / n) for n in names}
    after = {n: sha256(TARGET / n) for n in names}
    report = (SOURCE / "quality_report.md").read_text(encoding="utf-8")
    report = report.replace("# Release v2.1 quality report", "# Release v2.2 quality report", 1)
    report = report.replace(
        "Generated by `scripts/v2_release_report.py` from the build outputs in\n`data/release/v2.1/`.",
        "Sections above the v2.2 section are v2.1's, generated by `scripts/v2_release_report.py` from the build "
        "outputs in\n`data/release/v2.1/`; the v2.2 section is written by `scripts/correct_release_v22.py`.",
        1,
    )
    guard = guards(recipes, entries)
    report += report_section(changes, guard, open_items(recipes), before, after)
    (TARGET / "quality_report.md").write_text(report, encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {"corrected_lines": len(changes), "by_class": by_class, "guards": {k: len(v) for k, v in guard.items()}}
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
