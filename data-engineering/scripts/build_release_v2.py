"""Stage 6 of release v2 (ADR-0030): build the release from the merged enrichment.

    python scripts/v2_packet.py merge            # first: validated merge of parts A, B, C
    python scripts/build_release_v2.py           # writes data/release/v2.1/ (v2 is published and frozen)

For every recipe in data/staging/v2_enrich_set.jsonl with an enrichment result:

1. every ingredient line gets grams, with a basis: `stated` (mass unit, or a
   volume or count unit converted through the ingredient's grams per unit),
   `estimated` (a line the source left unquantified), and, for nutrition only,
   `consumed` (frying oil, discarded liquid);
2. per-serving nutrition is the sum of grams x the ingredient form's nutrition
   per 100 g, divided by servings;
3. allergens are the union of the ingredients' rule-table allergens; dietary tags
   are derived from dietary origin exactly as in release v1.1, except that
   `gluten_candidate` also rules out gluten-free.

A recipe is dropped, with its reason, when an ingredient form or unit weight is
missing, when per-serving energy is implausible, when it uses a new
ingredient whose allergen rule no human has confirmed, or (from v2.1) when its
title or steps name a food carrying an allergen no listed ingredient carries and
the completeness review did not clear it (scripts/recipe_completeness.py). A
recipe whose text names meat or fish is not vegetarian or vegan. The remaining recipes are
picked by quota against their enriched cuisine and course (config/v2_quotas.json).
"""

from __future__ import annotations

import collections
import csv
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v2_candidates import QUOTAS, course_group  # noqa: E402
from recipe_completeness import QUEUE, kept_by_review, names_meat, reviews, unlisted_allergens  # noqa: E402
from v2_vocab import ADDITIONS  # noqa: E402

