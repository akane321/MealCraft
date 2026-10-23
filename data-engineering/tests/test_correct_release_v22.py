from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from correct_release_v22 import (  # noqa: E402
    GUARD_PIECE_SHARE,
    SOURCE,
    TARGET,
    correct_line,
    correct_recipe,
    guards,
    read_jsonl,
)

ENTRIES = {row["ingredient_id"]: row for row in read_jsonl(SOURCE / "ingredients.jsonl")}
FORMS = {key: form for row in ENTRIES.values() for key, form in row["forms"].items()}


def line(text: str, cid: str, unit: str | None, quantity: float, grams: float, basis: str = "stated") -> dict:
    return {
        "original_text": text,
        "canonical_ingredient_id": cid,
        "unit": unit,
        "quantity_min": quantity,
        "quantity_max": None,
        "grams": grams,
        "grams_basis": basis,
        "preparation": [],
    }


def corrected(item: dict) -> dict:
    found = correct_line(item, FORMS)
    return found[0] if found else item


class CorrectionTests(unittest.TestCase):
    def test_a_stated_whole_bird_weighs_what_its_text_says(self) -> None:
        chicken = corrected(line("1 (5 1/2-pound) whole chicken", "ING_CHICKEN", "piece", 1, 100.0))
        self.assertAlmostEqual(chicken["grams"], 2494.8, delta=1)
        self.assertEqual(chicken["grams_correction"], "stated_weight")

    def test_a_parenthetical_total_is_not_multiplied_by_the_count(self) -> None:
        shrimp = line("20 shrimp (8 oz.)", "ING_SHRIMP", "piece", 20, 4535.9, "stated_package")
        self.assertEqual(corrected(shrimp)["grams"], 226.8)
        each = line("8 (5 ounce) salmon fillets, with skin", "ING_SALMON", "piece", 8, 1134.0, "stated_package")
        self.assertIsNone(correct_line(each, FORMS))
        lobsters = line("2 small (1 pound) fresh live lobsters", "ING_LOBSTER", "piece", 2, 907.2, "stated_package")
        self.assertIsNone(correct_line(lobsters, FORMS))

    def test_a_whole_pizza_crust_takes_its_own_loaf_weight(self) -> None:
        self.assertGreaterEqual(corrected(line("1 pizza crust", "ING_PIZZA_CRUST", "piece", 1, 43.0))["grams"], 300)

    def test_a_lasagna_sheet_takes_the_cited_sheet_weight(self) -> None:
        noodles = corrected(line("9 lasagna noodles", "ING_PASTA", "piece", 9, 9.0))
        self.assertGreaterEqual(noodles["grams"], 135)
        self.assertIsNone(correct_line(line("4 oz spaghetti strands", "ING_PASTA", "piece", 4, 4.0), FORMS))

    def test_fresh_red_pepper_is_bell_pepper_and_flakes_stay_cayenne(self) -> None:
        diced = corrected(line("1/2 cup red pepper, diced", "ING_CAYENNE", "cup", 0.5, 43.0))
        self.assertEqual(diced["canonical_ingredient_id"], "ING_BELL_PEPPER")
        self.assertEqual(diced["grams"], 74.5)
        for text, unit in (
            ("1 tsp. crushed red pepper", "tsp"),
            ("1/2 tsp. red pepper", "tsp"),
            ("1 dried red pepper", "piece"),
        ):
            self.assertIsNone(correct_line(line(text, "ING_CAYENNE", unit, 1, 1.8), FORMS), text)

    def test_a_whole_head_is_weighed_as_a_head_and_leaves_stay_leaves(self) -> None:
        self.assertEqual(
            corrected(line("1 small head cabbage, shredded", "ING_CABBAGE", "piece", 1, 100.0))["grams"], 908.0
        )
        head = line("1 large head cauliflower, cut into florets", "ING_CAULIFLOWER", "piece", 1, 25.0)
        self.assertEqual(corrected(head)["grams"], 588.0)
        self.assertIsNone(correct_line(line("4 lettuce leaves", "ING_LETTUCE", "piece", 4, 40.0), FORMS))
        self.assertIsNone(correct_line(line("2 pineapple slices", "ING_PINEAPPLE", "piece", 2, 28.0), FORMS))

    def test_ambiguous_masses_and_alternatives_are_left(self) -> None:
        several = line("6 medium potatoes (about 2 lb.)", "ING_POTATO", "piece", 6, 1278.0)
        self.assertIsNone(correct_line(several, FORMS))
        alternative = line("3 fresh mushrooms, sliced or 4 oz. can mushrooms", "ING_MUSHROOM", "piece", 3, 54.0)
        self.assertIsNone(correct_line(alternative, FORMS))
        compound = line("2 (1 lb. 5 oz.) pie fillings", "ING_FRUIT_PIE_FILLING", "piece", 2, 1190.0)
        self.assertIsNone(correct_line(compound, FORMS))
        thighs = line("8 (1 1/4 lb) boneless skinless chicken thighs", "ING_CHICKEN_THIGH", "piece", 8, 800.0)
        self.assertIsNone(correct_line(thighs, FORMS))

    def test_nutrition_moves_by_the_changed_grams_only(self) -> None:
        crust = line("1 pizza crust", "ING_PIZZA_CRUST", "piece", 1, 43.0)
        crust["allergens"] = ENTRIES["ING_PIZZA_CRUST"]["allergens"]
        nutrition = {
            "energy_kcal": 500.0,
            "protein_g": 0,
            "carbohydrate_g": 0,
            "fat_g": 0,
            "sodium_mg": 0,
            "sugar_g": 0,
        }
        recipe = {"recipe_id": "R", "servings": 2, "ingredients": [crust], "nutrition": nutrition,
                  "allergens": sorted(crust["allergens"])}  # fmt: skip
        out, changes = correct_recipe(recipe, FORMS, ENTRIES)
        kcal = FORMS["ING_PIZZA_CRUST"]["nutrition_per_100g"]["energy_kcal"]
        self.assertAlmostEqual(out["nutrition"]["energy_kcal"], round(500 + (340 - 43) * kcal / 100 / 2, 1))
        self.assertEqual(len(changes), 1)


class ReleaseTests(unittest.TestCase):
    def test_the_committed_v2_2_is_what_the_step_writes_and_v2_1_is_untouched(self) -> None:
        before = (SOURCE / "recipes.jsonl").read_text(encoding="utf-8").splitlines()
        after = (TARGET / "recipes.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(before), len(after))
        changed = 0
        for old, new in zip(before, after, strict=True):
            recipe, changes = correct_recipe(json.loads(old), FORMS, ENTRIES)
            self.assertEqual(json.dumps(recipe, ensure_ascii=False, sort_keys=True), new)
            changed += bool(changes)
            if not changes:
                self.assertEqual(old, new)
        manifest = json.loads((TARGET / "release_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["derived_from"]["corrected_recipes"], changed)

    def test_the_guards_hold_on_v2_2(self) -> None:
        guard = guards(read_jsonl(TARGET / "recipes.jsonl"), ENTRIES)
        self.assertEqual(guard["n_times_total_over_3kg"], [])
        self.assertEqual(guard["energy"], [])
        flagged = {g["form"] for g in guard["piece_under_30pct_of_whole"]}
        self.assertIn("ING_PIZZA_CRUST", flagged)
        self.assertTrue(
            all(
                g["piece"] < GUARD_PIECE_SHARE * max(g.get("head", 0), g.get("loaf", 0))
                for g in guard["piece_under_30pct_of_whole"]
            )
        )


if __name__ == "__main__":
    unittest.main()
