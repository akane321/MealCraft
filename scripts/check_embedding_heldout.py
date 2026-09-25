"""Check (and freeze) the held-out sets for ingredient matching (task A) and swap requests (task B).

    python scripts/check_embedding_heldout.py A FILE.json [--catalog DIR] [--dev DEV.json] [--freeze]
    python scripts/check_embedding_heldout.py B FILE.json [--catalog DIR] [--dev DEV.json] [--freeze]

Standard library only, so it runs inside the sealed authoring packet as well as the repository. `--catalog`
is the packet's data directory (catalog-ingredients.csv, catalog-mains.jsonl); without it the repository's
release data is read. `--dev` compares with the developer set at intake (the packet never contains it).
`--freeze` records the file's SHA-256 next to it; a frozen set is read by the evaluation once.
"""

import csv
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

KINDS_A = {
    "synonym",
    "british",
    "american",
    "regional",
    "chinese",
    "malay",
    "spelling",
    "typo",
    "short",
    "none",
    "other",
}
CHECKS_B = {"any_ingredient", "cuisine", "course", "title_word", "dietary_tag"}
MIN_A, MIN_B = 30, 15
EXACT_NAME_SHARE = 0.10  # a term that is already a catalog name tests nothing; a few are allowed
PREVALENCE = (0.01, 0.60)  # share of mains a check accepts: a pool of 100 holds one in most trials, not all


def fold(text: str) -> str:
    return " ".join(text.casefold().replace("_", " ").split())


