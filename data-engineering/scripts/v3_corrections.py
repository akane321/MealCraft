"""Check the reviewed corrections of release v3's added recipes, and withdraw the unfit ones (issue #408).

    python scripts/v3_corrections.py validate TABLE   # name every problem by row; exit 1 if any
    python scripts/v3_corrections.py withdraw TABLE   # write the withdraw rows into data/recipes/withdrawn.json

The table is `data/enrichment/v3-corrections.csv` (UTF-8 with BOM, so that Excel reads it), one row per recipe and
field: recipe_id, field, old_value, new_value, reason, reviewer. Fields: cuisine, course, servings (a whole number
1-50) and withdraw (new_value `yes`, old_value empty). Only recipes added in v3 (not in v2.2) may be corrected.
`validate` reads the committed `data/release/v3/recipes.jsonl`, so it runs on main without the staging inputs; a row
the release already carries (released value = new_value) passes. `build_release_v3.py` applies the cuisine, course
and servings rows; a withdrawn recipe stays released and is only kept out of plans. Standard library only.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v2_candidates import QUOTAS  # noqa: E402
from select_v3_candidates import CAP  # noqa: E402

TABLE = ROOT / "data" / "enrichment" / "v3-corrections.csv"
RELEASES = ROOT / "data" / "release"
WITHDRAWN = ROOT.parent / "data" / "recipes" / "withdrawn.json"
COLUMNS = ("recipe_id", "field", "old_value", "new_value", "reason", "reviewer")
VOCAB = json.loads((ROOT / "config" / "recipe_vocabulary.json").read_text(encoding="utf-8"))
# The cuisines the v3 build releases (international is in no quota bucket and is dropped).
CUISINES = {cuisine for spec in QUOTAS["buckets"].values() for cuisine in spec["cuisines"]}
COURSES = set(VOCAB["course"])
FIELDS = ("cuisine", "course", "servings", "withdraw")
SLUG_PREFIX = "v2-"  # backend app/data/release_v2.py recipe_slug


def read_table(path: Path = TABLE) -> list[dict]:
    """The filled rows, each with its sheet row number (`row`). `utf-8-sig` drops the BOM; `newline=""` handles CRLF."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path}: missing columns {sorted(missing)}")
        rows = []
        for row in reader:
            row = {key: (value or "").strip() for key, value in row.items() if key}
            if any(row[key] for key in COLUMNS):
                rows.append(dict(row, row=reader.line_num))
    return rows


