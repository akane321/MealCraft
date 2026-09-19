"""Turn the v2 candidates into the enrichment set and its work-packet items.

    python scripts/prepare_v2_inputs.py select        # apply stage-3 decisions, pick the enrichment set
    python scripts/prepare_v2_inputs.py recipes       # recipe items for the packets
    python scripts/prepare_v2_inputs.py ingredients   # ingredient items for the packets

`select` resolves every unmapped ingredient line through
config/ingredient_aliases_v2_additions.csv. A candidate with a line that is
dropped or still undecided is not used. The rest are picked by quota at
ENRICH_FACTOR x target, so the final release can still meet each quota after
enrichment relabels cuisines. Output: data/staging/v2_enrich_set.jsonl.

`recipes` and `ingredients` write data/staging/v2_<kind>_items.jsonl; then
`v2_packet.py build-inputs` splits them into parts A, B and C.
"""

from __future__ import annotations

import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v2_candidates import QUOTAS, select  # noqa: E402
from v2_vocab import ADDITIONS, existing, resolver  # noqa: E402

STAGING = ROOT / "data" / "staging"
CANDIDATES = STAGING / "v2_candidates.jsonl"
ENRICH_SET = STAGING / "v2_enrich_set.jsonl"
CORRECTIONS = ROOT / "config" / "ingredient_alias_corrections_v2.json"
ENRICH_FACTOR = 1.2
QUANTIFIED = {"mass", "volume", "count"}
MASS_UNITS = {"g", "kg", "oz", "lb", "mg"}
COUNT_ALIASES = {"dozen": "piece"}

DURATION = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*(?:to|-|–|or)\s*(\d+(?:\.\d+)?))?\s*(minutes?|mins?|hours?|hrs?)\b", re.IGNORECASE
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, items: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(i, ensure_ascii=False, sort_keys=True) + "\n" for i in items), encoding="utf-8", newline="\n"
    )


def needs_amount(line: dict) -> bool:
    return line.get("quantity_min") is None or line.get("unit_dimension") not in QUANTIFIED


def form_key(line: dict) -> str:
    """Enrichment key of an ingredient line: `<id>`, or `<id>#cooked` when the recipe says cooked."""
    cid = line["canonical_ingredient_id"]
    return f"{cid}#cooked" if "cooked" in (line.get("preparation") or []) else cid


# ------------------------------------------------------------------------------ select
def select_enrichment_set() -> None:
    resolve = resolver()
    corrections = {
        name: spec["ingredient_id"]
        for name, spec in json.loads(CORRECTIONS.read_text(encoding="utf-8")).items()
        if not name.startswith("_")
    }
    usable, reasons = [], collections.Counter()
    for record in read_jsonl(CANDIDATES):
        ok = True
        for line in record["ingredients"]:
            corrected = corrections.get((line.get("ingredient_text") or "").strip())
            if line["normalization_status"] == "mapped" and corrected:
                line["normalization_status"] = "corrected"
            if line["normalization_status"] == "mapped":
                continue
            if line["normalization_status"] == "corrected":
                decision = resolve(corrected, by_id=True)
                if decision is None:
                    raise SystemExit(f"correction target {corrected} is not a stage-3 ingredient")
                line["canonical_ingredient_id"], line["canonical_name"], allergens, status = decision
                line["allergens"] = [a for a in allergens.replace(";", "|").split("|") if a]
                line["allergen_status"] = status
                line["normalization_status"] = "mapped"
                line["mapping_basis"] = "v2_correction"
                continue
            decision = resolve(line["ingredient_text"])
            if decision is None or decision == "drop":
                reasons["dropped name" if decision == "drop" else "undecided name"] += 1
                ok = False
                break
            line["canonical_ingredient_id"], line["canonical_name"], allergens, status = decision
            line["allergens"] = [a for a in allergens.replace(";", "|").split("|") if a]
            line["allergen_status"] = status
            line["normalization_status"] = "mapped"
            line["mapping_basis"] = "v2_additions"
        if ok:
            usable.append(record)
    chosen = select(usable, factor=ENRICH_FACTOR)
    write_jsonl(ENRICH_SET, chosen)
    by_bucket = collections.Counter(r["quota_bucket"] for r in chosen)
    print(f"usable {len(usable)} of candidates; excluded: {dict(reasons)}")
    print(f"enrichment set {len(chosen)} -> {ENRICH_SET.relative_to(ROOT)}")
    for bucket, spec in QUOTAS["buckets"].items():
        flag = "" if by_bucket[bucket] >= spec["target"] else "  <- below target"
        print(f"  {bucket:<24} {by_bucket[bucket]:>5} / target {spec['target']}{flag}")
    print("  courses:", dict(collections.Counter(r["triage"]["course"] for r in chosen).most_common()))


