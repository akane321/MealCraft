"""The committed samples of the human checks of data release v3's new recipes (issue #392) are the draws."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import allergen_review  # noqa: E402
import manual_check  # noqa: E402
import review_sampling  # noqa: E402


class NewRecipeDrawsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.version, cls.recipes = review_sampling.new_recipes()
        _, old = review_sampling.release_recipes()
        cls.old_ids = {recipe["recipe_id"] for recipe in old}

    def test_the_population_is_the_recipes_v2_2_does_not_have(self) -> None:
        self.assertEqual(self.version, "v3 (new recipes, not in v2.2)")
        self.assertTrue(self.recipes)
        self.assertFalse({recipe["recipe_id"] for recipe in self.recipes} & self.old_ids)

    def test_the_committed_samples_are_the_draws(self) -> None:
        for module in (manual_check, allergen_review):
            with self.subTest(module=module.__name__):
                committed = json.loads((module.NEW_OUT / "sample.json").read_text(encoding="utf-8"))
                self.assertEqual(module.draw(self.version, self.recipes, review_sampling.NEW_SEED), committed)
                self.assertEqual(committed["size"], module.SIZE)
                self.assertNotEqual(module.NEW_OUT, module.OUT)


class WaveTwoDrawsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.version, cls.recipes = review_sampling.new_recipes(wave=2)
        _, first = review_sampling.new_recipes()
        _, old = review_sampling.release_recipes()
        cls.earlier = {recipe["recipe_id"] for recipe in first + old}

    def test_the_population_is_the_extra_wave_only(self) -> None:
        self.assertEqual(self.version, "v3 (wave 2 new recipes, not in the first v3 build)")
        self.assertEqual(len(self.recipes), 5263)
        self.assertFalse({recipe["recipe_id"] for recipe in self.recipes} & self.earlier)

    def test_the_committed_samples_are_the_draws_and_redraw_the_same(self) -> None:
        draws = {
            manual_check: lambda: manual_check.draw(self.version, self.recipes, 20261104, 60),
            allergen_review: lambda: allergen_review.draw(self.version, self.recipes, 20261104, 30, 2),
        }
        for module, again in draws.items():
            with self.subTest(module=module.__name__):
                committed = json.loads((module.WAVE_OUT[2] / "sample.json").read_text(encoding="utf-8"))
                self.assertEqual(again(), committed)
                self.assertEqual(again(), again())
                self.assertEqual(committed["seed"], review_sampling.WAVE_SEEDS[2])
                self.assertEqual(committed["size"], {manual_check: 60, allergen_review: 30}[module])
                self.assertNotEqual(module.WAVE_OUT[2], module.WAVE_OUT[1])


class WeightedScoreTest(unittest.TestCase):
    def test_the_combined_rate_weights_strata_by_recipes_and_skips_unchecked_ones(self) -> None:
        combo = review_sampling.combined(
            [
                {"name": "a", "population": 300, "k": 9, "n": 10},
                {"name": "b", "population": 100, "k": 5, "n": 10},
                {"name": "c", "population": 50, "k": 0, "n": 0},
            ]
        )
        self.assertEqual(combo["weighted"], 0.8)  # (0.9 * 300 + 0.5 * 100) / 400
        self.assertEqual(combo["cover"], {"recipes": 400, "of": 450})
        self.assertEqual([part["rate"] for part in combo["strata"]], [0.9, 0.5, None])
        self.assertEqual(combo["strata"][0]["wilson95"], review_sampling.wilson(9, 10))
        self.assertIsNone(combo["strata"][2]["wilson95"])

    def test_each_review_makes_its_waves_strata(self) -> None:
        manual = manual_check.by_wave(
            {1: {"correct": 9, "checked": 10, "sampled": 12}, 2: {"correct": 3, "checked": 6, "sampled": 8}},
            {1: 3, 2: 1},
        )
        self.assertEqual([part["name"] for part in manual["strata"]], ["wave 1", "wave 2"])
        self.assertEqual(manual["weighted"], 0.8)  # (0.9 * 3 + 0.5 * 1) / 4
        self.assertEqual(manual["correct_over_sampled"]["rate"], 0.6)  # 12 correct of 20 sampled
        self.assertNotIn("wilson95", manual["correct_over_sampled"])
        strata = {
            1: {"strata": {"milk": {"recipes_in_release": 30, "agree": 2, "checked": 2}}},
            2: {
                "strata": {
                    "milk": {"recipes_in_release": 10, "agree": 0, "checked": 2},
                    "none": {"recipes_in_release": 60, "agree": 0, "checked": 0},
                }
            },
        }
        allergens = allergen_review.by_wave(strata)
        self.assertEqual(len(allergens["strata"]), 3)
        self.assertEqual(allergens["weighted"], 0.75)  # (1.0 * 30 + 0.0 * 10) / 40
        self.assertEqual(allergens["cover"], {"recipes": 40, "of": 100})
        self.assertIn("**75.0%**", "\n".join(review_sampling.combined_lines(allergens, "agreement", "Agree")))


if __name__ == "__main__":
    unittest.main()
