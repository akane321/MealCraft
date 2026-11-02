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


if __name__ == "__main__":
    unittest.main()