def catalog(directory: Path | None) -> tuple[dict[str, str], list[dict]]:
    if directory is not None:
        with (directory / "catalog-ingredients.csv").open(encoding="utf-8") as handle:
            names = {row["id"]: row["name"] for row in csv.DictReader(handle)}
        mains = [
            json.loads(line) for line in (directory / "catalog-mains.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        return names, mains
    root = Path(__file__).resolve().parents[1]
    names = {}
    for line in (
        (root / "data-engineering/data/release/v2.1/ingredients.jsonl").read_text(encoding="utf-8").splitlines()
    ):
        record = json.loads(line)
        names[record["ingredient_id"].removeprefix("ING_").lower()] = record["canonical_name"]
    for record in json.loads((root / "data/ingredients/ingredients.json").read_text(encoding="utf-8")):
        names.setdefault(record["normalized_name"], record["display_name"])
    mains = [
        {
            "id": r["recipe_id"],
            "title": r["title"],
            "cuisine": r["cuisine"],
            "course": r["course"],
            "dietary_tags": r["dietary_tags"],
            "ingredients": sorted(
                {i["canonical_ingredient_id"].removeprefix("ING_").lower() for i in r["ingredients"]}
            ),
        }
        for line in (root / "data-engineering/data/release/v2.1/recipes.jsonl").read_text(encoding="utf-8").splitlines()
        if (r := json.loads(line))["course"] == "main"
    ]
    return names, mains


def accepts(check: dict, recipe: dict) -> bool:
    """The catalog fact a swap request is judged on; the evaluation uses this same function."""
    values = set(check["values"])
    kind = check["type"]
    if kind == "any_ingredient":
        return bool(values & set(recipe["ingredients"]))
    if kind == "cuisine":
        return recipe["cuisine"] in values
    if kind == "course":
        return recipe["course"] in values
    if kind == "dietary_tag":
        return bool(values & set(recipe["dietary_tags"]))
    return any(fold(word) in fold(recipe["title"]) for word in values)  # title_word


def check_a(cases: list[dict], names: dict[str, str]) -> list[str]:
    problems = []
    folded_names = {fold(n) for n in names.values()} | {fold(i) for i in names}
    terms = [fold(c.get("term", "")) for c in cases]
    for n, case in enumerate(cases, start=1):
        where = f"case {n} ({case.get('term')!r})"
        if not case.get("term", "").strip():
            problems.append(f"{where}: empty term")
        if case.get("kind") not in KINDS_A:
            problems.append(f"{where}: kind must be one of {sorted(KINDS_A)}")
        unknown = [i for i in case.get("accept", []) if i not in names]
        if unknown:
            problems.append(f"{where}: accept ids not in the catalog: {unknown}")
        if (case.get("kind") == "none") != (not case.get("accept")):
            problems.append(f"{where}: kind 'none' exactly when accept is empty")
        if not case.get("context", "").strip():
            problems.append(f"{where}: context (the sentence a household would say) is required")
    duplicates = {t for t in terms if terms.count(t) > 1}
    if duplicates:
        problems.append(f"duplicate terms: {sorted(duplicates)}")
    exact = sum(t in folded_names for t in terms)
    if exact > EXACT_NAME_SHARE * len(cases):
        problems.append(f"{exact} terms are already catalog names or ids; at most {EXACT_NAME_SHARE:.0%} may be")
    if len(cases) < MIN_A:
        problems.append(f"{len(cases)} cases; at least {MIN_A}")
    return problems


def check_b(cases: list[dict], names: dict[str, str], mains: list[dict]) -> list[str]:
    problems = []
    cuisines = {m["cuisine"] for m in mains}
    tags = {t for m in mains for t in m["dietary_tags"]}
    for n, case in enumerate(cases, start=1):
        where = f"case {n} ({case.get('request')!r})"
        check = case.get("check", {})
        if not case.get("request", "").strip():
            problems.append(f"{where}: empty request")
        if check.get("type") not in CHECKS_B or not check.get("values"):
            problems.append(f"{where}: check needs a type from {sorted(CHECKS_B)} and non-empty values")
            continue
        allowed = {"any_ingredient": set(names), "cuisine": cuisines, "dietary_tag": tags, "course": {"main"}}
        unknown = [v for v in check["values"] if check["type"] in allowed and v not in allowed[check["type"]]]
        if unknown:
            problems.append(f"{where}: values not in the catalog: {unknown}")
            continue
        share = sum(accepts(check, m) for m in mains) / len(mains)
        if not PREVALENCE[0] <= share <= PREVALENCE[1]:
            problems.append(
                f"{where}: the check accepts {share:.1%} of mains; keep it between "
                f"{PREVALENCE[0]:.0%} and {PREVALENCE[1]:.0%}"
            )
    requests = [fold(c.get("request", "")) for c in cases]
    duplicates = {r for r in requests if requests.count(r) > 1}
    if duplicates:
        problems.append(f"duplicate requests: {sorted(duplicates)}")
    if len(cases) < MIN_B:
        problems.append(f"{len(cases)} cases; at least {MIN_B}")
    return problems


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in {"A", "B"}:
        sys.exit(__doc__)
    task, path = args[0], Path(args[1])
    directory = Path(args[args.index("--catalog") + 1]) if "--catalog" in args else None
    names, mains = catalog(directory)
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    problems = check_a(cases, names) if task == "A" else check_b(cases, names, mains)
    if "--dev" in args:
        dev = json.loads(Path(args[args.index("--dev") + 1]).read_text(encoding="utf-8"))["cases"]
        key = "term" if task == "A" else "request"
        seen = {fold(c[key]) for c in dev}
        overlap = sorted(c[key] for c in cases if fold(c[key]) in seen)
        if overlap:
            problems.append(f"also in the developer set: {overlap}")
    if not data.get("authored_by", "").strip():
        problems.append("authored_by is required (who wrote the set, and with what help)")
    for problem in problems:
        print("-", problem)
    if problems:
        sys.exit(f"{len(problems)} problem(s); fix them and run again")
    print(f"{path.name}: {len(cases)} cases pass")
    if "--freeze" in args:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stamp = {"file": path.name, "sha256": digest, "cases": len(cases), "frozen_at": datetime.now(UTC).isoformat()}
        path.with_suffix(".frozen.json").write_text(json.dumps(stamp, indent=1) + "\n", encoding="utf-8")
        print(f"frozen: {digest}")


if __name__ == "__main__":
    main()