def read_release(version: str) -> dict[str, dict]:
    path = RELEASES / version / "recipes.jsonl"
    return {r["recipe_id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r}


def value_problem(field: str, value: str) -> str | None:
    if field == "cuisine" and value not in CUISINES:
        return f"new_value {value!r} is not a cuisine of the v3 build"
    if field == "course" and value not in COURSES:
        return f"new_value {value!r} is not one of {', '.join(VOCAB['course'])}"
    if field == "servings" and not (re.fullmatch(r"\d+", value) and 1 <= int(value) <= 50):
        return f"new_value {value!r} is not a whole number 1-50"
    if field == "withdraw" and value.lower() != "yes":
        return f"new_value {value!r} is not yes"
    return None


def new_value(row: dict) -> str | int:
    """The value a checked row gives its field, as the release record holds it."""
    return int(row["new_value"]) if row["field"] == "servings" else row["new_value"]


def check_rows(rows: list[dict], v22: set[str], released: dict[str, dict] | None = None) -> list[str]:
    """Every problem of the table, by row. With `released` (recipe_id -> record) the ids, old values and the cuisine
    cap are checked against it; the build checks old values against the recipes it builds instead."""
    problems, seen, fields_of = [], {}, collections.defaultdict(set)
    moves = []  # (row, old cuisine, new cuisine) of the cuisine rows without other problems
    for row in rows:
        issues, rid, field, old, new = [], row["recipe_id"], row["field"], row["old_value"], row["new_value"]
        for key in ("recipe_id", "field", "reason", "reviewer"):
            if not row[key]:
                issues.append(f"{key} is empty")
        if rid in v22:
            issues.append(f"recipe_id {rid} is a release v2.2 record; only recipes added in v3 may be corrected")
        elif rid and released is not None and rid not in released:
            issues.append(f"recipe_id {rid!r} is not in release v3")
        if field and field not in FIELDS:
            issues.append(f"field {field!r} is not one of {', '.join(FIELDS)}")
        elif field:
            issue = value_problem(field, new)
            if issue:
                issues.append(issue)
            if field == "withdraw" and old:
                issues.append("old_value must be empty for withdraw")
            if field != "withdraw" and old == new:
                issues.append("new_value is the same as old_value")
            record = (released or {}).get(rid)
            if field != "withdraw" and record and rid not in v22 and str(record[field]) not in (old, new):
                issues.append(f"old_value {old!r} is not the released {field} {record[field]!r}")
            if (rid, field) in seen:
                issues.append(f"{rid} {field} is already in row {seen[rid, field]}")
            seen.setdefault((rid, field), row["row"])
            fields_of[rid].add(field)
            if field == "cuisine" and not issues and record and record["cuisine"] != new:
                moves.append((row, record["cuisine"], new))
        problems += [f"row {row['row']}: {issue}" for issue in issues]
    for row in rows:
        if row["field"] == "withdraw" and len(fields_of[row["recipe_id"]]) > 1:
            problems.append(f"row {row['row']}: {row['recipe_id']} is withdrawn, so it takes no other correction")
    if released is not None:
        counts = collections.Counter(r["cuisine"] for r in released.values())
        for _, old, new in moves:
            counts[old] -= 1
            counts[new] += 1
        limit = int(CAP * len(released))
        for row, _, new in moves:
            if counts[new] > limit:
                problems.append(
                    f"row {row['row']}: cuisine {new} would have {counts[new]} of {len(released)} recipes, over the "
                    f"{CAP:.0%} cap ({limit})"
                )
    return sorted(problems, key=lambda p: int(p.split(":")[0].split()[1]))


def recipe_slug(recipe_id: str, title: str) -> str:
    """The catalog slug, as backend `app.data.release_v2.recipe_slug` makes it."""
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:100].strip("-") or "recipe"
    return f"{SLUG_PREFIX}{words}-{recipe_id.split('_', 1)[-1].lower()}"


def withdraw(rows: list[dict], released: dict[str, dict], path: Path = WITHDRAWN) -> int:
    """Add or update one withdrawn.json entry per withdraw row (slug, reason, reviewer); the file is rewritten only
    when an entry changes, so a second run changes nothing. Returns the number of entries added or changed."""
    document = json.loads(path.read_text(encoding="utf-8"))
    entries = {item["slug"]: item for item in document["recipes"]}
    changed = 0
    for row in rows:
        if row["field"] != "withdraw":
            continue
        record = released[row["recipe_id"]]
        slug = recipe_slug(record["recipe_id"], record["title"])
        entry = {"slug": slug, "reason": row["reason"], "reviewer": row["reviewer"]}
        if entries.get(slug) != entry:
            if slug in entries:
                entries[slug].update(entry)
            else:
                document["recipes"].append(entry)
                entries[slug] = entry
            changed += 1
    if changed:
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("validate", "withdraw"))
    parser.add_argument("table", type=Path)
    args = parser.parse_args()
    rows = read_table(args.table)
    released = read_release("v3")
    problems = check_rows(rows, set(read_release("v2.2")), released)
    if problems:
        print("\n".join(problems))
    if args.command == "validate" or problems:
        print(
            f"{len(rows)} rows, {len(problems)} problems" + ("; nothing written" if args.command != "validate" else "")
        )
        sys.exit(1 if problems else 0)
    changed = withdraw(rows, released)
    total = sum(row["field"] == "withdraw" for row in rows)
    print(f"{total} withdraw rows, {changed} entries added or changed in {WITHDRAWN}")


if __name__ == "__main__":
    main()
