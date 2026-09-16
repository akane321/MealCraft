"""Build a stratified, decision-oriented human-review packet from the curated
output. Emits CSVs under data/review/packet/ - one file per decision category,
each row a single decision with a first-pass proposal and blank columns for the
reviewer to fill in and hand back.

Run:  python scripts/build_review_packet.py
No third-party dependencies. Convert to a single .xlsx separately if wanted.
"""

from __future__ import annotations

import collections
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated" / "recipes.jsonl"
OUT = ROOT / "data" / "review" / "packet"

# Words that appear as recipe section headers, not ingredients.
SECTION_WORDS = {
    "filling", "topping", "sauce", "cake", "dressing", "salad", "frosting",
    "garnish", "glaze", "crust", "batter", "marinade", "ingredients", "directions",
    "for the filling", "for the topping", "for the sauce", "for the cake",
    "for the dressing", "for the crust", "for serving", "to serve", "note", "notes",
    "meat", "produce", "other", "optional", "base", "assembly",
}

ALLERGEN_HINTS = {
    "peanuts": ["peanut"],
    "tree_nuts": ["almond", "walnut", "pecan", "cashew", "pistachio", "hazelnut",
                  "pine nut", "macadamia", "nutella", "praline", "marzipan", "nut "],
    "milk": ["milk", "cream", "cheese", "butter", "yogurt", "yoghurt", "ghee",
             "custard", "whey", "curd", "buttermilk"],
    "eggs": ["egg", "mayonnaise", "mayo", "meringue", "aioli"],
    "soy": ["soy", "tofu", "edamame", "tempeh", "miso"],
    "gluten": ["flour", "wheat", "bread", "pasta", "noodle", "cracker", "barley",
               "rye", "couscous", "semolina", "farro", "bulgur", "crouton", "panko"],
    "fish": ["fish", "salmon", "tuna", "cod", "tilapia", "anchovy", "sardine",
             "haddock", "halibut", "trout", "fish sauce", "worcestershire"],
    "crustaceans": ["shrimp", "prawn", "crab", "lobster", "crayfish", "langoustine"],
    "molluscs": ["clam", "mussel", "oyster", "scallop", "squid", "octopus", "snail"],
    "sesame": ["sesame", "tahini", "za'atar"],
}


def load():
    recs = [json.loads(l) for l in CURATED.open(encoding="utf-8")]
    occ = [(r, i) for r in recs for i in r["ingredients"]]
    return recs, occ


def _write(name: str, header: list[str], rows: list[list]):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name}: {len(rows)} rows")


def propose_for_unmapped(text: str, known_names: set[str]) -> str:
    low = text.lower().strip()
    if low in SECTION_WORDS or re.fullmatch(r"[_\-.:; ]+", low):
        return "SKIP (section header / not an ingredient)"
    if re.search(r"\bsalt\b.*\bpepper\b|\bpepper\b.*\bsalt\b", low):
        return "composite -> salt and pepper"
    if " or " in f" {low} ":
        return "see 02_ambiguous_or"
    if " and " in low:
        return "see 03_composites"
    # ends with a known canonical name (longest trailing group wins)
    words = low.split()
    for start in range(len(words)):
        cand = " ".join(words[start:])
        if cand in known_names:
            return f"alias -> {cand}"
    return "?"


