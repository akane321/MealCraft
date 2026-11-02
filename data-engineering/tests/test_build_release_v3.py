from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_release_v3 as v3  # noqa: E402

NUTRITION = {
    "energy_kcal": 100.0,
    "protein_g": 1.0,
    "carbohydrate_g": 1.0,
    "fat_g": 1.0,
    "sodium_mg": 1.0,
    "sugar_g": 1.0,
}
FORM = {
    "nutrition_per_100g": {**NUTRITION, "energy_kcal": 20.0},
    "unit_grams": [{"unit": "piece", "grams": 100.0}],
    "sources": [{"url": "https://fdc.nal.usda.gov/x"}],
}
ENTRIES = {
    cid: {"ingredient_id": cid, "canonical_name": cid[4:].lower(), "allergens": allergens, "forms": {cid: FORM}}
    for cid, allergens in (("ING_TOMATO", []), ("ING_EGG", ["eggs"]))
}
RULES = {cid: {"allergens": e["allergens"], "allergen_status": "confirmed"} for cid, e in ENTRIES.items()}
OTHER = sorted(v3.BUCKETED - {"american", "chinese", "thai"})


def recipe(number: int, cuisine: str, course: str = "main", title: str | None = None, cid: str = "ING_TOMATO") -> dict:
    line = {
        "original_text": "2 tomatoes",
        "canonical_ingredient_id": cid,
        "canonical_name": cid[4:].lower(),
        "quantity_min": 2.0,
        "quantity_max": None,
        "unit": "piece",
        "preparation": [],
        "optional": False,
        "grams": 200.0,
        "grams_basis": "stated",
        "allergens": RULES.get(cid, {"allergens": []})["allergens"],
    }
    return {
        "recipe_id": f"RCP2_{number:012d}",
        "title": title or f"Dish {number}",
        "source": {"dataset": "RecipeNLG (Gathered)", "candidate_id": f"recipenlg:{number}", "license": "x"},
        "cuisine": cuisine,
        "course": course,
        "servings": 2,
        "servings_basis": "stated",
        "time_basis": "estimated",
        "ingredients": [line, {**line, "original_text": "1 tomato", "quantity_min": 1.0, "grams": 100.0}],
        "instructions": [{"step_number": 1, "text": "Slice and serve."}],
        "allergens": sorted(set(line["allergens"])),
        "nutrition": dict(NUTRITION),
        "enrichment": {"by": "openai/gpt-5.4-mini"},
    }


def inputs(v22: list[dict], over: list[dict], new: list[dict], drops: tuple = ()) -> tuple:
    # v2.2 lines are kept as written, not re-serialised: a key order json.dumps(sort_keys=True) would change.
    lines = [json.dumps(dict(reversed(list(r.items()))), ensure_ascii=False) for r in v22]
    ingredients = "".join(json.dumps(e, sort_keys=True) + "\n" for e in ENTRIES.values()).encode()
    rebuilt = {r["recipe_id"] for r in v22} | {r["recipe_id"] for r in over}  # the v2 set holds v2.2's candidates
    sizes = {"v2_enrichment_set": len(rebuilt) + len(drops), "v3_selected": len(new)}
    build_drops = [v3.drop({"candidate_id": c, "title": "t"}, "reviewed incomplete: milk") for c in drops]
    return lines, ingredients, RULES, sizes, [("over_quota", over), ("new", new)], build_drops, {}


def assemble(*args) -> dict[str, bytes]:
    return v3.assemble(*copy.deepcopy(args), minimum=0)


def released(files: dict[str, bytes]) -> dict[str, dict]:
    return {r["recipe_id"]: r for r in map(json.loads, files["recipes.jsonl"].decode().splitlines())}


def dropped(files: dict[str, bytes]) -> dict[str, str]:
    return {d["candidate_id"]: d["reason"] for d in map(json.loads, files["dropped.jsonl"].decode().splitlines())}


V22 = [recipe(1, "american")] + [recipe(n, OTHER[n]) for n in range(2, 11)]


