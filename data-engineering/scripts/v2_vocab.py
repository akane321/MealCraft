"""Stage 3 of release v2: extend the ingredient vocabulary for the new sources.

    python scripts/v2_vocab.py worklist       # names to decide -> data/staging/v2_vocab_worklist.jsonl
    python scripts/v2_vocab.py status         # decided / pending counts, allergen rules awaiting a human
    python scripts/v2_vocab.py merge-batches  # batch decisions -> config/ingredient_aliases_v2_additions.csv
    python scripts/v2_vocab.py review-sheet   # new ingredients' proposed allergen rules, for a human

Decisions live in `config/ingredient_aliases_v2_additions.csv`, one row per
unmapped name:

- `alias`: the name is another way of writing an existing canonical ingredient;
  it inherits that ingredient's allergen rule, so nothing needs confirming;
- `new`: a new canonical ingredient, with food group and dietary origin. Its
  allergen rule is proposed and stays `pending_human` until a person confirms it
  (ADR-0030 section 4, ADR-0024 section 3); a recipe using it cannot be released
  before then;
- `drop`: not a usable ingredient ("marinade", a garbled line); a recipe
  containing it leaves v2.

Which names are worked: every unmapped name in a bucket whose supply is thin,
and names seen at least twice elsewhere. A candidate with an undecided name is
simply not used.
"""

from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "staging"
ALIASES = ROOT / "config" / "ingredient_aliases.csv"
ADDITIONS = ROOT / "config" / "ingredient_aliases_v2_additions.csv"
QUOTAS = json.loads((ROOT / "config" / "v2_quotas.json").read_text(encoding="utf-8"))
SCARCE = {b for b, spec in QUOTAS["buckets"].items() if "oversample" in spec}
FIELDS = [
    "alias",
    "action",
    "ingredient_id",
    "canonical_name",
    "food_group",
    "allergens",
    "dietary_origin",
    "allergen_status",
    "decided_by",
    "basis",
]
ALLERGEN_RULES = {
    "milk",
    "eggs",
    "fish",
    "crustaceans",
    "molluscs",
    "tree_nuts",
    "peanuts",
    "gluten",
    "gluten_candidate",
    "soy",
    "sesame",
    "sulfites",
}
ORIGINS = {"plant", "flesh", "secretion"}


def existing() -> dict[str, dict]:
    """canonical id -> {canonical_name, food_group, allergens} from the current alias table."""
    table = {}
    with ALIASES.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            table.setdefault(row["ingredient_id"], row)
    return table


def decisions() -> dict[str, dict]:
    if not ADDITIONS.exists():
        return {}
    with ADDITIONS.open(encoding="utf-8") as handle:
        return {row["alias"]: row for row in csv.DictReader(handle)}


def check_row(row: dict, known: dict[str, dict], new_ids: set[str]) -> list[str]:
    errors = []
    if row["action"] == "alias":
        if row["ingredient_id"] not in known and row["ingredient_id"] not in new_ids:
            errors.append(f"alias target {row['ingredient_id']} does not exist")
    elif row["action"] == "new":
        if not row["ingredient_id"].startswith("ING_") or row["ingredient_id"] in known:
            errors.append("new ingredient_id must start with ING_ and not already exist")
        if not row["canonical_name"] or not row["food_group"]:
            errors.append("new ingredient needs canonical_name and food_group")
        if row["dietary_origin"] not in ORIGINS:
            errors.append(f"dietary_origin must be one of {sorted(ORIGINS)}")
        if not set(filter(None, row["allergens"].split(";"))) <= ALLERGEN_RULES:
            errors.append(f"allergens must use {sorted(ALLERGEN_RULES)}")
        if row["allergen_status"] not in {"pending_human", "confirmed"}:
            errors.append("allergen_status must be pending_human or confirmed")
    elif row["action"] != "drop":
        errors.append("action must be alias, new or drop")
    if not row["basis"].strip():
        errors.append("basis is required")
    return errors