# ------------------------------------------------------------------------------ recipes
def stated_durations(steps: list[dict]) -> list[str]:
    return [
        f"step {step['step_number']}: {match.group(0)}" for step in steps for match in DURATION.finditer(step["text"])
    ]


def recipes() -> list[dict]:
    return [
        {
            "candidate_id": record["candidate_id"],
            "title": record["title"],
            "servings": record["servings"],
            "ingredients": [
                {"index": index, "text": line["original_text"], "needs_amount": needs_amount(line)}
                for index, line in enumerate(record["ingredients"], 1)
            ],
            "steps": [f"{s['step_number']}. {s['text']}" for s in record["instructions"]],
            "stated_durations": stated_durations(record["instructions"]),
            "cuisine_hint": record["triage"]["cuisine"],
        }
        for record in read_jsonl(ENRICH_SET)
    ]


# --------------------------------------------------------------------------- ingredients
def catalog() -> dict[str, dict]:
    """canonical id -> name, food group and aliases, from the alias table plus stage-3 additions."""
    table = {
        i: {"canonical_name": r["canonical_name"], "food_group": r["food_group"], "aliases": set()}
        for i, r in existing().items()
    }
    with (ROOT / "config" / "ingredient_aliases.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            table[row["ingredient_id"]]["aliases"].add(row["alias"])
    if ADDITIONS.exists():
        with ADDITIONS.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row["action"] == "new":
                table.setdefault(
                    row["ingredient_id"],
                    {"canonical_name": row["canonical_name"], "food_group": row["food_group"], "aliases": set()},
                )
        for row in rows:
            if row["action"] in {"alias", "new"} and row["ingredient_id"] in table:
                table[row["ingredient_id"]]["aliases"].add(row["alias"])
    return table


def ingredients() -> list[dict]:
    table = catalog()
    units: dict[str, set] = collections.defaultdict(lambda: {"cup"})
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for record in read_jsonl(ENRICH_SET):
        for line in record["ingredients"]:
            key = form_key(line)
            unit = line.get("unit_normalized")
            if line.get("unit_dimension") == "count" and unit:
                units[key].add(COUNT_ALIASES.get(unit, unit))
            else:
                units[key]  # every form gets at least "cup"
            if len(examples[key]) < 8 and line["original_text"] not in examples[key]:
                examples[key].append(line["original_text"])
    items = []
    for key in sorted(units):
        base_id = key.split("#")[0]
        info = table[base_id]
        cooked = key.endswith("#cooked")
        items.append(
            {
                "ingredient_id": key,
                "canonical_name": f"cooked {info['canonical_name']}" if cooked else info["canonical_name"],
                "food_group": info["food_group"],
                "aliases": sorted(info["aliases"])[:12],
                "units_to_weigh": sorted(units[key] - MASS_UNITS),
                "examples": examples[key],
            }
        )
    return items


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "select":
        select_enrichment_set()
    elif command in {"recipes", "ingredients"}:
        items = recipes() if command == "recipes" else ingredients()
        path = STAGING / f"v2_{command}_items.jsonl"
        write_jsonl(path, items)
        print(f"{command}: {len(items)} items -> {path.relative_to(ROOT)}")
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