class BuildReleaseV3Test(unittest.TestCase):
    def test_v2_2_records_are_copied_byte_for_byte_and_ingredients_unchanged(self) -> None:
        args = inputs(V22, [recipe(1, "american"), recipe(20, "chinese")], [])
        files = assemble(*args)
        lines = files["recipes.jsonl"].decode().splitlines()
        self.assertTrue(set(args[0]) <= set(lines))
        self.assertEqual(files["ingredients.jsonl"], args[1])
        self.assertEqual(len(lines), 11)  # the v2.2 id in the over-quota leg is not added twice
        self.assertEqual(lines, sorted(lines, key=lambda line: json.loads(line)["recipe_id"]))

    def test_exclusions_are_dropped_with_their_reason(self) -> None:
        over = [
            recipe(20, "chinese", cid="ING_NEW"),
            recipe(21, "international"),
            recipe(22, "thai", title="  DISH   3 "),
            recipe(23, "thai", title="Twin noodles"),
        ]
        new = [recipe(30, "thai", title="twin  NOODLES"), {**recipe(31, "thai"), "instructions": []}]
        hot = recipe(32, "thai")
        hot["nutrition"]["energy_kcal"] = 5000.0
        files = assemble(*inputs(V22, over, [*new, hot], drops=("recipenlg:99",)))
        reasons = dropped(files)
        self.assertEqual(reasons["recipenlg:20"], "new ingredient id: ING_NEW")
        self.assertEqual(reasons["recipenlg:21"], "cuisine not in a quota bucket: international")
        self.assertEqual(reasons["recipenlg:22"], "title already in the release: dish 3")
        self.assertEqual(reasons["recipenlg:30"], "title already in the release: twin noodles")  # over-quota first
        self.assertTrue(reasons["recipenlg:31"].startswith("below the importer floor"))
        self.assertTrue(reasons["recipenlg:32"].startswith("implausible energy after the unit-weight correction"))
        self.assertEqual(reasons["recipenlg:99"], "reviewed incomplete: milk")
        self.assertIn("RCP2_000000000023", released(files))
        counts = json.loads(files["release_manifest.json"])["counts"]
        self.assertEqual(counts["released_recipes"] + len(reasons), counts["enrichment_set"])
        self.assertEqual(counts["dropped_by_reason"]["title already in the release"], 2)

    def test_the_label_cap_holds_on_the_final_total_and_keeps_usable_courses_first(self) -> None:
        over = [recipe(20, "american", "dessert"), recipe(21, "american", "side")]
        new = [recipe(22, "american", "main")] + [recipe(n, OTHER[n - 12]) for n in range(23, 28)]
        files = assemble(*inputs(V22, over, new))
        recipes = released(files)
        american = [r for r in recipes.values() if r["cuisine"] == "american"]
        self.assertEqual(len(recipes), 17)
        self.assertLessEqual(len(american), 0.2 * len(recipes))
        self.assertIn("RCP2_000000000021", recipes)
        self.assertIn("RCP2_000000000022", recipes)
        self.assertEqual(dropped(files)["recipenlg:20"], "cuisine label cap: american held at 3 of 17 recipes (20%)")

    def test_the_build_is_deterministic_and_the_fingerprint_covers_the_manifest(self) -> None:
        args = inputs(V22, [recipe(20, "chinese"), recipe(21, "american", "side")], [recipe(22, "thai")])
        first, second = assemble(*args), assemble(*args)
        self.assertEqual(first, second)
        manifest = json.loads(first["release_manifest.json"])
        stamp = manifest.pop("fingerprint")
        body = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
        self.assertEqual(stamp, v3.fingerprint(first["recipes.jsonl"], first["ingredients.jsonl"], body))
        self.assertEqual(manifest["release_version"], "v3")
        self.assertEqual(manifest["counts"]["added_new"], 1)

    def test_the_quality_summary_has_the_shape_of_v2_2s(self) -> None:
        files = assemble(*inputs(V22, [recipe(20, "chinese")], []))
        committed = json.loads((ROOT / "data/release/v2.2/quality_summary.json").read_text(encoding="utf-8"))
        summary = json.loads(files["quality_summary.json"])
        self.assertEqual(list(summary), list(committed))
        self.assertEqual(list(summary["coverage"]), list(committed["coverage"]))
        self.assertEqual(list(summary["estimated_share"]), list(committed["estimated_share"]))

    def test_an_added_recipe_with_allergens_not_from_the_rule_table_stops_the_build(self) -> None:
        wrong = recipe(20, "chinese", cid="ING_EGG")
        wrong["ingredients"][0]["allergens"] = []
        with self.assertRaises(SystemExit):
            assemble(*inputs(V22, [wrong], []))


if __name__ == "__main__":
    unittest.main()