def worklist() -> None:
    records = [json.loads(line) for line in (STAGING / "v2_candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    counts: collections.Counter = collections.Counter()
    buckets: dict[str, set] = collections.defaultdict(set)
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for record in records:
        for line in record["ingredients"]:
            if line["normalization_status"] == "mapped":
                continue
            name = line["ingredient_text"].strip()
            counts[name] += 1
            buckets[name].add(record["quota_bucket"])
            if len(examples[name]) < 3:
                examples[name].append(line["original_text"])
    decided = decisions()
    wanted = [n for n in counts if n and n not in decided and (counts[n] >= 2 or buckets[n] & SCARCE)]
    wanted.sort(key=lambda n: -counts[n])
    path = STAGING / "v2_vocab_worklist.jsonl"
    path.write_text(
        "".join(
            json.dumps(
                {"name": n, "count": counts[n], "buckets": sorted(buckets[n]), "examples": examples[n]},
                ensure_ascii=False,
            )
            + "\n"
            for n in wanted
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"{len(wanted)} names to decide ({len(decided)} already decided) -> {path.relative_to(ROOT)}")


def status() -> int:
    known = existing()
    rows = decisions()
    new_ids = {r["ingredient_id"] for r in rows.values() if r["action"] == "new"}
    bad = 0
    for alias, row in rows.items():
        errors = check_row(row, known, new_ids)
        if errors:
            bad += 1
            print(f"{alias!r}: " + "; ".join(errors))
    actions = collections.Counter(r["action"] for r in rows.values())
    pending = sum(1 for r in rows.values() if r["action"] == "new" and r["allergen_status"] == "pending_human")
    print(
        f"decided {len(rows)}: {dict(actions)}; new ingredients awaiting allergen confirmation: {pending}; "
        f"invalid rows: {bad}"
    )
    return 1 if bad else 0


def review_sheet() -> None:
    rows = [r for r in decisions().values() if r["action"] == "new"]
    by_id: dict[str, dict] = {}
    for row in rows:
        entry = by_id.setdefault(row["ingredient_id"], {**row, "aliases": []})
        entry["aliases"].append(row["alias"])
    path = ROOT / "data" / "enrichment" / "v2_new_ingredient_allergens.csv"
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(
            [
                "ingredient_id",
                "canonical_name",
                "food_group",
                "proposed_allergens",
                "aliases",
                "allergen_status",
                "confirm_or_correct",
            ]
        )
        for ingredient_id, entry in sorted(by_id.items()):
            writer.writerow(
                [
                    ingredient_id,
                    entry["canonical_name"],
                    entry["food_group"],
                    entry["allergens"] or "(none)",
                    " | ".join(entry["aliases"]),
                    entry["allergen_status"],
                    "",
                ]
            )
    print(f"{len(by_id)} new ingredients -> {path.relative_to(ROOT)}")


def merge_batches() -> int:
    """Validate the batch decisions and write them to the additions table."""
    folder = STAGING / "vocab_batches"
    known = existing()
    rows: dict[str, dict] = decisions()
    problems = 0
    for inp in sorted(folder.glob("batch-*.in.jsonl")):
        out = inp.with_name(inp.name.replace(".in.", ".out."))
        names = [json.loads(line)["name"] for line in inp.read_text(encoding="utf-8").splitlines() if line]
        if not out.exists():
            print(f"{out.name}: missing")
            problems += 1
            continue
        got = {}
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                got[row.get("alias")] = {f: str(row.get(f) or "") for f in FIELDS}
        missing = [n for n in names if n not in got]
        extra = [n for n in got if n not in names]
        if missing or extra:
            print(f"{out.name}: {len(missing)} names missing, {len(extra)} unexpected")
            problems += 1
        for name in names:
            if name in got:
                rows[name] = got[name]
    # Synonymous new ids from different batches are unified by id_merges.json ({"old": "kept"}).
    merges_path = folder / "id_merges.json"
    merges = json.loads(merges_path.read_text(encoding="utf-8")) if merges_path.exists() else {}
    for row in rows.values():
        row["ingredient_id"] = merges.get(row["ingredient_id"], row["ingredient_id"])
        if row["action"] == "new" and row["ingredient_id"] in known:
            # A batch minted an id that already exists: the existing definition wins.
            row.update(
                {f: "" for f in ("canonical_name", "food_group", "allergens", "dietary_origin", "allergen_status")},
                action="alias",
            )
    # Reviewed definitions for new ids whose batches disagreed ({"ING_X": {"allergens": "..."}}).
    definitions_path = folder / "id_definitions.json"
    definitions = json.loads(definitions_path.read_text(encoding="utf-8")) if definitions_path.exists() else {}
    for row in rows.values():
        if row["action"] == "new" and row["ingredient_id"] in definitions:
            row.update(definitions[row["ingredient_id"]])
    # One definition per new id: the first batch's wins when the allergen rule agrees;
    # a disagreement on allergens is a safety question and is reported instead.
    first: dict[str, dict] = {}
    for alias in sorted(rows):
        row = rows[alias]
        if row["action"] != "new":
            continue
        kept = first.setdefault(row["ingredient_id"], row)
        if kept is row:
            continue
        if kept["allergens"] != row["allergens"]:
            print(f"{row['ingredient_id']}: allergens differ ({kept['allergens']!r} vs {row['allergens']!r})")
            problems += 1
        for field in ("canonical_name", "food_group", "allergens", "dietary_origin", "allergen_status"):
            row[field] = kept[field]
    new_ids = set(first)
    by_new_id = first
    invalid = [(a, e) for a, r in rows.items() if (e := check_row(r, known, new_ids))]
    for alias, errors in invalid[:50]:
        print(f"{alias!r}: " + "; ".join(errors))
    problems += len(invalid)
    with ADDITIONS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for alias in sorted(rows):
            writer.writerow(rows[alias])
    print(f"{len(rows)} decisions written; {len(by_new_id)} new ingredients; problems: {problems}")
    return 1 if problems else 0


def resolver():
    """Return a function mapping an unmapped ingredient name to (id, name, allergens) or "drop" / None."""
    known = existing()
    rows = decisions()
    new = {r["ingredient_id"]: r for r in rows.values() if r["action"] == "new"}

    def resolve(name: str, by_id: bool = False):
        if by_id:
            row = new.get(name)
            if row is None:
                return None
            return row["ingredient_id"], row["canonical_name"], row["allergens"], row["allergen_status"]
        row = rows.get(name.strip())
        if row is None:
            return None
        if row["action"] == "drop":
            return "drop"
        target = new.get(row["ingredient_id"]) or row
        if row["action"] == "alias" and row["ingredient_id"] in known:
            base = known[row["ingredient_id"]]
            return row["ingredient_id"], base["canonical_name"], base["allergens"], "confirmed"
        return target["ingredient_id"], target["canonical_name"], target["allergens"], target["allergen_status"]

    return resolve


def apply_review(path: Path) -> int:
    """Apply a human-reviewed allergen sheet: `ok` keeps the proposal, `none` means no allergen,
    anything else is the corrected `;`-separated rule. Every new ingredient must be answered."""
    with path.open(encoding="utf-8-sig") as handle:
        answers = {r["ingredient_id"]: r for r in csv.DictReader(handle)}
    rows = decisions()
    new_ids = {r["ingredient_id"] for r in rows.values() if r["action"] == "new"}
    problems, final = [], {}
    for ingredient_id in sorted(new_ids):
        answer = answers.get(ingredient_id)
        verdict = (answer or {}).get("confirm_or_correct", "").strip().lower()
        if not verdict:
            problems.append(f"{ingredient_id}: no answer")
            continue
        proposed = answer["proposed_allergens"].strip()
        if verdict == "ok":
            chosen = "" if proposed == "(none)" else proposed
        elif verdict == "none":
            chosen = ""
        else:
            chosen = verdict
        parts = [a.strip() for a in chosen.split(";") if a.strip()]
        if not set(parts) <= ALLERGEN_RULES:
            problems.append(f"{ingredient_id}: unknown allergen in {chosen!r}")
            continue
        final[ingredient_id] = ";".join(parts)
    extra = sorted(set(answers) - new_ids)
    problems += [f"{i}: not a new ingredient" for i in extra]
    if problems:
        print("\n".join(problems))
        return 1
    changed = 0
    for row in rows.values():
        if row["action"] == "new":
            if row["allergens"] != final[row["ingredient_id"]]:
                changed += 1
            row["allergens"] = final[row["ingredient_id"]]
            row["allergen_status"] = "confirmed"
    with ADDITIONS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for alias in sorted(rows):
            writer.writerow(rows[alias])
    print(f"confirmed {len(final)} new ingredients; {changed} alias rows took a corrected rule")
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "worklist":
        worklist()
    elif command == "status":
        return status()
    elif command == "review-sheet":
        review_sheet()
    elif command == "merge-batches":
        return merge_batches()
    elif command == "apply-review":
        return apply_review(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
