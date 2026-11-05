from __future__ import annotations

import copy
import hashlib
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


def inputs(v22: list[dict], over: list[dict], new: list[dict], drops: tuple = (), extra: tuple = ()) -> tuple:
    # v2.2 lines are kept as written, not re-serialised: a key order json.dumps(sort_keys=True) would change.
    lines = [json.dumps(dict(reversed(list(r.items()))), ensure_ascii=False) for r in v22]
    ingredients = "".join(json.dumps(e, sort_keys=True) + "\n" for e in ENTRIES.values()).encode()
    rebuilt = {r["recipe_id"] for r in v22} | {r["recipe_id"] for r in over}  # the v2 set holds v2.2's candidates
    sizes = {
        "v2_enrichment_set": len(rebuilt) + len(drops),
        "v3_selected": len(new) + len(extra),
        "v3_selected_wave_1": len(new),
    }
    build_drops = [v3.drop({"candidate_id": c, "title": "t"}, "reviewed incomplete: milk") for c in drops]
    legs = [("over_quota", over), ("new", new), ("extra", list(extra))]
    return lines, ingredients, RULES, sizes, legs, build_drops, {}


def assemble(*args, **options) -> dict[str, bytes]:
    return v3.assemble(*copy.deepcopy(args), **{"minimum": 0, **options})


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

    def test_the_label_cap_cuts_the_extra_wave_before_wave_1(self) -> None:
        new = [recipe(20, "american", "dessert")]
        extra = [recipe(21, "american"), recipe(22, "american")] + [recipe(n, OTHER[n - 12]) for n in range(23, 28)]
        files = assemble(*inputs(V22, [], new, extra=extra))
        recipes = released(files)
        self.assertIn("RCP2_000000000020", recipes)  # a wave-1 dessert stays over an extra-wave main
        self.assertIn("RCP2_000000000021", recipes)
        self.assertEqual(dropped(files)["recipenlg:22"], "cuisine label cap: american held at 3 of 17 recipes (20%)")
        counts = json.loads(files["release_manifest.json"])["counts"]
        self.assertEqual((counts["added_new_wave_1"], counts["added_new_wave_2"]), (1, 6))
        self.assertEqual(counts["enriched_by_wave_2"], {"openai/gpt-5.4-mini": 6})

    def test_a_changed_or_missing_first_build_record_stops_the_build(self) -> None:
        args = inputs(V22, [recipe(20, "chinese")], [])
        line = released(assemble(*args))["RCP2_000000000020"]
        digest = hashlib.sha256(json.dumps(line, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        assemble(*args, first_build={"RCP2_000000000020": digest})
        with self.assertRaises(SystemExit):
            assemble(*args, first_build={"RCP2_000000000020": "0" * 64})
        with self.assertRaises(SystemExit):
            assemble(*args, first_build={"RCP2_000000000099": digest})

    def test_recipes_over_the_byte_limit_stop_the_build(self) -> None:
        args = inputs(V22, [recipe(20, "chinese")], [])
        with self.assertRaises(SystemExit):
            assemble(*args, max_bytes=1000)

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


class V3LineClassesTest(unittest.TestCase):
    """Rule 7 (issue #426), on v2.2's own ingredient forms."""

    entries = {r["ingredient_id"]: r for r in map(json.loads, (v3.V22 / "ingredients.jsonl").read_text().splitlines())}
    forms = {key: form for row in entries.values() for key, form in row["forms"].items()}

    def fix(self, text: str, cid: str, unit: str | None, quantity: float | None, grams: float, basis: str, **dish):
        item = {
            "original_text": text,
            "canonical_ingredient_id": cid,
            "unit": unit,
            "quantity_min": quantity,
            "quantity_max": None,
            "grams": grams,
            "grams_basis": basis,
            "preparation": [],
        }
        dish = {"title": "Dish", "instructions": [{"text": "Cook."}], **dish}
        return v3.correct_v3_line(item, self.forms, dish)

    def test_cooked_rice_takes_the_cooked_form_and_its_cup(self) -> None:
        new, name, _ = self.fix("4 cups steamed rice, hot", "ING_RICE", "cup", 4.0, 740.0, "stated")
        self.assertEqual((name, new["preparation"], new["grams"]), ("cooked_rice", ["cooked"], 632.0))
        kept, _, _ = self.fix("steamed rice, to serve", "ING_RICE", None, None, 370.0, "estimated")
        self.assertEqual((kept["grams"], v3.correct.form_key(kept)), (370.0, "ING_RICE#cooked"))

    def test_dry_rice_and_a_mass_of_steamed_rice_are_left(self) -> None:
        self.assertIsNone(self.fix("2 cups uncooked rice", "ING_RICE", "cup", 2.0, 370.0, "stated"))
        self.assertIsNone(self.fix("2 cups rice, cooked", "ING_RICE", "cup", 2.0, 370.0, "stated"))
        self.assertIsNone(self.fix("60 g steamed rice", "ING_RICE", "g", 60.0, 60.0, "stated"))

    def test_an_estimated_can_takes_its_stated_package_mass(self) -> None:
        new, name, source = self.fix(
            "1 (14 ounce) can coconut milk", "ING_COCONUT_MILK", "can", 1.0, 226.0, "estimated"
        )
        self.assertEqual((name, new["grams"], source), ("package_mass", 396.9, "the line's own text"))

    def test_drained_liquid_packed_marinade_and_misread_packages_are_left(self) -> None:
        drained = "1 (20 ounce) can crushed pineapple, drained"
        self.assertIsNone(self.fix(drained, "ING_PINEAPPLE", "can", 1.0, 400.0, "estimated"))
        self.assertIsNone(self.fix("1 (15 ounce) can chickpeas", "ING_CHICKPEA", "can", 1.0, 152.0, "estimated"))
        part = "1 (13 ounce) can dulce de leche (Use 1/2 cup out of the can)"
        self.assertIsNone(self.fix(part, "ING_CARAMEL", "can", 1.0, 160.0, "estimated"))
        steps = [{"text": "Remove chicken from marinade. Discard marinade."}]
        hoisin = self.fix(
            "1 (7.5 ounce) jar hoisin sauce", "ING_HOISIN", "jar", 1.0, 40.0, "estimated", instructions=steps
        )
        self.assertIsNone(hoisin)
        yeast = "1 (.25 ounce) package active dry yeast"
        self.assertIsNone(self.fix(yeast, "ING_YEAST", "package", 1.0, 7.0, "estimated"))
        stated = "1 (14 ounce) can coconut milk"
        self.assertIsNone(self.fix(stated, "ING_COCONUT_MILK", "can", 1.0, 226.0, "stated"))


class CommittedReleaseV3Test(unittest.TestCase):
    def test_every_first_build_record_is_byte_identical(self) -> None:
        # The first v3 build (12,895) = v2.2's records + the added lines in v3_first_build_lines.tsv.
        def hashes(path: Path) -> dict[str, str]:
            lines = path.read_text(encoding="utf-8").splitlines()
            return {json.loads(line)["recipe_id"]: hashlib.sha256(line.encode()).hexdigest() for line in lines}

        old = {**hashes(v3.V22 / "recipes.jsonl"), **v3.read_first_build()}
        self.assertEqual(len(old), 12895)
        # The recipes a reviewed row corrects (data/enrichment/v3-corrections.csv) and the recipes a rule-7 class
        # changes (corrections.jsonl, owner 2026-11-04, issue #426) are the only exceptions.
        corrected = {row["recipe_id"] for row in v3.reviewed.read_table() if row["field"] != "withdraw"}
        changes = map(json.loads, (v3.OUT / "corrections.jsonl").read_text(encoding="utf-8").splitlines())
        corrected |= {c["recipe_id"] for c in changes if c["class"] in v3.V3_CLASSES}
        self.assertFalse(corrected & set(hashes(v3.V22 / "recipes.jsonl")))  # never a v2.2 record
        old = {key: digest for key, digest in old.items() if key not in corrected}
        current = hashes(v3.OUT / "recipes.jsonl")
        self.assertEqual({key: current.get(key) for key in old}, old)

    def test_the_committed_counts(self) -> None:
        counts = json.loads((v3.OUT / "release_manifest.json").read_text(encoding="utf-8"))["counts"]
        parts = ("released_recipes", "from_v2_2", "added_over_quota", "added_new_wave_1", "added_new_wave_2")
        self.assertEqual([counts[k] for k in parts], [18335, 8968, 1867, 2237, 5263])
        self.assertEqual(counts["enriched_by_wave_2"], {"openai/gpt-5.4-mini": 2685, "claude/claude-sonnet-5-5": 2578})
        self.assertLessEqual((v3.OUT / "recipes.jsonl").stat().st_size, v3.MAX_RECIPES_BYTES)


if __name__ == "__main__":
    unittest.main()
