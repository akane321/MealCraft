"""Find recipes whose ingredient list misses an allergen the dish names, and record their review.

Some RecipeNLG sources list only part of a dish: a "Crab Meat Quiche" that lists
its crust. Allergens and dietary tags are derived from the listed lines, so such
a recipe is labelled free of what it contains. The release build therefore drops
a recipe whose title or steps name a food carrying an allergen that no listed
ingredient carries, unless a reviewer found the mention harmless:

    python scripts/recipe_completeness.py packet --shards 8   # flagged recipes, for review
    python scripts/recipe_completeness.py sample --size 300   # unflagged recipes, to measure misses
    python scripts/recipe_completeness.py validate FILE...
    python scripts/recipe_completeness.py merge FILE...       # data/enrichment/completeness/v2_review.jsonl
    python scripts/recipe_completeness.py audit               # the owner's sample of the review, fixed seed
    python scripts/recipe_completeness.py record-audit FILE   # record the owner's verdicts

A review line is {"recipe_id", "verdict", "allergens", "evidence", "enriched_by"}:

- `incomplete`: the dish as written needs an unlisted ingredient carrying the
  allergen (crab in a crab quiche, egg for an egg wash). The build drops it.
- `optional_mention`: the text only offers it on the side or as a choice
  ("serve with crusty bread", "top with cheese if you like"). The build keeps it.
- `false_positive`: the word is not that food ("spaghetti squash", "cream the
  sugar", "butterfly the chicken"). The build keeps it.

For a sampled, unflagged recipe the same verdicts apply; `complete` means the
reviewer found nothing missing. A recipe flagged but not reviewed is dropped:
an unexamined exclusion costs one recipe, an unexamined keep could serve an
allergen unchecked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data" / "enrichment" / "completeness" / "v2_review.jsonl"
PACKETS = ROOT / "data" / "review" / "completeness"
# Written by the build: flagged recipes outside release v2 that no review has seen.
QUEUE = PACKETS / "awaiting_review.jsonl"
# Written by the build: every built recipe the check flags, reviewed or not.
FLAGGED_POOL = PACKETS / "flagged_pool.jsonl"
SOURCE = ROOT / "data" / "release" / "v2" / "recipes.jsonl"
KEEP = {"optional_mention", "false_positive", "complete"}
VERDICTS = KEEP | {"incomplete"}
SEED = 20260922
AUDIT_SEED = 20260923
AUDIT = PACKETS / "audit-sample.json"  # redrawable from the seed, so not committed
AUDIT_RESULT = ROOT / "docs" / "completeness-v2.1-sampled-audit.json"  # the owner's judgement, committed
# A wrong keep can serve an allergen unchecked, so the sample leans on kept recipes.
AUDIT_STRATA = {"kept": 25, "incomplete": 10, "sample": 5}

# Phrases rewritten before matching. A phrase keeps the word that carries its
# allergen ("peanut butter" is peanut, not dairy; "almond milk" is tree nut, not
# dairy); a phrase that only looks like a trigger is removed ("cream of tartar",
# "eggplant", "cream the sugar").
REWRITES = [
    (
        re.compile(
            r"\b(peanut|almond|cashew|hazelnut|macadamia|pistachio|walnut|pecan|sesame|soy|soya) "
            r"(?:butter|milk|cream|flour|paste|sauce)\b",
            re.IGNORECASE,
        ),
        r"\1",
    ),
    (
        re.compile(
            r"\b(rice|corn|coconut|tapioca|potato|chickpea|gram|oat|millet|teff|sorghum|buckwheat) "
            r"(?:flour|noodles?|tortillas?|starch|milk|bread|cream)\b",
            re.IGNORECASE,
        ),
        r"\1",
    ),
    (re.compile(r"\bbutter ?beans?\b", re.IGNORECASE), "beans"),
    (re.compile(r"\bimitation crab\w*|\bcrab ?sticks?\b", re.IGNORECASE), "surimi fish"),
    (
        re.compile(
            r"\b(?:cream of tartar|butternut|butterfl\w*|egg ?plants?|nut ?meg|water ?chestnuts?|"
            r"spaghetti squash|cornflour|rice paper|scallop(?:ed)? potato\w*)\b",
            re.IGNORECASE,
        ),
        " ",
    ),
    (re.compile(r"\bcream(?:ed|ing)? (?:together|the|until|in)\b", re.IGNORECASE), " "),
    (re.compile(r"\b(?:gluten|dairy|egg|nut|soy)[- ]free \w+|\bvegan \w+", re.IGNORECASE), " "),
]
# Release allergen name -> words naming a food that carries it. A match is
# answered by any of the listed allergens in the value's second element.
ALLERGEN_WORDS = {
    "crustaceans": (r"crab|shrimps?|prawns?|lobsters?|crawfish|crayfish", {"crustaceans"}),
    "molluscs": (r"scallops?|clams?|mussels?|oysters?|squid|calamari|octopus", {"molluscs"}),
    "fish": (
        r"salmon|tuna|cod|tilapia|anchov\w*|sardines?|halibut|trout|mackerel|catfish|haddock|snapper|fish|worcestershire",
        {"fish"},
    ),
    "eggs": (r"eggs?|yolks?|omelets?|omelettes?|quiche|frittata|meringue|mayo|mayonnaise|aioli", {"eggs"}),
    "milk": (r"cheese|cheddar|parmesan|mozzarella|milk|butter|cream|yogh?urt|ricotta|feta", {"milk"}),
    "peanuts": (r"peanuts?", {"peanuts"}),
    "tree_nuts": (r"almonds?|walnuts?|pecans?|cashews?|pistachios?|hazelnuts?|macadamias?", {"tree_nuts"}),
    "sesame": (r"sesame|tahini", {"sesame"}),
    "soy": (r"soy|soya|tofu|edamame|miso|tempeh", {"soy"}),
    "gluten": (
        r"flour|bread|breadcrumbs?|pasta|spaghetti|macaroni|noodles?|wheat|barley|rye|couscous|crackers?|"
        r"tortillas?|croutons?",
        {"gluten", "gluten_candidate"},
    ),
}
PATTERNS = {
    name: (re.compile(rf"\b(?:{words})\b", re.IGNORECASE), answers) for name, (words, answers) in ALLERGEN_WORDS.items()
}
MEAT = re.compile(
    r"\b(?:chicken|beef|pork|bacon|ham|sausages?|lamb|turkey|meat|steak|veal|duck|gelatin|anchov\w*|fish|"
    r"shrimps?|prawns?|crab|tuna|salmon)\b",
    re.IGNORECASE,
)


def _text(record: dict) -> str:
    steps = [step["text"] if isinstance(step, dict) else str(step) for step in record["instructions"]]
    text = " ".join([record["title"], *steps])
    for pattern, replacement in REWRITES:
        text = pattern.sub(replacement, text)
    return text


def unlisted_allergens(record: dict, listed: set[str]) -> list[str]:
    """Release allergens the title or steps name that no listed ingredient carries."""
    text = _text(record)
    return sorted(
        name for name, (pattern, answers) in PATTERNS.items() if not answers & listed and pattern.search(text)
    )


def matched_words(record: dict, allergen: str) -> list[str]:
    return sorted({m.lower() for m in PATTERNS[allergen][0].findall(_text(record))})


def names_meat(record: dict) -> bool:
    return bool(MEAT.search(_text(record)))


@lru_cache
def reviews() -> dict[str, dict]:
    if not REVIEW.exists():
        return {}
    return {row["recipe_id"]: row for row in map(json.loads, REVIEW.read_text(encoding="utf-8").splitlines()) if row}


def kept_by_review(recipe_id: str) -> bool:
    row = reviews().get(recipe_id)
    return row is not None and row["verdict"] in KEEP


def _records() -> list[dict]:
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    for extra in (QUEUE, FLAGGED_POOL):
        if extra.exists():
            seen = {row["recipe_id"] for row in rows}
            rows += [
                r for r in map(json.loads, extra.read_text(encoding="utf-8").splitlines()) if r["recipe_id"] not in seen
            ]
    return rows


def _packet_line(record: dict, flagged: list[str]) -> dict:
    return {
        "recipe_id": record["recipe_id"],
        "title": record["title"],
        "ingredients": [line["original_text"] for line in record["ingredients"]],
        "instructions": [step["text"] for step in record["instructions"]],
        "flagged": {name: matched_words(record, name) for name in flagged},
    }


def _write(name: str, lines: list[dict], shards: int) -> None:
    PACKETS.mkdir(parents=True, exist_ok=True)
    for shard in range(shards):
        path = PACKETS / f"{name}-{shard + 1}.jsonl"
        path.write_text("".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines[shard::shards]), "utf-8")
    print(f"{len(lines)} recipes in {shards} {name} packets under {PACKETS}")


def _rank(recipe_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{recipe_id}".encode()).hexdigest()


def draw_audit(records: dict[str, dict]) -> None:
    # Only reviews that still decide something: the recipe is flagged by the final check,
    # or it is one of the unflagged sample.
    rows = [r for r in reviews().values() if r["recipe_id"] in records]
    strata = {
        "kept": [
            r for r in rows if r.get("source") != "sample" and r["verdict"] in {"optional_mention", "false_positive"}
        ],
        "incomplete": [r for r in rows if r.get("source") != "sample" and r["verdict"] == "incomplete"],
        "sample": [r for r in rows if r.get("source") == "sample"],
    }
    items = []
    for stratum, want in AUDIT_STRATA.items():
        for row in sorted(strata[stratum], key=lambda r: _rank(r["recipe_id"], AUDIT_SEED))[:want]:
            record = records[row["recipe_id"]]
            items.append(
                {
                    "stratum": stratum,
                    "review": row,
                    "title": record["title"],
                    "ingredients": [
                        line["original_text"] if isinstance(line, dict) else line for line in record["ingredients"]
                    ],
                    "instructions": [
                        step["text"] if isinstance(step, dict) else step for step in record["instructions"]
                    ],
                }
            )
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps({"seed": AUDIT_SEED, "items": items}, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"{len(items)} reviews sampled into {AUDIT}")


def record_audit(path: Path) -> None:
    """Verdicts: {"recipe_id", "verdict": accepted|corrected, "note"}; corrections are applied by hand."""
    sheet = json.loads(AUDIT.read_text(encoding="utf-8"))
    sampled = {item["review"]["recipe_id"]: item["stratum"] for item in sheet["items"]}
    verdicts = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    bad = [
        v for v in verdicts if v.get("recipe_id") not in sampled or v.get("verdict") not in {"accepted", "corrected"}
    ]
    if bad:
        sys.exit(f"verdicts outside the sample or with an unknown verdict: {bad[:3]}")
    by_stratum: dict[str, dict[str, int]] = {}
    for verdict in verdicts:
        counts = by_stratum.setdefault(sampled[verdict["recipe_id"]], {"accepted": 0, "corrected": 0})
        counts[verdict["verdict"]] += 1
    AUDIT_RESULT.write_text(
        json.dumps(
            {
                "seed": sheet["seed"],
                "reviewer": "owner",
                "sampled": len(sampled),
                "verdicts_recorded": len(verdicts),
                "by_stratum": by_stratum,
                "verdicts": sorted(verdicts, key=lambda v: v["recipe_id"]),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(verdicts)} verdicts recorded: {by_stratum}; written to {AUDIT_RESULT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("packet").add_argument("--shards", type=int, default=8)
    sampler = commands.add_parser("sample")
    sampler.add_argument("--size", type=int, default=300)
    sampler.add_argument("--shards", type=int, default=3)
    for name in ("validate", "merge"):
        commands.add_parser(name).add_argument("files", nargs="+")
    commands.add_parser("audit")
    commands.add_parser("record-audit").add_argument("verdicts")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    from build_release_v2 import ingredient_rules  # noqa: PLC0415 - the build's own rule table

    rules = ingredient_rules()

    def listed(record: dict) -> set[str]:
        return {a for line in record["ingredients"] for a in rules[line["canonical_ingredient_id"]]["allergens"]}

    records = _records()
    if args.command == "packet":
        done = reviews()
        lines = []
        for record in records:
            flagged = unlisted_allergens(record, listed(record))
            if flagged and record["recipe_id"] not in done:
                lines.append(_packet_line(record, flagged))
        _write("flagged", lines, args.shards)
        return
    if args.command == "audit":
        flagged_now = {r["recipe_id"] for r in records if unlisted_allergens(r, listed(r))}
        by_id = {r["recipe_id"]: r for r in records}
        live = {
            rid: rec
            for rid, rec in by_id.items()
            if rid in flagged_now or reviews().get(rid, {}).get("source") == "sample"
        }
        draw_audit(live)
        return
    if args.command == "record-audit":
        record_audit(Path(args.verdicts))
        return
    if args.command == "sample":
        pool = [r for r in records if not unlisted_allergens(r, listed(r))]
        pool.sort(key=lambda r: hashlib.sha256(f"{SEED}:{r['recipe_id']}".encode()).hexdigest())
        _write("sample", [_packet_line(r, []) for r in pool[: args.size]], args.shards)
        return

    known = {r["recipe_id"] for r in records}
    rows, problems = [], []
    for file in args.files:
        for number, row in enumerate(map(json.loads, Path(file).read_text(encoding="utf-8").splitlines()), 1):
            issues = []
            if row.get("recipe_id") not in known:
                issues.append("unknown recipe")
            if row.get("verdict") not in VERDICTS:
                issues.append(f"verdict {row.get('verdict')!r}")
            if row.get("verdict") == "incomplete" and not row.get("allergens"):
                issues.append("incomplete without the allergens it misses")
            if not str(row.get("evidence") or "").strip():
                issues.append("no evidence")
            if not str(row.get("enriched_by") or "").strip():
                issues.append("enriched_by missing")
            if issues:
                problems.append(f"{file}:{number} {row.get('recipe_id')}: " + "; ".join(issues))
            rows.append(row)
    print("\n".join(problems) or "all reviews valid")
    if args.command == "validate" or problems:
        sys.exit(1 if problems else 0)
    merged = dict(reviews())
    merged.update({row["recipe_id"]: row for row in rows})
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text("".join(json.dumps(merged[k], ensure_ascii=False) + "\n" for k in sorted(merged)), "utf-8")
    print(f"{len(rows)} merged; {len(merged)} reviews in {REVIEW}")


if __name__ == "__main__":
    main()