def build():
    recs, occ = load()
    total = len(occ)
    freq = collections.Counter(i["ingredient_text"] for _, i in occ)
    rec_of = collections.defaultdict(set)
    example = {}
    for r, i in occ:
        rec_of[i["ingredient_text"]].add(r["recipe_id"])
        example.setdefault(i["ingredient_text"], i["original_text"])

    known_names = {i["canonical_name"] for _, i in occ
                   if i["normalization_status"] == "mapped" and i["canonical_name"]}

    print(f"curated: {len(recs)} recipes, {total} ingredient occurrences")

    # 1. unmapped high frequency ------------------------------------------
    cand = collections.Counter(
        i["ingredient_text"] for _, i in occ if i["normalization_status"] == "candidate"
    )
    rows = []
    for text, c in cand.most_common(180):
        rows.append([
            text, c, len(rec_of[text]), example[text][:70],
            propose_for_unmapped(text, known_names),
            "", "", "", "",  # decision, canonical_name, food_group, allergens
            "",  # notes
        ])
    _write(
        "01_unmapped_high_freq.csv",
        ["ingredient_text", "occurrences", "recipes", "example_source",
         "PROPOSED", "decision(add/skip/remap)", "canonical_name", "food_group",
         "allergens(;)", "notes"],
        rows,
    )

    # 2. ambiguous "or" -------------------------------------------------
    amb = collections.Counter(
        i["ingredient_text"] for _, i in occ if "ambiguous_alternative" in i["review_reasons"]
    )
    rows = []
    for text, c in amb.most_common(60):
        prop = "keep composite" if re.search(r"\bbutter\b.*\bor\b.*\bmargarine\b|\bmargarine\b.*\bor\b.*\bbutter\b", text) else "?"
        rows.append([text, c, len(rec_of[text]), example[text][:70], prop,
                     "", "", ""])
    _write(
        "02_ambiguous_or.csv",
        ["ingredient_text", "occurrences", "recipes", "example_source", "PROPOSED",
         "decision(composite/pick-first/pick-other/skip)", "canonical_name", "notes"],
        rows,
    )

    # 3. composites "and" ---------------------------------------------
    comp = collections.Counter(
        i["ingredient_text"] for _, i in occ
        if " and " in (i["ingredient_text"] or "") and i["normalization_status"] != "mapped"
    )
    rows = []
    for text, c in comp.most_common(40):
        rows.append([text, c, len(rec_of[text]), example[text][:70],
                     "composite ID or keep unresolved", "", "", ""])
    _write(
        "03_composites.csv",
        ["ingredient_text", "occurrences", "recipes", "example_source", "PROPOSED",
         "decision(composite/decompose/unresolved)", "canonical_name", "notes"],
        rows,
    )

    # 4. safety / allergens -----------------------------------------
    # (a) every mapped ingredient in the sample that carries an allergen label
    seen = {}
    for _, i in occ:
        if i["normalization_status"] == "mapped":
            seen.setdefault(i["canonical_ingredient_id"],
                            (i["canonical_name"], tuple(i["allergens"])))
    a_occ = collections.Counter(
        i["canonical_ingredient_id"] for _, i in occ if i["normalization_status"] == "mapped"
    )
    rows = []
    for iid, (name, alg) in sorted(seen.items(), key=lambda kv: -a_occ[kv[0]]):
        if alg:
            rows.append([name, iid, ";".join(alg), a_occ[iid], "confirm", "", ""])
    # (b) unmapped candidates whose name hints at an allergen
    for text, c in cand.most_common(400):
        hits = sorted({a for a, kws in ALLERGEN_HINTS.items()
                       if any(k in text.lower() for k in kws)})
        if hits:
            rows.append([text, "(unmapped)", "", c,
                         "check: " + ";".join(hits), "", ""])
    _write(
        "04_safety_allergens.csv",
        ["ingredient", "mapped_id", "current_allergens", "occurrences",
         "PROPOSED", "confirmed_allergens(;)", "notes"],
        rows,
    )

    # 5. NER mismatch sample (possible wrong mapping) ----------------
    mm = [(r, i) for r, i in occ
          if i["normalization_status"] == "mapped" and i["source_ner_match"] is False]
    mm.sort(key=lambda ri: ri[1]["ingredient_text"])
    rows = []
    for r, i in mm[:120]:
        rows.append([i["original_text"][:70], i["ingredient_text"],
                     i["canonical_name"], "", "", ""])
    _write(
        "05_ner_mismatch_sample.csv",
        ["example_source", "parsed_name", "mapped_to", "ok?(y/n)",
         "corrected_name", "notes"],
        rows,
    )

    # 6. leftover empty-after-parsing --------------------------------
    eap = [(r, i) for r, i in occ if "empty_after_parsing" in i["review_reasons"]]
    rows = [[i["original_text"][:80], ";".join(i["preparation"])[:60], "", ""]
            for r, i in eap]
    _write(
        "06_empty_after_parsing.csv",
        ["source_line", "extracted_notes", "keep-as?(drop/attach/ingredient)", "notes"],
        rows,
    )

    # 7. reference: every canonical ingredient already known ---------
    # So a reviewer never has to guess "does this already exist" - search this
    # sheet first. Built from config/ingredient_aliases.csv, not from the
    # sample, so it lists every alias the pipeline would already recognise.
    alias_csv = ROOT / "config" / "ingredient_aliases.csv"
    by_id: dict[str, dict] = {}
    with alias_csv.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            iid = row["ingredient_id"]
            entry = by_id.setdefault(iid, {
                "canonical_name": row["canonical_name"],
                "food_group": row["food_group"],
                "allergens": row["allergens"],
                "aliases": [],
            })
            entry["aliases"].append(row["alias"])
    rows = []
    for iid, d in sorted(by_id.items(), key=lambda kv: kv[1]["canonical_name"]):
        rows.append([iid, d["canonical_name"], d["food_group"], d["allergens"],
                     "; ".join(sorted(d["aliases"]))])
    _write(
        "07_reference_canonical_list.csv",
        ["ingredient_id", "canonical_name", "food_group", "allergens",
         "already_covers_these_words"],
        rows,
    )

    # README --------------------------------------------------------
    (OUT / "00_README.txt").write_text(
        "MealCraft data review packet\n"
        "===========================\n\n"
        f"Generated from data/curated/recipes.jsonl ({len(recs)} recipes, {total} "
        "ingredient occurrences) and config/ingredient_aliases.csv "
        f"({len(by_id)} canonical ingredients already known).\n\n"
        "Fill the blank columns and send the packet back. Column PROPOSED is a\n"
        "first-pass guess - override it freely.\n\n"
        "How to decide 'is this a new ingredient' (sheet 01/02/03):\n"
        "  1. Search 07_reference_canonical_list for the word (canonical_name\n"
        "     AND already_covers_these_words - an item may already be covered\n"
        "     under a different spelling, e.g. 'pecans' is under 'pecan').\n"
        "  2. Found a clear match          -> decision = remap, canonical_name = that row's name.\n"
        "  3. Found something related but a genuinely different food\n"
        "     (e.g. 'blue cheese' vs 'cheddar cheese') -> decision = add, it is new.\n"
        "  4. Nothing close, and it names a real ingredient -> decision = add.\n"
        "  5. Not a food at all (section header, brand alone, junk) -> decision = skip.\n"
        "  When in doubt, or the item might be an allergen, leave notes and we will\n"
        "  discuss it rather than guessing.\n\n"
        "01_unmapped_high_freq  - top 180 unmapped ingredient phrases by frequency.\n"
        "  decision = add  -> also fill canonical_name / food_group / allergens\n"
        "  decision = skip -> section header / junk, will be dropped\n"
        "  decision = remap-> fill canonical_name of an existing ingredient (see 07)\n\n"
        "02_ambiguous_or        - 'X or Y' phrases. Choose composite / pick one / skip.\n"
        "03_composites          - 'X and Y' phrases. Composite ID / decompose / leave unresolved.\n"
        "04_safety_allergens    - SAFETY CRITICAL. Two reviewers recommended.\n"
        "  confirm rows = existing labels; check rows = unmapped names that look allergenic.\n"
        "05_ner_mismatch_sample - mapped rows where the source NER disagrees; spot wrong maps.\n"
        "06_empty_after_parsing - lines that parsed to nothing; confirm drop vs attach.\n"
        "07_reference_canonical_list - every ingredient already in config/ingredient_aliases.csv.\n"
        "  Search this FIRST before marking anything 'add' in sheets 01-03.\n",
        encoding="utf-8",
    )
    print(f"\npacket written to {OUT}")


if __name__ == "__main__":
    build()
