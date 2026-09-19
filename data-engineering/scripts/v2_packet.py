"""Work-packet tool for release v2 enrichment (ADR-0030 section 5).

Every item to enrich is assigned to one of three parts, A, B or C, by a hash of
its id, so the parts never overlap and their outputs merge by concatenation. A
few items (OVERLAP_RATE) are also given to the next part, to measure agreement
between producers. Each part lives in its own folder:

    enrichment-work/part-X/ingredients.input.jsonl   what to enrich
    enrichment-work/part-X/recipes.input.jsonl
    enrichment-work/part-X/ingredients.output.jsonl  appended one item at a time
    enrichment-work/part-X/recipes.output.jsonl

Commands (run from data-engineering/):

    python scripts/v2_packet.py status  [--part A]
    python scripts/v2_packet.py next    --part A --kind recipes [--n 10]
    python scripts/v2_packet.py submit  --part A --kind recipes --by "claude/<name>" < results.jsonl
    python scripts/v2_packet.py merge                      # all parts, validated
    python scripts/v2_packet.py build-inputs               # maintainers only

`next` prints the next items not yet in the output; `submit` validates each
result and appends the valid ones, reporting the rest, so a stopped run resumes
where it stopped. Nothing is ever overwritten.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "enrichment-work"
VOCAB = json.loads((ROOT / "config" / "recipe_vocabulary.json").read_text(encoding="utf-8"))
PARTS = ("A", "B", "C")
OVERLAP_RATE = 0.03
KINDS = ("ingredients", "recipes")
ALLERGENS = {"milk", "eggs", "fish", "crustaceans", "tree_nuts", "peanuts", "gluten", "soy", "sesame"}
NUTRIENTS = ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")
# Estimated amounts use mass or volume only: every ingredient has grams per cup, so both always convert.
ESTIMATE_UNITS = {"g", "kg", "oz", "lb", "ml", "l", "tsp", "tbsp", "cup"}
ID_FIELD = {"ingredients": "ingredient_id", "recipes": "candidate_id"}


def part_of(item_id: str) -> tuple[str, str | None]:
    """Primary part, and the second part for an overlap item (or None)."""
    digest = int(hashlib.sha256(item_id.encode("utf-8")).hexdigest(), 16)
    primary = PARTS[digest % 3]
    overlap = PARTS[(digest % 3 + 1) % 3] if (digest // 3) % 1000 < OVERLAP_RATE * 1000 else None
    return primary, overlap


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------------------ validation
def _num(value, low, high) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high


def check_ingredient(item: dict, result: dict) -> list[str]:
    errors = []
    nutrition = result.get("nutrition_per_100g") or {}
    limits = {
        "energy_kcal": 900,
        "protein_g": 100,
        "carbohydrate_g": 100,
        "fat_g": 100,
        "sodium_mg": 40000,
        "sugar_g": 100,
    }
    for key in NUTRIENTS:
        if not _num(nutrition.get(key), 0, limits[key]):
            errors.append(f"nutrition_per_100g.{key} missing or out of range")
    if not errors:
        if nutrition["protein_g"] + nutrition["carbohydrate_g"] + nutrition["fat_g"] > 105:
            errors.append("protein + carbohydrate + fat exceed 100 g per 100 g")
        if nutrition["sugar_g"] > nutrition["carbohydrate_g"] + 0.5:
            errors.append("sugar exceeds carbohydrate")
        atwater = 4 * nutrition["protein_g"] + 4 * nutrition["carbohydrate_g"] + 9 * nutrition["fat_g"]
        gap = abs(atwater - nutrition["energy_kcal"])
        if (
            gap > 40
            and gap > 0.35 * max(atwater, nutrition["energy_kcal"])
            and "energy_check_exception" not in result.get("notes", "")
        ):
            errors.append(
                f"energy {nutrition['energy_kcal']} kcal disagrees with macros ({atwater:.0f}); fix it or "
                "explain in notes with the words energy_check_exception (alcohol, fibre, polyols)"
            )
    if not isinstance(result.get("nutrition_form"), str) or not result["nutrition_form"].strip():
        errors.append("nutrition_form missing")
    grams = {u.get("unit"): u for u in result.get("unit_grams") or [] if isinstance(u, dict)}
    for unit in item["units_to_weigh"]:
        entry = grams.get(unit)
        if not entry or not _num(entry.get("grams"), 0.05, 5000) or not str(entry.get("basis", "")).strip():
            errors.append(f"unit_grams for '{unit}' missing, out of range or without basis")
    if not set(result.get("allergen_opinion") or []) <= ALLERGENS:
        errors.append(f"allergen_opinion must use {sorted(ALLERGENS)}")
    sources = result.get("sources") or []
    if not sources or not all(isinstance(s, dict) and str(s.get("url", "")).startswith("http") for s in sources):
        errors.append("at least one source with an http(s) url is required")
    if not _num(result.get("confidence"), 0, 1):
        errors.append("confidence must be 0-1")
    return errors


def check_recipe(item: dict, result: dict) -> list[str]:
    errors = []
    for key in ("prep_minutes", "cook_minutes", "passive_minutes"):
        if not (isinstance(result.get(key), int) and 0 <= result[key] <= 10080):
            errors.append(f"{key} must be an integer 0-10080")
    if not errors and result["prep_minutes"] + result["cook_minutes"] <= 0:
        errors.append("prep_minutes + cook_minutes must be > 0")
    if result.get("time_basis") not in {"stated", "estimated"}:
        errors.append("time_basis must be stated or estimated")
    if not (isinstance(result.get("servings"), int) and 1 <= result["servings"] <= 100):
        errors.append("servings must be an integer 1-100")
    elif item.get("servings") and result["servings"] != item["servings"]:
        errors.append(f"servings is stated by the source as {item['servings']}; keep it")
    for key in ("course", "cuisine", "difficulty"):
        if result.get(key) not in VOCAB[key]:
            errors.append(f"{key} must be one of {VOCAB[key]}")
    meal_types = result.get("meal_types")
    if not meal_types or not set(meal_types) <= set(VOCAB["meal_types"]):
        errors.append(f"meal_types must be a non-empty subset of {VOCAB['meal_types']}")
    wanted = {line["index"] for line in item["ingredients"] if line.get("needs_amount")}
    estimates = {e.get("index"): e for e in result.get("line_estimates") or [] if isinstance(e, dict)}
    for index in wanted:
        estimate = estimates.get(index)
        valid = (
            estimate
            and _num(estimate.get("quantity"), 0.001, 5000)
            and estimate.get("unit") in ESTIMATE_UNITS
            and str(estimate.get("basis", "")).strip()
        )
        if not valid:
            errors.append(
                f"line_estimates for ingredient line {index} needs quantity, unit in {sorted(ESTIMATE_UNITS)} and basis"
            )
    # Lines whose stated amount is mostly not eaten (deep-frying oil, pasta water, a discarded
    # marinade or brine) carry the amount actually consumed; nutrition uses it.
    consumed = [e for e in result.get("consumed_estimates") or [] if isinstance(e, dict)]
    stated = {line["index"] for line in item["ingredients"] if not line.get("needs_amount")}
    for estimate in consumed:
        valid = (
            estimate.get("index") in stated
            and _num(estimate.get("quantity"), 0, 5000)
            and estimate.get("unit") in ESTIMATE_UNITS
            and str(estimate.get("basis", "")).strip()
        )
        if not valid:
            errors.append(
                "consumed_estimates entries need the index of a line with a stated amount, quantity, a unit in "
                f"{sorted(ESTIMATE_UNITS)} and basis"
            )
            break
    if set(estimates) - wanted:
        errors.append(f"line_estimates given for lines that already have an amount: {sorted(set(estimates) - wanted)}")
    evidence = result.get("evidence") or {}
    confidence = result.get("confidence") or {}
    for key in ("time", "servings", "course", "cuisine", "meal_types", "difficulty"):
        if not str(evidence.get(key, "")).strip():
            errors.append(f"evidence.{key} missing")
        if not _num(confidence.get(key), 0, 1):
            errors.append(f"confidence.{key} must be 0-1")
    return errors


CHECKS = {"ingredients": check_ingredient, "recipes": check_recipe}


# ------------------------------------------------------------------------ commands
def status(parts: list[str]) -> None:
    for part in parts:
        folder = WORK / f"part-{part}"
        for kind in KINDS:
            total = len(read_jsonl(folder / f"{kind}.input.jsonl"))
            done = len({r[ID_FIELD[kind]] for r in read_jsonl(folder / f"{kind}.output.jsonl")})
            print(f"part {part} {kind:<11} {done:>6}/{total:<6} done")


def next_items(part: str, kind: str, n: int) -> None:
    folder = WORK / f"part-{part}"
    done = {r[ID_FIELD[kind]] for r in read_jsonl(folder / f"{kind}.output.jsonl")}
    todo = [item for item in read_jsonl(folder / f"{kind}.input.jsonl") if item[ID_FIELD[kind]] not in done]
    for item in todo[:n]:
        print(json.dumps(item, ensure_ascii=False))
    print(f"# {len(todo)} {kind} left in part {part}", file=sys.stderr)


def submit(part: str, kind: str, by: str) -> int:
    folder = WORK / f"part-{part}"
    items = {i[ID_FIELD[kind]]: i for i in read_jsonl(folder / f"{kind}.input.jsonl")}
    out_path = folder / f"{kind}.output.jsonl"
    done = {r[ID_FIELD[kind]] for r in read_jsonl(out_path)}
    accepted, rejected = 0, 0
    with out_path.open("a", encoding="utf-8", newline="\n") as out:
        for number, line in enumerate(sys.stdin, 1):
            if not line.strip():
                continue
            try:
                result = json.loads(line)
            except json.JSONDecodeError as error:
                print(f"line {number}: not JSON ({error})")
                rejected += 1
                continue
            item_id = result.get(ID_FIELD[kind])
            if item_id not in items:
                print(f"line {number}: {ID_FIELD[kind]} {item_id!r} is not in part {part}")
                rejected += 1
                continue
            if item_id in done:
                print(f"line {number}: {item_id} already done, skipped")
                continue
            errors = CHECKS[kind](items[item_id], result)
            if errors:
                print(f"line {number}: {item_id} rejected: " + "; ".join(errors))
                rejected += 1
                continue
            result["enriched_by"] = by
            out.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            done.add(item_id)
            accepted += 1
    print(f"accepted {accepted}, rejected {rejected}")
    return 1 if rejected else 0


def merge() -> int:
    """Validate every part and write the merged outputs; report overlap agreement."""
    problems = 0
    for kind in KINDS:
        merged: dict[str, dict] = {}
        duplicates: dict[str, list[dict]] = collections.defaultdict(list)
        missing = 0
        for part in PARTS:
            folder = WORK / f"part-{part}"
            items = {i[ID_FIELD[kind]]: i for i in read_jsonl(folder / f"{kind}.input.jsonl")}
            outputs = {r[ID_FIELD[kind]]: r for r in read_jsonl(folder / f"{kind}.output.jsonl")}
            for item_id, item in items.items():
                result = outputs.get(item_id)
                if result is None:
                    missing += 1
                    continue
                errors = CHECKS[kind](item, result)
                if errors:
                    print(f"{part} {item_id}: " + "; ".join(errors))
                    problems += 1
                    continue
                if item.get("overlap_copy"):
                    duplicates[item_id].append(result)
                else:
                    merged[item_id] = result
        agreement = _agreement(kind, merged, duplicates)
        path = WORK / f"merged.{kind}.jsonl"
        path.write_text(
            "".join(json.dumps(merged[k], ensure_ascii=False, sort_keys=True) + "\n" for k in sorted(merged)),
            encoding="utf-8",
            newline="\n",
        )
        print(f"{kind}: {len(merged)} merged, {missing} not done, overlap agreement {agreement}")
    return 1 if problems else 0


def _agreement(kind: str, merged: dict, duplicates: dict) -> dict:
    pairs = [(merged[k], d) for k, copies in duplicates.items() if k in merged for d in copies]
    if not pairs:
        return {"pairs": 0}
    if kind == "recipes":
        fields = ("course", "cuisine", "difficulty", "time_basis")
        report = {f: round(sum(a[f] == b[f] for a, b in pairs) / len(pairs), 3) for f in fields}
        total = [(a["prep_minutes"] + a["cook_minutes"], b["prep_minutes"] + b["cook_minutes"]) for a, b in pairs]
        report["working_minutes_within_25pct"] = round(
            sum(abs(x - y) <= 0.25 * max(x, y, 1) for x, y in total) / len(total), 3
        )
    else:
        report = {
            n: round(
                sum(
                    abs(a["nutrition_per_100g"][n] - b["nutrition_per_100g"][n])
                    <= 0.15 * max(a["nutrition_per_100g"][n], b["nutrition_per_100g"][n], 1)
                    for a, b in pairs
                )
                / len(pairs),
                3,
            )
            for n in NUTRIENTS
        }
    report["pairs"] = len(pairs)
    return report


def build_inputs(recipes_path: Path, ingredients_path: Path) -> None:
    """Split prepared input items into the three parts (maintainers only)."""
    for kind, path in (("recipes", recipes_path), ("ingredients", ingredients_path)):
        buckets: dict[str, list[dict]] = {p: [] for p in PARTS}
        for item in read_jsonl(path):
            primary, overlap = part_of(item[ID_FIELD[kind]])
            buckets[primary].append(item)
            if overlap:
                buckets[overlap].append({**item, "overlap_copy": True})
        for part, items in buckets.items():
            folder = WORK / f"part-{part}"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{kind}.input.jsonl"
            if read_jsonl(folder / f"{kind}.output.jsonl"):
                raise SystemExit(f"{target} already has outputs; inputs are frozen once work starts")
            target.write_text(
                "".join(json.dumps(i, ensure_ascii=False, sort_keys=True) + "\n" for i in items),
                encoding="utf-8",
                newline="\n",
            )
            print(f"part {part} {kind}: {len(items)} items")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "next", "submit"):
        command = sub.add_parser(name)
        command.add_argument("--part", choices=PARTS, required=name != "status")
        if name != "status":
            command.add_argument("--kind", choices=KINDS, required=True)
        if name == "next":
            command.add_argument("--n", type=int, default=10)
        if name == "submit":
            command.add_argument("--by", required=True, help='who produced it, e.g. "claude/alice" or "codex/bob"')
    sub.add_parser("merge")
    build = sub.add_parser("build-inputs")
    build.add_argument("--recipes", type=Path, required=True)
    build.add_argument("--ingredients", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "status":
        status([args.part] if args.part else list(PARTS))
    elif args.command == "next":
        next_items(args.part, args.kind, args.n)
    elif args.command == "submit":
        if not re.fullmatch(r"(claude|codex|human)/[\w.-]+", args.by):
            raise SystemExit('--by must look like "claude/<name>", "codex/<name>" or "human/<name>"')
        return submit(args.part, args.kind, args.by)
    elif args.command == "merge":
        return merge()
    elif args.command == "build-inputs":
        build_inputs(args.recipes, args.ingredients)
    return 0


if __name__ == "__main__":
    sys.exit(main())