STAGING = ROOT / "data" / "staging"
RELEASE_VERSION = "v2.1"
RELEASE = ROOT / "data" / "release" / RELEASE_VERSION
NUTRIENTS = ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")
ENERGY_PER_SERVING = (10, 3000)
FLESH_ALLERGENS = {"fish", "crustaceans", "molluscs"}
# Built recipes flagged by the completeness check that no review has seen yet.
AWAITING_REVIEW: list[dict] = []
PACKAGE = re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*-?\s*(oz|ounces?|lbs?|pounds?|g|grams?|kg|ml|l)\.?\s*\)", re.I)
PACKAGE_UNIT = {
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "ml": "ml",
    "l": "l",
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def unit_table() -> dict[str, tuple[str, float]]:
    table = {}
    with (ROOT / "config" / "units.csv").open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            table.setdefault(row["normalized_unit"], (row["dimension"], float(row["multiplier_to_base"])))
    return table


UNITS = unit_table()
CUP_ML = UNITS["cup"][1]


def ingredient_rules() -> dict[str, dict]:
    """canonical id -> allergens, allergen status, dietary origin, food group."""
    rules: dict[str, dict] = {}
    with (ROOT / "config" / "ingredient_aliases.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rules.setdefault(
                row["ingredient_id"],
                {
                    "canonical_name": row["canonical_name"],
                    "food_group": row["food_group"],
                    "allergens": [a for a in re.split(r"[;|]", row["allergens"]) if a],
                    "allergen_status": "confirmed",
                },
            )
    with (ROOT / "config" / "ingredient_dietary_origin.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["ingredient_id"] in rules:
                rules[row["ingredient_id"]]["dietary_origin"] = row["dietary_origin"]
    with ADDITIONS.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["action"] == "new":
                rules[row["ingredient_id"]] = {
                    "canonical_name": row["canonical_name"],
                    "food_group": row["food_group"],
                    "allergens": [a for a in row["allergens"].split(";") if a],
                    "allergen_status": row["allergen_status"],
                    "dietary_origin": row["dietary_origin"],
                }
    # Owner-confirmed additions for ingredients whose rule misses what the usual
    # product carries; only ever stricter (config/allergen_corrections.csv).
    with (ROOT / "config" / "allergen_corrections.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rule = rules[row["ingredient_id"]]
            rule["allergens"] = sorted(set(rule["allergens"]) | set(row["add_allergens"].split(";")))
    return rules


def grams(quantity: float, unit: str, weights: dict[str, float]) -> float | None:
    """Grams for `quantity` of `unit`, through the ingredient form's weights (None when unknown)."""
    if unit in {"g", "kg", "oz", "lb", "mg"}:
        return quantity * (0.001 if unit == "mg" else UNITS[unit][1])
    dimension, factor = UNITS.get(unit, (None, None))
    if dimension == "volume" and "cup" in weights:
        return quantity * factor / CUP_ML * weights["cup"]
    if dimension == "count":
        if unit == "dozen":
            return quantity * 12 * weights["piece"] if "piece" in weights else None
        return quantity * weights[unit] if unit in weights else None
    return None


def line_grams(line: dict, weights: dict[str, float], estimate: dict | None) -> tuple[float | None, str]:
    if estimate:
        return grams(estimate["quantity"], estimate["unit"], weights), "estimated"
    low, high = line["quantity_min"], line["quantity_max"]
    quantity = (low + high) / 2 if high is not None else low
    package = PACKAGE.search(line["original_text"])
    if package and line.get("unit_dimension") in {"count", "package"}:
        unit = PACKAGE_UNIT[package.group(2).lower()]
        each = grams(float(package.group(1)), unit, weights)
        return (quantity * each if each is not None else None), "stated_package"
    return grams(quantity, line["unit_normalized"], weights), "stated"


def derive_tags(lines: list[dict], rules: dict[str, dict]) -> tuple[list[str], dict[str, str]]:
    dairy = milk = gluten = flesh = secretion = False
    for line in lines:
        rule = rules[line["canonical_ingredient_id"]]
        dairy |= rule["food_group"] == "dairy"
        milk |= "milk" in rule["allergens"]
        gluten |= bool({"gluten", "gluten_candidate"} & set(rule["allergens"]))
        # An ingredient whose allergens name fish or shellfish is animal flesh
        # whatever its recorded origin (kimchi carries fish sauce and shrimp).
        flesh |= rule.get("dietary_origin") == "flesh" or bool(FLESH_ALLERGENS & set(rule["allergens"]))
        secretion |= rule.get("dietary_origin") == "secretion" or bool({"milk", "eggs"} & set(rule["allergens"]))
    verdicts = {
        "dairy-free": not dairy and not milk,
        "gluten-free": not gluten,
        "vegetarian": not flesh,
        "vegan": not flesh and not secretion,
    }
    return (
        [t for t, ok in verdicts.items() if ok],
        {t: "derived_true" if ok else "derived_false" for t, ok in verdicts.items()},
    )


def build_recipe(record: dict, result: dict, forms: dict[str, dict], rules: dict[str, dict]) -> tuple[dict | None, str]:
    estimates = {e["index"]: e for e in result.get("line_estimates") or []}
    consumed = {e["index"]: e for e in result.get("consumed_estimates") or []}
    totals = dict.fromkeys(NUTRIENTS, 0.0)
    lines_out, pending = [], []
    for index, line in enumerate(record["ingredients"], 1):
        cid = line["canonical_ingredient_id"]
        rule = rules.get(cid)
        if rule is None:
            return None, f"ingredient {cid} has no rule"
        if rule["allergen_status"] != "confirmed":
            pending.append(cid)
        key = f"{cid}#cooked" if "cooked" in (line.get("preparation") or []) else cid
        form = forms.get(key)
        if form is None:
            return None, f"ingredient form {key} not enriched"
        weights = {u["unit"]: u["grams"] for u in form["unit_grams"]}
        weight, basis = line_grams(line, weights, estimates.get(index))
        if weight is None:
            return None, f"no weight for line {index} ({line.get('unit_normalized')}) of {key}"
        eaten = weight
        if index in consumed:
            eaten = grams(consumed[index]["quantity"], consumed[index]["unit"], weights)
            if eaten is None:
                return None, f"no weight for consumed amount of line {index}"
        for nutrient in NUTRIENTS:
            totals[nutrient] += eaten * form["nutrition_per_100g"][nutrient] / 100
        lines_out.append(
            {
                "original_text": line["original_text"],
                "canonical_ingredient_id": cid,
                "canonical_name": rule["canonical_name"],
                "quantity_min": line["quantity_min"],
                "quantity_max": line["quantity_max"],
                "unit": line.get("unit_normalized"),
                "preparation": line.get("preparation") or [],
                "optional": line.get("optional", False),
                "grams": round(weight, 1),
                "grams_basis": basis,
                **(
                    {"grams_consumed": round(eaten, 1), "consumed_basis": consumed[index]["basis"]}
                    if index in consumed
                    else {}
                ),
                **({"estimate_basis": estimates[index]["basis"]} if index in estimates else {}),
                "allergens": rule["allergens"],
            }
        )
    if pending:
        return None, "allergen rule awaiting human confirmation: " + ", ".join(sorted(set(pending)))
    servings = result["servings"]
    per_serving = {k: round(v / servings, 1) for k, v in totals.items()}
    if not ENERGY_PER_SERVING[0] <= per_serving["energy_kcal"] <= ENERGY_PER_SERVING[1]:
        return None, f"implausible energy {per_serving['energy_kcal']} kcal per serving"
    tags, tag_basis = derive_tags(record["ingredients"], rules)
    if names_meat(record) and {"vegetarian", "vegan"} & set(tags):
        tags = [tag for tag in tags if tag not in {"vegetarian", "vegan"}]
        tag_basis.update(vegetarian="text_names_meat", vegan="text_names_meat")
    recipe_id = "RCP2_" + hashlib.sha256(record["candidate_id"].encode()).hexdigest()[:12].upper()
    missing = unlisted_allergens(record, {a for line in lines_out for a in line["allergens"]})
    reviewed = reviews().get(recipe_id)
    if reviewed is not None and reviewed["verdict"] == "incomplete":
        return None, "reviewed incomplete: " + ", ".join(reviewed["allergens"])
    if missing and not kept_by_review(recipe_id):
        if recipe_id not in reviews():
            AWAITING_REVIEW.append(
                {
                    "recipe_id": recipe_id,
                    "title": record["title"],
                    "ingredients": lines_out,
                    "instructions": record["instructions"],
                }
            )
        return None, "text names allergens no listed ingredient carries: " + ", ".join(missing)
    source = record["source"].replace("recipenlg_v1.1", "recipenlg")
    return {
        "recipe_id": recipe_id,
        "schema_version": "mealcraft.recipe.v2",
        "title": record["title"],
        "source": {
            "dataset": {
                "recipenlg": "RecipeNLG (Gathered)",
                "wikibooks": "Wikibooks Cookbook",
                "themealdb": "TheMealDB",
            }[source],
            "source_id": record["source_id"],
            "source_url": record.get("source_url"),
            "source_revision": record.get("source_revision"),
            "license": record["source_license"],
            "candidate_id": record["candidate_id"],
        },
        "servings": servings,
        "servings_basis": "stated" if record.get("servings") else "estimated",
        "prep_minutes": result["prep_minutes"],
        "cook_minutes": result["cook_minutes"],
        "passive_minutes": result["passive_minutes"],
        "total_minutes": result["prep_minutes"] + result["cook_minutes"] + result["passive_minutes"],
        # "stated" needs the source to have said something: a recipe with no stated
        # duration anywhere is our estimate however the enricher labelled it. The
        # durations are the ones the packet showed the enricher, not a second rule.
        "time_basis": result["time_basis"] if record.get("stated_durations") else "estimated",
        "course": result["course"],
        "cuisine": result["cuisine"],
        "meal_types": result["meal_types"],
        "difficulty": result["difficulty"],
        "dietary_tags": tags,
        "dietary_tags_basis": tag_basis,
        "allergens": sorted({a for line in lines_out for a in line["allergens"]}),
        "allergen_basis": "rule table over canonical ingredients (ADR-0024 section 3); check product labels",
        "ingredients": lines_out,
        "instructions": record["instructions"],
        "nutrition": {
            "basis": "per_serving",
            **per_serving,
            "status": "computed",
            "source": "sum of ingredient grams x enriched nutrition per 100 g (ADR-0030)",
        },
        "enrichment": {"by": result["enriched_by"], "evidence": result["evidence"], "confidence": result["confidence"]},
        "video_url": record.get("video_url"),
    }, ""


def pick_by_quota(recipes: list[dict]) -> list[dict]:
    """Final pick against the enriched cuisine and course, within each bucket's target."""
    bucket_of = {c: b for b, spec in QUOTAS["buckets"].items() for c in spec["cuisines"]}
    caps = {"dessert_baked": 0.12, "other": 0.10}
    chosen = []
    by_bucket = collections.defaultdict(list)
    for recipe in sorted(recipes, key=lambda r: r["recipe_id"]):
        # A cuisine no bucket claims (today only `international`) is not released.
        # Counting it as American would both inflate that quota and disagree with
        # the cuisine table in the report, which reads the enriched label.
        by_bucket[bucket_of.get(recipe["cuisine"], "_unbucketed")].append(recipe)
    for bucket, spec in QUOTAS["buckets"].items():
        pool = sorted(by_bucket.get(bucket, []), key=lambda r: course_group(r["course"]) != "main")
        taken, groups = [], collections.Counter()
        for recipe in pool:
            if len(taken) >= spec["target"]:
                break
            group = course_group(recipe["course"])
            if group in caps and groups[group] + 1 > caps[group] * spec["target"]:
                continue
            groups[group] += 1
            taken.append(recipe)
        chosen += taken
    return chosen


def main() -> int:
    enrich_set = {r["candidate_id"]: r for r in read_jsonl(STAGING / "v2_enrich_set.jsonl")}
    # The packet inputs carry the durations found in the steps by rule; the enrich
    # set does not. Attach them so time_basis can be checked against the source.
    for part in ("A", "B", "C"):
        for item in read_jsonl(ROOT / "enrichment-work" / f"part-{part}" / "recipes.input.jsonl"):
            record = enrich_set.get(item["candidate_id"])
            if record is not None:
                record["stated_durations"] = item.get("stated_durations") or []
    results = {r["candidate_id"]: r for r in read_jsonl(STAGING / "v2_merged.recipes.jsonl")}
    forms = {r["ingredient_id"]: r for r in read_jsonl(STAGING / "v2_merged.ingredients.jsonl")}
    rules = ingredient_rules()
    built, dropped = [], collections.Counter()
    drop_log = []
    for candidate_id, record in enrich_set.items():
        result = results.get(candidate_id)
        if result is None:
            dropped["not enriched"] += 1
            continue
        if "exclude" in result:
            dropped["excluded by enricher"] += 1
            drop_log.append({"candidate_id": candidate_id, "title": record["title"], "reason": result["exclude"]})
            continue
        recipe, reason = build_recipe(record, result, forms, rules)
        if recipe is None:
            dropped[re.sub(r"ING_\S+|\d+(\.\d+)?|\([^)]*\)", "#", reason).split(":")[0].strip()] += 1
            drop_log.append({"candidate_id": candidate_id, "title": record["title"], "reason": reason})
            continue
        built.append(recipe)
    release = pick_by_quota(built)
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in AWAITING_REVIEW), encoding="utf-8")
    if AWAITING_REVIEW:
        print(f"{len(AWAITING_REVIEW)} flagged recipes await completeness review: {QUEUE}")

    RELEASE.mkdir(parents=True, exist_ok=True)
    with (RELEASE / "recipes.jsonl").open("w", encoding="utf-8", newline="\n") as out:
        for recipe in sorted(release, key=lambda r: r["recipe_id"]):
            out.write(json.dumps(recipe, ensure_ascii=False, sort_keys=True) + "\n")
    used = collections.Counter()
    for recipe in release:
        for line in recipe["ingredients"]:
            used[line["canonical_ingredient_id"]] += 1
    with (RELEASE / "ingredients.jsonl").open("w", encoding="utf-8", newline="\n") as out:
        for cid in sorted(used):
            rule = rules[cid]
            record = {
                "ingredient_id": cid,
                **{
                    k: rule.get(k)
                    for k in ("canonical_name", "food_group", "allergens", "allergen_status", "dietary_origin")
                },
                "recipe_occurrences": used[cid],
                "forms": {
                    key: {
                        k: forms[key][k]
                        for k in (
                            "nutrition_form",
                            "nutrition_per_100g",
                            "unit_grams",
                            "sources",
                            "confidence",
                            "notes",
                            "enriched_by",
                        )
                    }
                    for key in (cid, f"{cid}#cooked")
                    if key in forms
                },
            }
            out.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    (RELEASE / "dropped.jsonl").write_text(
        "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in drop_log), encoding="utf-8", newline="\n"
    )
    manifest = {
        "release_version": RELEASE_VERSION,
        "schema_version": "mealcraft.recipe.v2",
        "decision": "ADR-0030",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "counts": {
            "released_recipes": len(release),
            "built_before_quota": len(built),
            "enrichment_set": len(enrich_set),
            "released_ingredients": len(used),
            "unbucketed_cuisine": sum(
                r["cuisine"] not in {c for spec in QUOTAS["buckets"].values() for c in spec["cuisines"]} for r in built
            ),
            "dropped_by_reason": dict(dropped.most_common()),
            "by_cuisine": dict(collections.Counter(r["cuisine"] for r in release).most_common()),
            "by_course": dict(collections.Counter(r["course"] for r in release).most_common()),
            "by_source": dict(collections.Counter(r["source"]["dataset"] for r in release).most_common()),
            "servings_estimated": sum(r["servings_basis"] == "estimated" for r in release),
            "time_estimated": sum(r["time_basis"] == "estimated" for r in release),
            "lines_with_estimated_amount": sum(
                line["grams_basis"] == "estimated" for r in release for line in r["ingredients"]
            ),
        },
        "licensing": "Each record keeps its own licence in source.license; the release is a collection, not "
        "relicensed. Non-commercial use only. See ATTRIBUTION.md.",
    }
    summary = {
        "release_version": manifest["release_version"],
        "created_at": manifest["created_at"],
        "coverage": {
            "released_recipes": len(release),
            "enrichment_set": len(enrich_set),
            "released_ingredients": len(used),
            "recipes_with_every_field": len(release),
        },
        "by_cuisine": manifest["counts"]["by_cuisine"],
        "by_course": manifest["counts"]["by_course"],
        "by_source": manifest["counts"]["by_source"],
        "estimated_share": {
            "servings": round(manifest["counts"]["servings_estimated"] / max(len(release), 1), 4),
            "times": round(manifest["counts"]["time_estimated"] / max(len(release), 1), 4),
            "ingredient_amounts": round(
                manifest["counts"]["lines_with_estimated_amount"] / max(sum(len(r["ingredients"]) for r in release), 1),
                4,
            ),
        },
        "dropped_by_reason": manifest["counts"]["dropped_by_reason"],
        "allergen_rules_pending_human": sum(1 for rule in rules.values() if rule.get("allergen_status") != "confirmed"),
        "nutrition_per_serving": {
            "median_energy_kcal": (
                sorted(r["nutrition"]["energy_kcal"] for r in release)[len(release) // 2] if release else None
            )
        },
    }
    (RELEASE / "quality_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (RELEASE / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
