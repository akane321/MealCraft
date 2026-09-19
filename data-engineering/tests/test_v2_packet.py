from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import v2_packet  # noqa: E402

INGREDIENT = {"ingredient_id": "ING_BUTTER", "units_to_weigh": ["cup", "stick"]}
GOOD_INGREDIENT = {
    "ingredient_id": "ING_BUTTER",
    "nutrition_form": "unsalted butter",
    "nutrition_per_100g": {
        "energy_kcal": 717,
        "protein_g": 0.85,
        "carbohydrate_g": 0.06,
        "fat_g": 81.1,
        "sodium_mg": 11,
        "sugar_g": 0.06,
    },
    "unit_grams": [{"unit": "cup", "grams": 227, "basis": "USDA"}, {"unit": "stick", "grams": 113, "basis": "label"}],
    "allergen_opinion": ["milk"],
    "sources": [{"title": "USDA", "url": "https://fdc.nal.usda.gov/"}],
    "confidence": 0.95,
    "notes": "",
}
RECIPE = {
    "candidate_id": "wikibooks:1",
    "servings": 4,
    "ingredients": [{"index": 1, "needs_amount": False}, {"index": 2, "needs_amount": True}],
}
GOOD_RECIPE = {
    "candidate_id": "wikibooks:1",
    "prep_minutes": 10,
    "cook_minutes": 20,
    "passive_minutes": 0,
    "time_basis": "stated",
    "servings": 4,
    "course": "main",
    "cuisine": "japanese",
    "meal_types": ["dinner"],
    "difficulty": "easy",
    "line_estimates": [{"index": 2, "quantity": 0.5, "unit": "tsp", "basis": "salt to taste"}],
    "evidence": {k: "x" for k in ("time", "servings", "course", "cuisine", "meal_types", "difficulty")},
    "confidence": {k: 0.8 for k in ("time", "servings", "course", "cuisine", "meal_types", "difficulty")},
}


class PacketTests(unittest.TestCase):
    def test_partition_is_stable_and_overlap_goes_elsewhere(self):
        ids = [f"recipenlg:{n}" for n in range(3000)]
        parts = [v2_packet.part_of(i) for i in ids]
        self.assertEqual(parts, [v2_packet.part_of(i) for i in ids])
        counts = {p: sum(1 for primary, _ in parts if primary == p) for p in v2_packet.PARTS}
        self.assertTrue(all(800 < c < 1200 for c in counts.values()), counts)
        overlaps = [(p, o) for p, o in parts if o]
        self.assertTrue(30 < len(overlaps) < 180)
        self.assertTrue(all(p != o for p, o in overlaps))

    def test_shards_split_a_part_without_overlap(self):
        ids = [f"recipenlg:{n}" for n in range(500)]
        slices = [{i for i in ids if v2_packet.in_shard(i, f"{k}/4")} for k in range(1, 5)]
        self.assertEqual(set().union(*slices), set(ids))
        self.assertEqual(sum(len(s) for s in slices), len(ids))

    def test_valid_results_pass(self):
        self.assertEqual(v2_packet.check_ingredient(INGREDIENT, GOOD_INGREDIENT), [])
        self.assertEqual(v2_packet.check_recipe(RECIPE, GOOD_RECIPE), [])

    def test_ingredient_errors_are_caught(self):
        missing_unit = {**GOOD_INGREDIENT, "unit_grams": GOOD_INGREDIENT["unit_grams"][:1]}
        self.assertTrue(v2_packet.check_ingredient(INGREDIENT, missing_unit))
        bad_energy = {
            **GOOD_INGREDIENT,
            "nutrition_per_100g": {**GOOD_INGREDIENT["nutrition_per_100g"], "energy_kcal": 200},
        }
        self.assertTrue(any("energy" in e for e in v2_packet.check_ingredient(INGREDIENT, bad_energy)))
        self.assertTrue(v2_packet.check_ingredient(INGREDIENT, {**GOOD_INGREDIENT, "sources": []}))

    def test_recipe_errors_are_caught(self):
        self.assertTrue(v2_packet.check_recipe(RECIPE, {**GOOD_RECIPE, "servings": 6}))  # stated servings kept
        self.assertTrue(v2_packet.check_recipe(RECIPE, {**GOOD_RECIPE, "line_estimates": []}))
        self.assertTrue(v2_packet.check_recipe(RECIPE, {**GOOD_RECIPE, "cuisine": "martian"}))
        self.assertTrue(v2_packet.check_recipe(RECIPE, {**GOOD_RECIPE, "meal_types": []}))
        fried = {
            **GOOD_RECIPE,
            "consumed_estimates": [{"index": 1, "quantity": 3, "unit": "tbsp", "basis": "absorbed"}],
        }
        self.assertEqual(v2_packet.check_recipe(RECIPE, fried), [])
        wrong_line = {**GOOD_RECIPE, "consumed_estimates": [{"index": 2, "quantity": 3, "unit": "tbsp", "basis": "x"}]}
        self.assertTrue(v2_packet.check_recipe(RECIPE, wrong_line))


if __name__ == "__main__":
    unittest.main()
